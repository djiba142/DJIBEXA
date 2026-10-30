from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import AuditLog, Tenant
from notifications.models import Notification
from products.models import Product
from users.models import User
from .labels import ensure_carton_units
from .costing import consume_fifo_cost
from .models import (
    Carton,
    InventoryCostLayer,
    InventoryCount,
    InventoryCountItem,
    InventoryLocation,
    SampleCarton,
    StockItem,
    StockFileImport,
    StockMovement,
    StockReplenishmentRequest,
    StockTransfer,
    StockUnit,
)


class InventoryApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='stock_manager',
            password='secret123',
            pin_code='1234',
            role='stock',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.product = Product.objects.create(
            sku='INV-100',
            name='Sac à dos Pro',
            purchase_price='50000',
            selling_price='85000',
            quantity=0,
            alert_threshold=5,
        )

    def test_create_stock_location(self):
        payload = {
            'name': 'Entrepôt central',
            'code': 'ENT-01',
            'location_type': 'warehouse',
            'address': 'Conakry',
        }
        response = self.client.post('/api/inventory/locations/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(InventoryLocation.objects.count(), 1)
        self.assertEqual(response.data['code'], 'ENT-01')

    def test_initial_stock_file_submits_count_without_creating_receipt_and_blocks_duplicate_imports(self):
        location = InventoryLocation.objects.create(
            name='Dépôt import',
            code='WH-IMPORT',
            location_type='warehouse',
        )
        file_content = b'reference,physical_quantity,location\nINV-100,7,WH-IMPORT\n'
        preview = self.client.post(
            '/api/inventory/stock-import/',
            {
                'file': SimpleUploadedFile('stock-initial.csv', file_content, content_type='text/csv'),
                'mode': 'initial',
                'reason': 'Chargement du stock de départ.',
            },
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201, preview.data)
        self.assertEqual(preview.data['valid_rows'], 1)
        self.assertEqual(self.product.quantity, 0)
        self.assertFalse(StockItem.objects.filter(product=self.product, location=location).exists())

        confirmed = self.client.post(
            f"/api/inventory/stock-import/{preview.data['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(InventoryCount.objects.get(pk=confirmed.data['summary']['inventory_counts'][0]).status, 'submitted')
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())
        self.assertEqual(StockFileImport.objects.get(pk=preview.data['id']).status, 'submitted')

        repeated = self.client.post(
            '/api/inventory/stock-import/',
            {
                'file': SimpleUploadedFile('same-content.csv', file_content, content_type='text/csv'),
                'mode': 'initial',
                'reason': 'Nouvel essai.',
            },
            format='multipart',
        )
        self.assertEqual(repeated.status_code, 409)

        duplicate_file = SimpleUploadedFile(
            'stock-initial-duplicate.csv',
            b'reference,physical_quantity,location\nINV-100,8,WH-IMPORT\n',
            content_type='text/csv',
        )
        duplicate = self.client.post(
            '/api/inventory/stock-import/',
            {
                'file': duplicate_file,
                'mode': 'initial',
                'reason': 'Tentative de doublon.',
            },
            format='multipart',
        )
        self.assertEqual(duplicate.status_code, 201, duplicate.data)
        self.assertEqual(duplicate.data['error_rows'], 1)
        self.assertIn('déjà en attente', duplicate.data['rows'][0]['errors'][0])

        admin = User.objects.create_user(
            username='stock_import_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=admin)
        count_id = confirmed.data['summary']['inventory_counts'][0]
        validated = self.client.post(
            f'/api/inventory/counts/{count_id}/validate/',
            {},
            format='json',
        )
        self.assertEqual(validated.status_code, 200, validated.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 7)
        self.assertEqual(
            StockMovement.objects.get(product=self.product, location=location).movement_type,
            'adjustment',
        )

    def test_physical_count_import_uses_existing_count_validation_workflow(self):
        location = InventoryLocation.objects.create(
            name='Dépôt comptage',
            code='WH-COUNT',
            location_type='warehouse',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=3)
        self.product.quantity = 3
        self.product.save(update_fields=['quantity'])
        preview = self.client.post(
            '/api/inventory/stock-import/',
            {
                'file': SimpleUploadedFile(
                    'inventaire.csv',
                    b'reference,physical_quantity,location\nINV-100,5,WH-COUNT\n',
                    content_type='text/csv',
                ),
                'mode': 'inventory',
                'reason': 'Comptage physique hebdomadaire.',
            },
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201, preview.data)
        self.assertEqual(preview.data['valid_rows'], 1)

        submitted = self.client.post(
            f"/api/inventory/stock-import/{preview.data['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        count_id = submitted.data['summary']['inventory_counts'][0]
        line = InventoryCountItem.objects.get(inventory_count_id=count_id, product=self.product)
        self.assertEqual(line.theoretical_quantity, 3)
        self.assertEqual(line.counted_quantity, 5)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 3)

        admin = User.objects.create_user(
            username='physical_count_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=admin)
        validated = self.client.post(
            f'/api/inventory/counts/{count_id}/validate/',
            {},
            format='json',
        )
        self.assertEqual(validated.status_code, 200, validated.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 5)
        movement = StockMovement.objects.get(product=self.product, location=location)
        self.assertEqual(movement.movement_type, 'adjustment')
        self.assertIn('Comptage physique hebdomadaire.', movement.notes)

    def test_seller_replenishment_request_runs_through_linked_transfer(self):
        seller = User.objects.create_user(
            username='replenishment_seller',
            password='secret123',
            role='sales',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique demande',
            code='SHOP-REPLENISHMENT',
            location_type='shop',
        )
        source = InventoryLocation.objects.create(
            name='Dépôt demande',
            code='WH-REPLENISHMENT',
            location_type='warehouse',
        )
        shop.authorized_users.add(seller, self.user)
        source.authorized_users.add(self.user)
        self.product.quantity = 5
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=source, quantity=5)

        seller_client = APIClient()
        seller_client.force_authenticate(user=seller)
        response = seller_client.post(
            '/api/inventory/replenishment-requests/',
            {
                'product': self.product.id,
                'shop': shop.id,
                'requested_quantity': 3,
                'request_reason': 'Rupture en boutique.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        request_id = response.data['id']
        self.assertEqual(response.data['remaining_quantity'], 3)
        self.assertTrue(Notification.objects.filter(
            recipient_user=self.user,
            event_type='stock_replenishment_requested',
        ).exists())
        self.assertEqual(
            seller_client.post(
                f'/api/inventory/replenishment-requests/{request_id}/accept/',
                {'allocations': [{'location': source.id, 'quantity': 3}]},
                format='json',
            ).status_code,
            403,
        )

        accepted = self.client.post(
            f'/api/inventory/replenishment-requests/{request_id}/accept/',
            {'allocations': [{'location': source.id, 'quantity': 3}]},
            format='json',
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        transfer = StockTransfer.objects.get(replenishment_request_id=request_id)
        self.assertEqual(transfer.status, 'requested')
        self.assertEqual(transfer.to_location, shop)

        admin = User.objects.create_user(
            username='replenishment_admin',
            password='secret123',
            role='admin',
        )
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        self.assertEqual(
            admin_client.post(f'/api/v1/transfers/{transfer.id}/validate/').status_code,
            200,
        )
        self.assertEqual(self.client.post(f'/api/v1/transfers/{transfer.id}/ship/').status_code, 200)
        received = self.client.post(f'/api/v1/transfers/{transfer.id}/receive/')
        self.assertEqual(received.status_code, 200, received.data)

        request = StockReplenishmentRequest.objects.get(pk=request_id)
        self.assertEqual(request.status, 'completed')
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=shop).quantity,
            3,
        )
        seller_notifications = seller_client.get('/api/notifications/')
        seller_notification_rows = (
            seller_notifications.data.get('results', [])
            if isinstance(seller_notifications.data, dict)
            else seller_notifications.data
        )
        self.assertFalse(any(
            notification.get('event_type') == 'stock_replenishment_requested'
            for notification in seller_notification_rows
        ))

    def test_replenishment_request_duplicate_and_rejection_require_reason(self):
        seller = User.objects.create_user(
            username='replenishment_seller_duplicate',
            password='secret123',
            role='sales',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique demande refus',
            code='SHOP-REPLENISHMENT-REJECT',
            location_type='shop',
        )
        shop.authorized_users.add(seller, self.user)
        seller_client = APIClient()
        seller_client.force_authenticate(user=seller)
        payload = {
            'product': self.product.id,
            'shop': shop.id,
            'requested_quantity': 2,
        }
        created = seller_client.post(
            '/api/inventory/replenishment-requests/',
            payload,
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        duplicate = seller_client.post(
            '/api/inventory/replenishment-requests/',
            payload,
            format='json',
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.data)

        request_id = created.data['id']
        missing_reason = self.client.post(
            f'/api/inventory/replenishment-requests/{request_id}/reject/',
            {},
            format='json',
        )
        self.assertEqual(missing_reason.status_code, 400)
        rejected = self.client.post(
            f'/api/inventory/replenishment-requests/{request_id}/reject/',
            {'reason': 'Aucun stock disponible au dépôt.'},
            format='json',
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(rejected.data['status'], 'rejected')
        self.assertEqual(
            StockReplenishmentRequest.objects.get(pk=request_id).refusal_reason,
            'Aucun stock disponible au dépôt.',
        )

    def test_admin_can_create_multiple_sales_shops_and_assign_a_seller(self):
        admin = User.objects.create_user(
            username='shop_admin',
            password='secret123',
            role='admin',
        )
        seller = User.objects.create_user(
            username='shop_seller',
            password='secret123',
            role='sales',
        )
        self.client.force_authenticate(user=admin)

        first = self.client.post(
            '/api/v1/inventory/locations/',
            {
                'name': 'Boutique Madina',
                'code': 'SHOP-MADINA',
                'location_type': 'shop',
                'address': 'Madina, Conakry',
                'authorized_users': [seller.id],
            },
            format='json',
        )
        second = self.client.post(
            '/api/v1/inventory/locations/',
            {
                'name': 'Boutique Matoto',
                'code': 'SHOP-MATOTO',
                'location_type': 'shop',
                'address': 'Matoto, Conakry',
            },
            format='json',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            InventoryLocation.objects.filter(location_type='shop').count(),
            2,
        )
        madina = InventoryLocation.objects.get(code='SHOP-MADINA')
        self.assertTrue(madina.authorized_users.filter(pk=seller.pk).exists())

        self.client.force_authenticate(user=seller)
        sale_locations = self.client.get('/api/v1/sales/locations/')
        self.assertEqual(sale_locations.status_code, 200)
        self.assertEqual(
            [location['id'] for location in sale_locations.data],
            [madina.id],
        )

    def test_stock_manager_cannot_create_a_sales_shop(self):
        response = self.client.post(
            '/api/v1/inventory/locations/',
            {
                'name': 'Boutique non autorisée',
                'code': 'SHOP-STOCK-FORBIDDEN',
                'location_type': 'shop',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            InventoryLocation.objects.filter(code='SHOP-STOCK-FORBIDDEN').exists(),
        )

    def test_stock_manager_cannot_convert_a_warehouse_into_a_sales_shop(self):
        location = InventoryLocation.objects.create(
            name='Entrepôt autorisé',
            code='WAREHOUSE-SHOP-FORBIDDEN',
            location_type='warehouse',
        )
        location.authorized_users.add(self.user)

        response = self.client.patch(
            f'/api/v1/inventory/locations/{location.id}/',
            {'location_type': 'shop'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        location.refresh_from_db()
        self.assertEqual(location.location_type, 'warehouse')

    def test_stock_manager_submits_inventory_for_admin_validation(self):
        location = InventoryLocation.objects.create(
            name='Boutique inventaire',
            code='INV-COUNT-SHOP',
            location_type='shop',
        )
        location.authorized_users.add(self.user)
        StockItem.objects.create(product=self.product, location=location, quantity=5)
        carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='INV-COUNT-CARTON',
            quantity=4,
            items_per_carton=4,
        )
        listed = self.client.get('/api/v1/inventory/counts/')
        created = self.client.post(
            '/api/v1/inventory/counts/',
            {
                'number': 'INV-STOCK-COUNT',
                'period_type': 'journalier',
                'location': location.id,
                'notes': 'Comptage physique de contrôle',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        new_count_id = created.data['id']
        new_item = InventoryCountItem.objects.get(inventory_count_id=new_count_id, product=self.product)
        retrieved = self.client.get(f'/api/v1/inventory/counts/{new_count_id}/')
        saved = self.client.patch(
            f'/api/v1/inventory/counts/{new_count_id}/',
            {'notes': 'Comptage physique avec écart', 'items': [{'id': new_item.id, 'counted_quantity': 2}]},
            format='json',
        )
        validated = self.client.post(
            f'/api/v1/inventory/counts/{new_count_id}/validate/',
            format='json',
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(validated.status_code, 403)
        submitted = self.client.post(f'/api/v1/inventory/counts/{new_count_id}/submit/', format='json')
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'submitted')
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 5)
        blocked_edit = self.client.patch(
            f'/api/v1/inventory/counts/{new_count_id}/',
            {'items': [{'id': new_item.id, 'counted_quantity': 1}]},
            format='json',
        )
        self.assertEqual(blocked_edit.status_code, 403)
        validated = self.client.post(f'/api/v1/inventory/counts/{new_count_id}/validate/', format='json')
        self.assertEqual(validated.status_code, 403)

        admin = User.objects.create_user(username='count_admin', role='admin', pin_code='1111')
        self.client.force_authenticate(user=admin)
        validated = self.client.post(f'/api/v1/inventory/counts/{new_count_id}/validate/', format='json')
        self.assertEqual(validated.status_code, 200)
        self.assertEqual(validated.data['status'], 'validated')
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 2)
        carton.refresh_from_db()
        self.assertEqual(carton.quantity, 1)
        movement = StockMovement.objects.get(reference='INV-STOCK-COUNT')
        self.assertIn('INV-COUNT-CARTON x 3', movement.notes)

        stock_user = User.objects.create_user(
            username='inventory_stock',
            pin_code='9876',
            role='stock',
        )
        self.client.force_authenticate(user=stock_user)
        stock_access = self.client.get('/api/v1/inventory/counts/')
        self.assertEqual(stock_access.status_code, 200)

    def test_positive_inventory_adjustment_does_not_create_or_enlarge_a_carton(self):
        location = InventoryLocation.objects.create(
            name='Boutique inventaire positif',
            code='INV-COUNT-POS',
            location_type='shop',
        )
        location.authorized_users.add(self.user)
        StockItem.objects.create(product=self.product, location=location, quantity=2)
        carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='INV-COUNT-POS-CARTON',
            quantity=1,
            items_per_carton=1,
        )
        created = self.client.post(
            '/api/v1/inventory/counts/',
            {
                'number': 'INV-COUNT-POSITIVE',
                'period_type': 'journalier',
                'location': location.id,
                'notes': 'Écart positif contrôlé',
            },
            format='json',
        )
        item = InventoryCountItem.objects.get(inventory_count_id=created.data['id'], product=self.product)
        self.client.patch(
            f'/api/v1/inventory/counts/{created.data["id"]}/',
            {'items': [{'id': item.id, 'counted_quantity': 4}]},
            format='json',
        )
        self.client.post(f'/api/v1/inventory/counts/{created.data["id"]}/submit/', format='json')
        admin = User.objects.create_user(username='count_positive_admin', role='admin', pin_code='1111')
        self.client.force_authenticate(user=admin)
        validated = self.client.post(
            f'/api/v1/inventory/counts/{created.data["id"]}/validate/',
            format='json',
        )

        self.assertEqual(validated.status_code, 200, validated.data)
        carton.refresh_from_db()
        self.assertEqual(carton.quantity, 1)
        movement = StockMovement.objects.get(reference='INV-COUNT-POSITIVE')
        self.assertIn('Écart positif de 2 unité(s) laissé non affecté à un carton.', movement.notes)

    def test_location_access_is_filtered_after_explicit_assignment(self):
        other_user = User.objects.create_user(
            username='other_location_user',
            pin_code='4321',
            role='stock',
        )
        location = InventoryLocation.objects.create(
            name='Emplacement privé',
            code='PRIVATE-LOC',
            location_type='warehouse',
        )
        location.authorized_users.add(other_user)

        response = self.client.get('/api/inventory/locations/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(item['id'] == location.id for item in response.data['results']))

    def test_location_cannot_be_deleted_through_api(self):
        location = InventoryLocation.objects.create(
            name='Emplacement protégé',
            code='LOC-PROTECTED',
            location_type='warehouse',
        )

        admin = User.objects.create_user(
            username='location_admin',
            pin_code='4321',
            role='admin',
        )
        self.client.force_authenticate(user=admin)
        response = self.client.delete(f'/api/inventory/locations/{location.id}/')

        self.assertEqual(response.status_code, 405)
        self.assertTrue(InventoryLocation.objects.filter(pk=location.id).exists())

    def test_stock_manager_cannot_grant_location_access_to_other_users(self):
        location = InventoryLocation.objects.create(
            name='Emplacement stock autorisé',
            code='STOCK-AUTH-LOC',
            location_type='warehouse',
        )
        location.authorized_users.add(self.user)
        other_user = User.objects.create_user(
            username='other_stock_user',
            role='stock',
            pin_code='2222',
        )

        response = self.client.patch(
            f'/api/inventory/locations/{location.id}/',
            {'authorized_users': [other_user.id]},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(location.authorized_users.filter(pk=other_user.pk).exists())

    def test_stock_manager_cannot_move_or_adjust_carton_contents_directly(self):
        location = InventoryLocation.objects.create(
            name='Emplacement carton autorisé',
            code='STOCK-CARTON-LOC',
            location_type='warehouse',
        )
        location.authorized_users.add(self.user)
        other_location = InventoryLocation.objects.create(
            name='Emplacement carton non autorisé',
            code='STOCK-CARTON-OTHER',
            location_type='warehouse',
        )
        carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='CTN-STOCK-SECURE',
            quantity=5,
            items_per_carton=1,
        )

        move_response = self.client.patch(
            f'/api/inventory/cartons/{carton.id}/',
            {'location': other_location.id},
            format='json',
        )
        quantity_response = self.client.patch(
            f'/api/inventory/cartons/{carton.id}/',
            {'quantity': 1},
            format='json',
        )

        self.assertEqual(move_response.status_code, 403)
        self.assertEqual(quantity_response.status_code, 400)
        carton.refresh_from_db()
        self.assertEqual(carton.location_id, location.id)
        self.assertEqual(carton.quantity, 5)

    def test_create_stock_in_movement_updates_quantity(self):
        location = InventoryLocation.objects.create(name='Boutique', code='SHOP-01', location_type='shop')
        admin = User.objects.create_user(username='movement_admin', role='admin', pin_code='1111')
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            '/api/inventory/movements/',
            {
                'product': self.product.id,
                'location': location.id,
                'movement_type': 'in',
                'quantity': 25,
                'reference': 'RECEPTION-001',
                'notes': 'Réception initiale',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 25)
        self.assertTrue(AuditLog.objects.filter(model_name='StockMovement', action='stock', record_id=response.data['id']).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 25)

        self.client.force_authenticate(user=self.user)
        denied = self.client.post(
            '/api/inventory/movements/',
            {
                'product': self.product.id,
                'location': location.id,
                'movement_type': 'in',
                'quantity': 1,
                'reference': 'STOCK-DIRECT-FORBIDDEN',
                'notes': 'Tentative de modification directe',
            },
            format='json',
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 25)

    def test_out_movement_cannot_make_stock_negative(self):
        location = InventoryLocation.objects.create(name='Boutique', code='SHOP-02', location_type='shop')
        StockItem.objects.create(product=self.product, location=location, quantity=5)
        self.client.force_authenticate(user=User.objects.create_user(
            username='movement_stock', role='stock', pin_code='2222',
        ))

        response = self.client.post(
            '/api/inventory/movements/',
            {
                'product': self.product.id,
                'location': location.id,
                'movement_type': 'out',
                'quantity': 8,
                'reference': 'VENTE-001',
                'notes': 'Sortie non autorisée',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_create_out_movement_above_location_stock(self):
        location = InventoryLocation.objects.create(
            name='Boutique stock limité',
            code='SHOP-OUT-LIMIT',
            location_type='shop',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=5)
        admin = User.objects.create_user(
            username='movement_admin_out',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=admin)

        response = self.client.post(
            '/api/inventory/movements/',
            {
                'product': self.product.id,
                'location': location.id,
                'movement_type': 'out',
                'quantity': 8,
                'reference': 'VENTE-INSUFFISANTE-001',
                'notes': 'Sortie supérieure au stock disponible',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=location).quantity,
            5,
        )
        self.assertFalse(
            StockMovement.objects.filter(reference='VENTE-INSUFFISANTE-001').exists(),
        )

    def test_unit_status_change_updates_stock(self):
        location = InventoryLocation.objects.create(
            name='Entrepôt pièce suivie',
            code='UNIT-STATUS-WH',
            location_type='warehouse',
        )
        admin = User.objects.create_user(
            username='unit_status_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=admin)
        self.product.quantity = 2
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=location, quantity=2)
        carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='CT-UNIT-STATUS',
            quantity=2,
            initial_quantity=2,
            items_per_carton=2,
        )
        unit = StockUnit.objects.create(
            carton=carton,
            location=location,
            unit_number=1,
            reference='U-UNIT-STATUS-0001',
            qr_code='KAP-UNIT-STATUS-0001',
        )

        response = self.client.post(
            f'/api/v1/inventory/units/{unit.id}/status/',
            {'status': 'sample'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        unit.refresh_from_db()
        carton.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(unit.status, 'sample')
        self.assertEqual(carton.quantity, 1)
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=location).quantity,
            1,
        )
        self.assertEqual(self.product.quantity, 1)

    def test_stock_transfer_requires_validate_ship_and_receive(self):
        source = InventoryLocation.objects.create(name='Entrepôt central', code='ENT-01', location_type='warehouse')
        destination = InventoryLocation.objects.create(name='Boutique principale', code='SHOP-01', location_type='shop')
        source.authorized_users.add(self.user)
        destination.authorized_users.add(self.user)
        StockItem.objects.create(product=self.product, location=source, quantity=20)
        StockItem.objects.create(product=self.product, location=destination, quantity=0)
        first_carton = Carton.objects.create(
            product=self.product,
            location=source,
            reference='TR-FIFO-CARTON-01',
            quantity=5,
            items_per_carton=5,
        )
        second_carton = Carton.objects.create(
            product=self.product,
            location=source,
            reference='TR-FIFO-CARTON-02',
            quantity=5,
            items_per_carton=5,
        )
        InventoryCostLayer.objects.create(
            product=self.product,
            location=source,
            source='opening',
            reference='FIFO-OLD',
            quantity_received=3,
            quantity_remaining=3,
            unit_cost=Decimal('10000.00'),
        )
        InventoryCostLayer.objects.create(
            product=self.product,
            location=source,
            source='receipt',
            reference='FIFO-NEW',
            quantity_received=17,
            quantity_remaining=17,
            unit_cost=Decimal('20000.00'),
        )

        response = self.client.post(
            '/api/inventory/transfers/',
            {
                'product': self.product.id,
                'from_location': source.id,
                'to_location': destination.id,
                'quantity': 8,
                'reference': 'TR-001',
                'notes': 'Transfert magasin',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(StockTransfer.objects.count(), 1)
        self.assertEqual(response.data['status'], 'requested')
        self.assertTrue(AuditLog.objects.filter(
            model_name='StockTransfer',
            action='stock',
            record_id=response.data['id'],
        ).exists())
        self.assertEqual(StockItem.objects.get(product=self.product, location=source).quantity, 20)
        self.assertEqual(StockItem.objects.get(product=self.product, location=destination).quantity, 0)

        transfer_id = response.data['id']
        self.assertEqual(self.client.post(f'/api/v1/transfers/{transfer_id}/validate/', format='json').status_code, 403)
        admin = User.objects.create_user(username='transfer_admin', role='admin', pin_code='3333')
        self.client.force_authenticate(user=admin)
        self.assertEqual(self.client.post(f'/api/v1/transfers/{transfer_id}/validate/', format='json').status_code, 200)
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.post(f'/api/v1/transfers/{transfer_id}/ship/', format='json').status_code, 200)
        self.assertEqual(StockItem.objects.get(product=self.product, location=source).quantity, 12)
        self.assertEqual(StockItem.objects.get(product=self.product, location=destination).quantity, 0)
        in_transit = InventoryCostLayer.objects.filter(transfer_id=transfer_id)
        self.assertEqual(sum(layer.quantity_remaining for layer in in_transit), 8)
        self.assertFalse(in_transit.filter(is_available=True).exists())
        self.assertEqual(self.client.post(f'/api/v1/transfers/{transfer_id}/receive/', format='json').status_code, 200)
        self.assertEqual(StockItem.objects.get(product=self.product, location=destination).quantity, 8)
        first_carton.refresh_from_db()
        second_carton.refresh_from_db()
        self.assertEqual(first_carton.location, destination)
        self.assertEqual(first_carton.quantity, 5)
        self.assertEqual(second_carton.location, source)
        self.assertEqual(second_carton.quantity, 2)
        received_layers = InventoryCostLayer.objects.filter(
            transfer_id=transfer_id,
            location=destination,
            is_available=True,
        ).order_by('unit_cost')
        self.assertEqual(
            list(received_layers.values_list('quantity_remaining', 'unit_cost')),
            [(3, Decimal('10000.00')), (5, Decimal('20000.00'))],
        )
        self.assertEqual(
            consume_fifo_cost(product=self.product, quantity=4, location=destination),
            Decimal('50000.00'),
        )

    def test_transfer_splits_a_carton_and_tracks_shop_units(self):
        source = InventoryLocation.objects.create(name='Entrepôt carton', code='ENT-CARTON', location_type='warehouse')
        destination = InventoryLocation.objects.create(name='Boutique carton', code='SHOP-CARTON', location_type='shop')
        source.authorized_users.add(self.user)
        destination.authorized_users.add(self.user)
        self.product.quantity = 5
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=source, quantity=5)
        carton = Carton.objects.create(
            product=self.product,
            location=source,
            reference='TR-WHOLE-CARTON',
            quantity=5,
            items_per_carton=5,
        )
        created = self.client.post(
            '/api/inventory/transfers/',
            {
                'product': self.product.id,
                'from_location': source.id,
                'to_location': destination.id,
                'quantity': 3,
                'reference': 'TR-PARTIAL-CARTON',
                'notes': 'Tentative de transfert partiel',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        admin = User.objects.create_user(username='transfer_whole_admin', role='admin', pin_code='3333')
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        transfer_id = created.data['id']
        self.assertEqual(admin_client.post(f'/api/v1/transfers/{transfer_id}/validate/').status_code, 200)
        shipped = self.client.post(f'/api/v1/transfers/{transfer_id}/ship/')

        self.assertEqual(shipped.status_code, 200, shipped.data)
        self.assertEqual(StockItem.objects.get(product=self.product, location=source).quantity, 2)
        self.assertEqual(StockTransfer.objects.get(pk=transfer_id).status, 'shipped')
        carton.refresh_from_db()
        self.assertEqual(carton.quantity, 2)
        self.assertTrue(carton.transfer_allocations.get().is_partial)
        units_in_transit = StockUnit.objects.filter(
            carton=carton,
            transfer_id=transfer_id,
            status='in_transit',
        )
        self.assertEqual(units_in_transit.count(), 3)

        received = self.client.post(f'/api/v1/transfers/{transfer_id}/receive/')

        self.assertEqual(received.status_code, 200, received.data)
        carton.refresh_from_db()
        self.assertEqual(carton.location, source)
        self.assertEqual(carton.quantity, 2)
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=destination).quantity,
            3,
        )
        self.assertEqual(
            StockUnit.objects.filter(
                carton=carton,
                location=destination,
                status='available',
            ).count(),
            3,
        )

        secondary_destination = InventoryLocation.objects.create(
            name='Boutique secondaire carton',
            code='SHOP-CARTON-SECONDARY',
            location_type='shop',
        )
        secondary_destination.authorized_users.add(self.user)
        secondary = self.client.post(
            '/api/v1/transfers/',
            {
                'product': self.product.id,
                'from_location': destination.id,
                'to_location': secondary_destination.id,
                'quantity': 2,
                'reference': 'TR-SECONDARY-UNITS',
                'notes': 'Transfert secondaire des pièces séparées',
            },
            format='json',
        )
        self.assertEqual(secondary.status_code, 201, secondary.data)
        secondary_id = secondary.data['id']
        self.assertEqual(
            admin_client.post(f'/api/v1/transfers/{secondary_id}/validate/').status_code,
            200,
        )
        self.assertEqual(
            self.client.post(f'/api/v1/transfers/{secondary_id}/ship/').status_code,
            200,
        )
        self.assertEqual(
            StockUnit.objects.filter(
                carton=carton,
                location=destination,
                status='in_transit',
                is_separated=True,
            ).count(),
            2,
        )
        secondary_received = self.client.post(
            f'/api/v1/transfers/{secondary_id}/receive/',
        )
        self.assertEqual(secondary_received.status_code, 200, secondary_received.data)
        carton.refresh_from_db()
        self.assertEqual(carton.location, source)
        self.assertEqual(carton.quantity, 2)
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=destination).quantity,
            1,
        )
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=secondary_destination).quantity,
            2,
        )
        self.assertEqual(
            StockUnit.objects.filter(
                carton=carton,
                location=secondary_destination,
                status='available',
                is_separated=True,
            ).count(),
            2,
        )

    def test_transfer_receives_actual_quantity_and_requires_variance_reason(self):
        source = InventoryLocation.objects.create(name='Entrepôt écarts', code='ENT-VAR', location_type='warehouse')
        destination = InventoryLocation.objects.create(name='Boutique écarts', code='SHOP-VAR', location_type='shop')
        source.authorized_users.add(self.user)
        destination.authorized_users.add(self.user)
        self.product.quantity = 5
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=source, quantity=5)
        carton = Carton.objects.create(
            product=self.product,
            location=source,
            reference='TR-VARIANCE-CARTON',
            quantity=5,
            items_per_carton=5,
        )
        InventoryCostLayer.objects.create(
            product=self.product,
            location=source,
            source='opening',
            reference='FIFO-VAR',
            quantity_received=5,
            quantity_remaining=5,
            unit_cost=Decimal('10000.00'),
        )
        created = self.client.post(
            '/api/v1/transfers/',
            {
                'product': self.product.id,
                'from_location': source.id,
                'to_location': destination.id,
                'quantity': 5,
                'reference': 'TR-VARIANCE',
                'notes': 'Transfert de test avec écart de comptage.',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        admin = User.objects.create_user(username='transfer_variance_admin', role='admin', pin_code='3333')
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        transfer_id = created.data['id']
        self.assertEqual(admin_client.post(f'/api/v1/transfers/{transfer_id}/validate/').status_code, 200)
        shipped = self.client.post(f'/api/v1/transfers/{transfer_id}/ship/')
        self.assertEqual(shipped.status_code, 200, shipped.data)
        transfer_state = self.client.get(f'/api/v1/transfers/{transfer_id}/')
        self.assertEqual(transfer_state.status_code, 200, transfer_state.data)
        self.assertEqual(transfer_state.data['status'], 'shipped')
        self.assertEqual(transfer_state.data['to_location'], destination.id)

        missing_reason = self.client.post(
            f'/api/v1/transfers/{transfer_id}/receive/',
            {'quantity_received': 3},
            format='json',
        )
        self.assertEqual(missing_reason.status_code, 409)
        received = self.client.post(
            f'/api/v1/transfers/{transfer_id}/receive/',
            {
                'quantity_received': 3,
                'variance_reason': 'Deux unités manquantes lors du comptage à destination.',
            },
            format='json',
        )
        self.assertEqual(received.status_code, 200, received.data)
        self.assertEqual(received.data['quantity_shipped'], 5)
        self.assertEqual(received.data['quantity_received'], 3)
        self.assertEqual(StockItem.objects.get(product=self.product, location=source).quantity, 0)
        self.assertEqual(StockItem.objects.get(product=self.product, location=destination).quantity, 3)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 3)
        carton.refresh_from_db()
        self.assertEqual(carton.location, destination)
        self.assertEqual(carton.quantity, 3)
        self.assertEqual(
            StockUnit.objects.filter(
                carton=carton,
                location=destination,
                status='available',
            ).count(),
            3,
        )
        self.assertEqual(
            StockUnit.objects.filter(
                carton=carton,
                location=destination,
                status='written_off',
            ).count(),
            2,
        )
        self.assertIn('TR-VARIANCE-CARTON: -2', StockMovement.objects.get(
            location=destination,
            reference='TR-VARIANCE',
        ).notes)
        self.assertEqual(
            sum(
                InventoryCostLayer.objects.filter(
                    transfer_id=transfer_id,
                    location=destination,
                    is_available=True,
                ).values_list('quantity_remaining', flat=True),
            ),
            3,
        )

    def test_stock_transfer_rejects_insufficient_source_quantity(self):
        source = InventoryLocation.objects.create(name='Entrepôt central', code='ENT-02', location_type='warehouse')
        destination = InventoryLocation.objects.create(name='Boutique secondaire', code='SHOP-02', location_type='shop')
        source.authorized_users.add(self.user)
        destination.authorized_users.add(self.user)
        StockItem.objects.create(product=self.product, location=source, quantity=3)
        StockItem.objects.create(product=self.product, location=destination, quantity=0)

        response = self.client.post(
            '/api/inventory/transfers/',
            {
                'product': self.product.id,
                'from_location': source.id,
                'to_location': destination.id,
                'quantity': 5,
                'reference': 'TR-002',
                'notes': 'Transfert interdit',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('quantity', response.data)

    def test_location_stock_endpoint_returns_server_side_stock(self):
        location = InventoryLocation.objects.create(name='Stock emplacement', code='STOCK-LOCATION')
        location.authorized_users.add(self.user)
        StockItem.objects.create(product=self.product, location=location, quantity=13)

        response = self.client.get(f'/api/v1/locations/{location.id}/stock/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_quantity'], 13)
        self.assertEqual(response.data['items'][0]['product'], self.product.id)

    def test_versioned_location_alias_is_available(self):
        response = self.client.post(
            '/api/v1/locations/',
            {'name': 'Alias emplacement', 'code': 'ALIAS-LOCATION', 'location_type': 'warehouse'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['code'], 'ALIAS-LOCATION')

    def test_stock_manager_can_create_carton_with_manual_reference(self):
        location = InventoryLocation.objects.create(name='Boutique principale', code='SHOP-03', location_type='shop')
        location.authorized_users.add(self.user)
        self.product.quantity = 30
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=location, quantity=30)

        response = self.client.post(
            '/api/inventory/cartons/',
            {
                'product': self.product.id,
                'location': location.id,
                'reference': 'CTN-000125',
                'quantity': 10,
                'items_per_carton': 5,
                'notes': 'Carton de stock',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['reference'], 'CTN-000125')
        self.assertEqual(response.data['product_reference'], self.product.sku)
        self.assertEqual(response.data['quantity'], 10)

    def test_stock_manager_and_sales_have_separate_carton_permissions(self):
        seller = User.objects.create_user(
            username='carton_scan_sales',
            password='secret123',
            role='sales',
        )
        other_stock_user = User.objects.create_user(
            username='carton_scan_other_stock',
            role='stock',
        )
        manager_shop = InventoryLocation.objects.create(
            name='Boutique stock autorisée',
            code='CARTON-MANAGER-SHOP',
            location_type='shop',
        )
        manager_shop.authorized_users.add(self.user)
        seller_shop = InventoryLocation.objects.create(
            name='Boutique vendeur autorisée',
            code='CARTON-SELLER-SHOP',
            location_type='shop',
        )
        seller_shop.authorized_users.add(seller)
        private_warehouse = InventoryLocation.objects.create(
            name='Entrepôt privé',
            code='CARTON-PRIVATE-WAREHOUSE',
            location_type='warehouse',
        )
        private_warehouse.authorized_users.add(other_stock_user)
        manager_stock = StockItem.objects.create(
            product=self.product,
            location=manager_shop,
            quantity=5,
        )
        seller_stock = StockItem.objects.create(
            product=self.product,
            location=seller_shop,
            quantity=4,
        )
        private_stock = StockItem.objects.create(
            product=self.product,
            location=private_warehouse,
            quantity=9,
        )
        original_product_quantity = self.product.quantity

        manual_stock_list = self.client.get('/api/v1/inventory/stock/')
        manager_carton = self.client.post(
            '/api/v1/inventory/cartons/',
            {
                'product': self.product.id,
                'location': manager_shop.id,
                'reference': 'CTN-MANAGER-001',
                'quantity': 3,
                'items_per_carton': 1,
            },
            format='json',
        )
        self.assertEqual(manual_stock_list.status_code, 200)
        listed_items = manual_stock_list.data.get('results', manual_stock_list.data)
        self.assertTrue(any(item['product'] == self.product.id for item in listed_items))
        self.assertEqual(manager_carton.status_code, 201, manager_carton.data)
        quantity_change = self.client.patch(
            f"/api/v1/inventory/cartons/{manager_carton.data['id']}/",
            {'quantity': 9},
            format='json',
        )
        self.assertEqual(quantity_change.status_code, 400)

        seller_client = APIClient()
        seller_client.force_authenticate(user=seller)
        seller_product_list = seller_client.get('/api/v1/products/')
        self.assertEqual(seller_product_list.status_code, 200)
        self.assertTrue(any(item['id'] == self.product.id for item in seller_product_list.data))
        self.assertEqual(seller_client.get('/api/v1/inventory/cartons/').status_code, 403)
        self.assertEqual(
            seller_client.get(
                f"/api/v1/inventory/cartons/{manager_carton.data['id']}/"
            ).status_code,
            403,
        )
        self.assertEqual(
            seller_client.post(
                '/api/v1/inventory/cartons/',
                {
                    'product': self.product.id,
                    'location': seller_shop.id,
                    'reference': 'CTN-SELLER-FORBIDDEN',
                    'quantity': 1,
                    'items_per_carton': 1,
                },
                format='json',
            ).status_code,
            403,
        )

        self.product.refresh_from_db()
        manager_stock.refresh_from_db()
        seller_stock.refresh_from_db()
        private_stock.refresh_from_db()
        self.assertEqual(self.product.quantity, original_product_quantity)
        self.assertEqual(manager_stock.quantity, 5)
        self.assertEqual(seller_stock.quantity, 4)
        self.assertEqual(private_stock.quantity, 9)

        admin = User.objects.create_user(username='carton_manager_admin', role='admin')
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        self.assertEqual(admin_client.get('/api/v1/inventory/cartons/').status_code, 200)
        admin_carton = admin_client.post(
            '/api/v1/inventory/cartons/',
            {
                'product': self.product.id,
                'location': private_warehouse.id,
                'reference': 'CTN-ADMIN-001',
                'quantity': 2,
                'items_per_carton': 1,
            },
            format='json',
        )
        self.assertEqual(admin_carton.status_code, 201, admin_carton.data)

    def test_carton_view_permission_does_not_grant_management(self):
        location = InventoryLocation.objects.create(
            name='Emplacement lecture seule',
            code='CARTON-READ-ONLY',
            location_type='warehouse',
        )
        location.authorized_users.add(self.user)
        carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='CTN-READ-ONLY',
            quantity=2,
            items_per_carton=1,
        )

        with override_settings(
            ROLE_PERMISSIONS={
                'admin': {'all'},
                'stock': {'cartons.view', 'shop_scan'},
                'sales': {'shop_scan'},
            }
        ):
            listed = self.client.get('/api/v1/inventory/cartons/')
            self.assertEqual(listed.status_code, 200)
            listed_cartons = listed.data.get('results', listed.data)
            self.assertNotIn('qr_code', listed_cartons[0])
            self.assertEqual(
                self.client.patch(
                    f'/api/v1/inventory/cartons/{carton.id}/',
                    {'notes': 'Modification refusée'},
                    format='json',
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.get(f'/api/v1/inventory/cartons/{carton.id}/qr/').status_code,
                404,
            )

    def test_legacy_product_scan_route_is_not_registered(self):
        product = Product.objects.create(
            sku='QR-010',
            name='Produit scannable',
            purchase_price='20000',
            selling_price='35000',
            quantity=4,
            alert_threshold=1,
        )

        response = self.client.get('/api/products/scan/', {'code': product.qr_code})

        self.assertEqual(response.status_code, 404)

    def test_legacy_qr_endpoints_are_not_registered(self):
        product = Product.objects.create(sku='QR-011', name='Produit QR')
        location = InventoryLocation.objects.create(name='Boutique QR', code='QR-LOC-01', location_type='shop')
        location.authorized_users.add(self.user)
        StockItem.objects.create(product=product, location=location, quantity=6)
        carton = Carton.objects.create(
            product=product,
            location=location,
            reference='CTN-QR-011',
            quantity=2,
            items_per_carton=1,
        )

        product_qr = self.client.get(f'/api/v1/products/{product.id}/qr/')
        carton_qr = self.client.get(f'/api/v1/cartons/{carton.id}/qr/')
        resolved = self.client.get('/api/v1/qr/resolve/', {'code': carton.qr_code})

        self.assertEqual(product_qr.status_code, 404)
        self.assertEqual(carton_qr.status_code, 404)
        self.assertEqual(resolved.status_code, 404)

    def test_legacy_qr_resolution_route_is_not_registered(self):
        product = Product.objects.create(
            sku='QR-SELL-001',
            name='Filtre Toyota',
            barcode='1234567890123',
            selling_price='45000',
            quantity=8,
        )
        location = InventoryLocation.objects.create(name='Boutique vente', code='QR-SELL-SHOP', location_type='shop')
        location.authorized_users.add(self.user)
        StockItem.objects.create(product=product, location=location, quantity=5)

        for code in (product.qr_code, product.sku, product.barcode):
            with self.subTest(code=code):
                response = self.client.get('/api/v1/qr/resolve/', {'code': code})
                self.assertEqual(response.status_code, 404)

    def test_legacy_sample_qr_resolution_route_is_not_registered(self):
        location = InventoryLocation.objects.create(name='Stock échantillon', code='SAMPLE-LOC')
        location.authorized_users.add(self.user)
        StockItem.objects.create(product=self.product, location=location, quantity=7)

        response = self.client.get('/api/v1/qr/resolve/', {'code': self.product.sample_qr_code})

        self.assertEqual(response.status_code, 404)

    def test_legacy_sample_carton_records_are_readable_but_not_created(self):
        shop = InventoryLocation.objects.create(
            name='Boutique échantillons',
            code='SAMPLE-SHOP',
            location_type='shop',
        )
        shop.authorized_users.add(self.user)
        legacy_sample = SampleCarton.objects.create(
            product=self.product,
            location=shop,
            reference='SAMPLE-LEGACY-001',
            sample_count=24,
            qr_code='SAMPLE-LEGACY-QR-001',
        )

        listed = self.client.get('/api/v1/inventory/sample-cartons/')
        self.assertEqual(listed.status_code, 200)
        legacy_rows = listed.data.get('results', []) if isinstance(listed.data, dict) else listed.data
        self.assertTrue(any(row['id'] == legacy_sample.id for row in legacy_rows))
        rejected = self.client.post(
            '/api/v1/inventory/sample-cartons/',
            {'product': self.product.id, 'location': shop.id, 'sample_count': 24},
            format='json',
        )

        self.assertEqual(rejected.status_code, 405)
        self.assertEqual(SampleCarton.objects.count(), 1)
        self.assertFalse(StockItem.objects.filter(product=self.product).exists())

    def test_individual_unit_status_update_stock(self):
        location = InventoryLocation.objects.create(
            name='Magasin traçabilité',
            code='UNIT-TRACE-WH',
            location_type='warehouse',
        )
        location.authorized_users.add(self.user)
        self.product.quantity = 2
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=location, quantity=2)
        carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='CT-UNIT-TRACE',
            quantity=2,
            initial_quantity=2,
            items_per_carton=2,
        )
        unit = StockUnit.objects.create(
            carton=carton,
            location=location,
            unit_number=1,
            reference='U-UNIT-TRACE-0001',
            qr_code='KAP-UNIT-TRACE-0001',
        )

        sampled = self.client.post(
            f'/api/v1/inventory/units/{unit.id}/status/',
            {'status': 'sample'},
            format='json',
        )

        self.assertEqual(sampled.status_code, 200, sampled.data)
        unit.refresh_from_db()
        carton.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(unit.status, 'sample')
        self.assertEqual(carton.quantity, 1)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 1)
        self.assertEqual(self.product.quantity, 1)
        stock = self.client.get('/api/v1/inventory/stock/')
        stock_rows = stock.data.get('results', []) if isinstance(stock.data, dict) else stock.data
        stock_row = next(row for row in stock_rows if row['location'] == location.id)
        self.assertEqual(stock_row['quantity'], 1)
        self.assertEqual(stock_row['sample_quantity'], 1)
        self.assertEqual(stock_row['physical_quantity'], 2)
        self.assertNotIn('qr_code', sampled.data)
        returned = self.client.post(
            f'/api/v1/inventory/units/{unit.id}/status/',
            {'status': 'available'},
            format='json',
        )
        self.assertEqual(returned.status_code, 200, returned.data)
        carton.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(carton.quantity, 2)
        self.assertEqual(self.product.quantity, 2)
        self.assertEqual(StockMovement.objects.filter(reference=unit.reference).count(), 2)
        stock = self.client.get('/api/v1/inventory/stock/')
        stock_rows = stock.data.get('results', []) if isinstance(stock.data, dict) else stock.data
        stock_row = next(row for row in stock_rows if row['location'] == location.id)
        self.assertEqual(stock_row['sample_quantity'], 0)
        self.assertEqual(stock_row['physical_quantity'], 2)

    def test_legacy_sample_carton_endpoint_cannot_create_data(self):
        other_manager = User.objects.create_user(
            username='other_sample_manager',
            password='secret123',
            role='stock',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique non autorisée',
            code='SAMPLE-PRIVATE-SHOP',
            location_type='shop',
        )
        shop.authorized_users.add(other_manager)

        response = self.client.post(
            '/api/v1/inventory/sample-cartons/',
            {'product': self.product.id, 'location': shop.id, 'sample_count': 12},
            format='json',
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(SampleCarton.objects.exists())

        seller = User.objects.create_user(
            username='sample_label_seller',
            password='secret123',
            role='sales',
        )
        seller_client = APIClient()
        seller_client.force_authenticate(user=seller)
        response = seller_client.post(
            '/api/v1/inventory/sample-cartons/',
            {'product': self.product.id, 'location': shop.id, 'sample_count': 12},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SampleCarton.objects.exists())

    def test_stock_unit_initialization_and_list_are_location_scoped(self):
        shop = InventoryLocation.objects.create(
            name='Boutique unités',
            code='UNIT-INIT-SHOP',
            location_type='shop',
        )
        shop.authorized_users.add(self.user)
        self.product.quantity = 2
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=shop, quantity=2)
        Carton.objects.create(
            product=self.product,
            location=shop,
            reference='CT-UNIT-INIT',
            quantity=2,
            initial_quantity=4,
            items_per_carton=4,
        )

        initialized = self.client.post(
            '/api/v1/inventory/units/initialize/',
            {'product': self.product.id, 'location': shop.id},
            format='json',
        )
        self.assertEqual(initialized.status_code, 200, initialized.data)
        self.assertEqual(initialized.data['created_count'], 4)
        self.assertEqual(initialized.data['untracked_saleable_quantity'], 0)
        carton = Carton.objects.get(reference='CT-UNIT-INIT')
        units = self.client.get(
            '/api/v1/inventory/units/',
            {'product': self.product.id, 'location': shop.id},
        )
        self.assertEqual(units.status_code, 200, units.data)
        unit_rows = units.data.get('results', []) if isinstance(units.data, dict) else units.data
        self.assertEqual(len(unit_rows), 4)
        self.assertEqual(
            [unit['status'] for unit in unit_rows],
            ['historical_unknown', 'historical_unknown', 'available', 'available'],
        )
        self.assertTrue(all(unit['carton_reference'] == carton.reference for unit in unit_rows))
        self.assertTrue(all('qr_code' not in unit for unit in unit_rows))

        missing_filters = self.client.get('/api/v1/inventory/units/')
        self.assertEqual(missing_filters.status_code, 400)
        foreign = InventoryLocation.objects.create(
            name='Boutique privée unités',
            code='UNIT-PRIVATE-SHOP',
            location_type='shop',
        )
        self.assertEqual(
            self.client.get(
                '/api/v1/inventory/units/',
                {'product': self.product.id, 'location': foreign.id},
            ).status_code,
            404,
        )

    def test_manual_carton_creation_registers_units_without_qr_exposure(self):
        location = InventoryLocation.objects.create(
            name='Boutique nouveau carton',
            code='UNIT-CARTON-CREATE',
            location_type='shop',
        )
        location.authorized_users.add(self.user)
        self.product.quantity = 3
        self.product.save(update_fields=['quantity'])
        stock_item = StockItem.objects.create(product=self.product, location=location, quantity=3)
        created = self.client.post(
            '/api/v1/inventory/cartons/',
            {
                'product': self.product.id,
                'location': location.id,
                'reference': 'UNIT-CARTON-CREATE-001',
                'quantity': 3,
                'items_per_carton': 3,
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        stock_item.refresh_from_db()
        self.assertEqual(stock_item.quantity, 3)
        units = self.client.get(
            '/api/v1/inventory/units/',
            {'product': self.product.id, 'location': location.id},
        )
        self.assertEqual(units.status_code, 200)
        unit_rows = units.data.get('results', []) if isinstance(units.data, dict) else units.data
        self.assertEqual(len(unit_rows), 3)
        self.assertTrue(all(unit['status'] == 'available' for unit in unit_rows))

    def test_carton_movement_history_includes_individual_sample_transitions(self):
        location = InventoryLocation.objects.create(
            name='Entrepôt historique cartons',
            code='CARTON-MOVEMENT-HISTORY',
            location_type='warehouse',
        )
        location.authorized_users.add(self.user)
        self.product.quantity = 1
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=location, quantity=1)
        carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='CTN-MOVEMENT-HISTORY',
            quantity=1,
            initial_quantity=1,
        )
        unit = ensure_carton_units(carton)[0]
        sampled = self.client.post(
            f'/api/v1/inventory/units/{unit.id}/status/',
            {'status': 'sample'},
            format='json',
        )
        self.assertEqual(sampled.status_code, 200, sampled.data)

        history = self.client.get(
            f'/api/v1/inventory/cartons/{carton.id}/movements/',
        )

        self.assertEqual(history.status_code, 200, history.data)
        self.assertEqual(history.data['carton'], carton.reference)
        self.assertEqual(
            [(movement['type'], movement['reference'], movement['quantity'])
             for movement in history.data['movements']],
            [
                ('registration', carton.reference, 1),
                ('sample', unit.reference, 1),
            ],
        )

    def test_manual_carton_reconciliation_cannot_exceed_untracked_local_stock(self):
        location = InventoryLocation.objects.create(
            name='Boutique stock historique',
            code='CARTON-RECONCILE-BOUNDS',
            location_type='shop',
        )
        location.authorized_users.add(self.user)
        StockItem.objects.create(product=self.product, location=location, quantity=2)
        self.product.quantity = 2
        self.product.save(update_fields=['quantity'])

        response = self.client.post(
            '/api/v1/inventory/cartons/',
            {
                'product': self.product.id,
                'location': location.id,
                'reference': 'CTN-RECONCILE-OVER',
                'quantity': 3,
                'items_per_carton': 3,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Carton.objects.filter(reference='CTN-RECONCILE-OVER').exists())

    def test_legacy_qr_resolution_route_is_not_registered_for_sales(self):
        seller = User.objects.create_user(
            username='qr_sales_scope',
            password='secret123',
            role='sales',
        )
        other_user = User.objects.create_user(
            username='qr_other_location_user',
            role='stock',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique QR autorisée',
            code='QR-SALES-SHOP',
            location_type='shop',
        )
        shop.authorized_users.add(seller)
        other_shop = InventoryLocation.objects.create(
            name='Boutique QR privée',
            code='QR-SALES-OTHER-SHOP',
            location_type='shop',
        )
        other_shop.authorized_users.add(other_user)
        warehouse = InventoryLocation.objects.create(
            name='Entrepôt QR privé',
            code='QR-SALES-WAREHOUSE',
            location_type='warehouse',
        )
        warehouse.authorized_users.add(other_user)
        StockItem.objects.create(product=self.product, location=shop, quantity=3)
        StockItem.objects.create(product=self.product, location=other_shop, quantity=7)
        StockItem.objects.create(product=self.product, location=warehouse, quantity=11)
        allowed_carton = Carton.objects.create(
            product=self.product,
            location=shop,
            reference='CTN-QR-ALLOWED',
            quantity=2,
            items_per_carton=1,
        )
        private_carton = Carton.objects.create(
            product=self.product,
            location=warehouse,
            reference='CTN-QR-PRIVATE',
            quantity=2,
            items_per_carton=1,
        )
        self.client.force_authenticate(user=seller)

        product_response = self.client.get('/api/v1/qr/resolve/', {'code': self.product.sku})
        carton_response = self.client.get(
            '/api/v1/qr/resolve/',
            {'code': allowed_carton.qr_code},
        )
        private_carton_response = self.client.get(
            '/api/v1/qr/resolve/',
            {'code': private_carton.qr_code},
        )

        self.assertEqual(product_response.status_code, 404)
        self.assertEqual(carton_response.status_code, 404)
        self.assertEqual(private_carton_response.status_code, 404)

    def test_legacy_qr_resolution_has_no_scanner_data_side_effects(self):
        seller = User.objects.create_user(
            username='qr_sales_read_only',
            password='secret123',
            role='sales',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique scan vendeur',
            code='QR-SALES-READ-ONLY',
            location_type='shop',
        )
        shop.authorized_users.add(seller)
        stock_item = StockItem.objects.create(product=self.product, location=shop, quantity=4)
        carton = Carton.objects.create(
            product=self.product,
            location=shop,
            reference='CTN-QR-READ-ONLY',
            quantity=3,
            supplier_reference='FOURNISSEUR-SECRET',
            supplier_barcode='BARCODE-SECRET',
        )
        client = APIClient()
        client.force_authenticate(user=seller)

        response = client.get('/api/v1/qr/resolve/', {'code': carton.qr_code})

        self.assertEqual(response.status_code, 404)
        carton.refresh_from_db()
        stock_item.refresh_from_db()
        self.assertEqual(carton.quantity, 3)
        self.assertEqual(stock_item.quantity, 4)

    def test_legacy_qr_resolution_route_is_not_registered_anonymously(self):
        response = APIClient().get('/api/v1/qr/resolve/', {'code': self.product.sku})

        self.assertEqual(response.status_code, 404)


class InventoryTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.get(slug='kourouma-auto-parts')
        self.tenant_b = Tenant.objects.create(
            slug='inventory-tenant-b',
            name='Inventaire Tenant B',
            status='active',
        )
        self.user = User.objects.create_user(
            username='inventory_tenant_a_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant_a,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.location_a = self.create_location(
            self.tenant_a,
            'Entrepôt A',
            'INV-TENANT-A',
        )
        self.location_a_shop = self.create_location(
            self.tenant_a,
            'Boutique A',
            'INV-TENANT-A-SHOP',
            location_type='shop',
        )
        self.location_b = self.create_location(
            self.tenant_b,
            'Entrepôt B',
            'INV-TENANT-B',
        )
        self.location_b_shop = self.create_location(
            self.tenant_b,
            'Boutique B',
            'INV-TENANT-B-SHOP',
            location_type='shop',
        )
        self.product_a = self.create_product(
            self.tenant_a,
            'INV-TENANT-A-SKU',
            'Produit inventaire A',
        )
        self.product_b = self.create_product(
            self.tenant_b,
            'INV-TENANT-B-SKU',
            'Produit inventaire B',
        )
        self.stock_a = StockItem.objects.create(
            product=self.product_a,
            location=self.location_a,
            quantity=5,
        )
        self.stock_b = StockItem.objects.create(
            product=self.product_b,
            location=self.location_b,
            quantity=8,
        )
        self.movement_a = StockMovement.objects.create(
            product=self.product_a,
            location=self.location_a,
            movement_type='in',
            quantity=5,
        )
        self.movement_b = StockMovement.objects.create(
            product=self.product_b,
            location=self.location_b,
            movement_type='in',
            quantity=8,
        )
        self.transfer_a = self.create_transfer(
            self.product_a,
            self.location_a,
            self.location_a_shop,
            'TR-INV-TENANT-A',
        )
        self.transfer_b = self.create_transfer(
            self.product_b,
            self.location_b,
            self.location_b_shop,
            'TR-INV-TENANT-B',
        )
        self.replenishment_a = StockReplenishmentRequest.objects.create(
            product=self.product_a,
            shop=self.location_a_shop,
            requested_quantity=2,
            requested_by=self.user,
        )
        self.replenishment_b = StockReplenishmentRequest.objects.create(
            product=self.product_b,
            shop=self.location_b_shop,
            requested_quantity=2,
        )
        self.carton_a = self.create_carton(
            self.product_a,
            self.location_a,
            'CTN-INV-TENANT-A',
        )
        self.carton_b = self.create_carton(
            self.product_b,
            self.location_b,
            'CTN-INV-TENANT-B',
        )
        self.sample_a = SampleCarton.objects.create(
            product=self.product_a,
            location=self.location_a_shop,
            reference='SMP-INV-TENANT-A',
            sample_count=1,
            qr_code='QR-SMP-INV-TENANT-A',
        )
        self.sample_b = SampleCarton.objects.create(
            product=self.product_b,
            location=self.location_b_shop,
            reference='SMP-INV-TENANT-B',
            sample_count=1,
            qr_code='QR-SMP-INV-TENANT-B',
        )
        self.unit_a = self.create_unit(self.carton_a, self.location_a, 'UNIT-INV-A')
        self.unit_b = self.create_unit(self.carton_b, self.location_b, 'UNIT-INV-B')
        self.count_a = self.create_count(self.location_a, 'COUNT-INV-A', self.product_a)
        self.count_b = self.create_count(self.location_b, 'COUNT-INV-B', self.product_b)

    @staticmethod
    def create_location(tenant, name, code, location_type='warehouse'):
        return InventoryLocation.objects.create(
            tenant=tenant,
            name=name,
            code=code,
            location_type=location_type,
        )

    @staticmethod
    def create_product(tenant, sku, name):
        return Product.objects.create(
            tenant=tenant,
            sku=sku,
            name=name,
            quantity=0,
            alert_threshold=10,
        )

    @staticmethod
    def create_transfer(product, source, destination, reference):
        return StockTransfer.objects.create(
            product=product,
            from_location=source,
            to_location=destination,
            quantity=1,
            reference=reference,
            status='requested',
        )

    @staticmethod
    def create_carton(product, location, reference):
        return Carton.objects.create(
            product=product,
            location=location,
            reference=reference,
            quantity=1,
            items_per_carton=1,
        )

    @staticmethod
    def create_unit(carton, location, reference):
        return StockUnit.objects.create(
            carton=carton,
            location=location,
            unit_number=1,
            reference=reference,
            qr_code=f'QR-{reference}',
        )

    @staticmethod
    def create_count(location, number, product):
        count = InventoryCount.objects.create(
            location=location,
            number=number,
        )
        InventoryCountItem.objects.create(
            inventory_count=count,
            product=product,
            theoretical_quantity=1,
            counted_quantity=1,
        )
        return count

    @staticmethod
    def result_ids(response):
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            data = data['results']
        return {item['id'] for item in data}

    def test_inventory_lists_and_reports_are_limited_to_the_assigned_tenant(self):
        locations = self.client.get('/api/inventory/locations/')
        stock = self.client.get('/api/inventory/stock/')
        movements = self.client.get('/api/inventory/movements/')
        transfers = self.client.get('/api/inventory/transfers/')
        replenishments = self.client.get('/api/inventory/replenishment-requests/')
        cartons = self.client.get('/api/inventory/cartons/')
        samples = self.client.get('/api/inventory/sample-cartons/')
        units = self.client.get(
            f'/api/inventory/units/?product={self.product_a.pk}&location={self.location_a.pk}',
        )
        counts = self.client.get('/api/inventory/counts/')
        report = self.client.get('/api/v1/reports/inventory/')

        self.assertEqual(locations.status_code, 200)
        self.assertEqual(stock.status_code, 200)
        self.assertEqual(movements.status_code, 200)
        self.assertEqual(transfers.status_code, 200)
        self.assertEqual(replenishments.status_code, 200)
        self.assertEqual(cartons.status_code, 200)
        self.assertEqual(samples.status_code, 200)
        self.assertEqual(units.status_code, 200)
        self.assertEqual(counts.status_code, 200)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(
            {item['id'] for item in locations.data.get('results', locations.data)},
            {self.location_a.pk, self.location_a_shop.pk},
        )
        self.assertEqual(self.result_ids(stock), {self.stock_a.pk})
        self.assertEqual(self.result_ids(movements), {self.movement_a.pk})
        self.assertEqual(self.result_ids(transfers), {self.transfer_a.pk})
        self.assertEqual(self.result_ids(replenishments), {self.replenishment_a.pk})
        self.assertEqual(self.result_ids(cartons), {self.carton_a.pk})
        self.assertEqual(self.result_ids(samples), {self.sample_a.pk})
        self.assertEqual(self.result_ids(units), {self.unit_a.pk})
        self.assertEqual(self.result_ids(counts), {self.count_a.pk})
        self.assertEqual(
            {item['product_id'] for item in report.data['inventory']},
            {self.product_a.pk},
        )
        self.assertEqual(
            report.data['summary']['total_stock_units'],
            self.stock_a.quantity,
        )

    def test_foreign_inventory_objects_cannot_be_read_or_mutated(self):
        endpoints = [
            f'/api/inventory/locations/{self.location_b.pk}/',
            f'/api/inventory/movements/{self.movement_b.pk}/',
            f'/api/inventory/transfers/{self.transfer_b.pk}/',
            f'/api/inventory/cartons/{self.carton_b.pk}/',
            f'/api/inventory/counts/{self.count_b.pk}/',
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint).status_code, 404)

        self.assertEqual(
            self.client.post(
                f'/api/inventory/transfers/{self.transfer_b.pk}/validate/',
                format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/inventory/replenishment-requests/{self.replenishment_b.pk}/reject/',
                {'reason': 'Hors périmètre'},
                format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/inventory/units/{self.unit_b.pk}/status/',
                {'status': 'sample'},
                format='json',
            ).status_code,
            404,
        )

    def test_inventory_write_paths_reject_cross_tenant_relations_and_assign_location_tenant(self):
        location = self.client.post(
            '/api/inventory/locations/',
            {
                'name': 'Nouvel entrepôt A',
                'code': 'INV-TENANT-A-NEW',
                'location_type': 'warehouse',
            },
            format='json',
        )
        movement = self.client.post(
            '/api/inventory/movements/',
            {
                'product': self.product_b.pk,
                'location': self.location_a.pk,
                'movement_type': 'in',
                'quantity': 1,
            },
            format='json',
        )
        transfer = self.client.post(
            '/api/inventory/transfers/',
            {
                'product': self.product_a.pk,
                'from_location': self.location_a.pk,
                'to_location': self.location_b.pk,
                'quantity': 1,
                'reference': 'TR-CROSS-TENANT',
            },
            format='json',
        )

        self.assertEqual(location.status_code, 201, location.data)
        self.assertEqual(
            InventoryLocation.objects.get(pk=location.data['id']).tenant_id,
            self.tenant_a.pk,
        )
        self.assertEqual(movement.status_code, 400)
        self.assertEqual(transfer.status_code, 400)
        self.assertFalse(
            StockMovement.objects.filter(
                product=self.product_b,
                location=self.location_a,
            ).exists(),
        )
        self.assertFalse(StockTransfer.objects.filter(reference='TR-CROSS-TENANT').exists())
