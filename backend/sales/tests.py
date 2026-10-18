from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Tenant
from customers.models import Customer
from finance.models import FinancialAccount, FinancialTransaction
from inventory.models import Carton, InventoryCostLayer, InventoryLocation, StockItem, StockUnit
from payments.models import CreditLedger, Payment
from products.models import Category, Product
from sales.models import (
    CustomerOrder,
    CustomerOrderItem,
    Invoice,
    Sale,
    SaleItem,
    SaleItemStockOrigin,
    SaleItemTrackedUnit,
    SaleReturnItem,
    SaleReturnQuarantine,
)
from users.models import User


class SaleApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='vente_sales',
            password='secret123',
            pin_code='1234',
            role='sales',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.customer = Customer.objects.create(full_name='Ali Kaba', phone='+224600002000')
        self.product = Product.objects.create(
            sku='SALE-001',
            name='Smartphone X',
            purchase_price='200000',
            selling_price='300000',
            quantity=10,
            alert_threshold=2,
        )
        self.location = InventoryLocation.objects.create(
            name='Boutique de test ventes',
            code='SALE-DEFAULT-SHOP',
            location_type='shop',
        )
        StockItem.objects.create(product=self.product, location=self.location, quantity=10)

    def test_create_sale_and_invoice(self):
        location = InventoryLocation.objects.create(
            name='Boutique facture',
            code='SALE-INVOICE-SHOP',
            location_type='shop',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=10)
        payload = {
            'customer': self.customer.id,
            'location': location.id,
            'status': 'paid',
            'payment_method': 'cash',
            'items': [
                {'product': self.product.id, 'quantity': 2, 'unit_price': '300000.00'}
            ],
        }
        response = self.client.post('/api/sales/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(float(response.data['total_amount']), 600000.0)
        self.assertTrue(response.data['invoice_number'])
        invoice = Invoice.objects.get(sale_id=response.data['id'])
        self.assertEqual(
            invoice.company_name,
            Tenant.objects.get(slug='kourouma-auto-parts').name,
        )

    def test_stock_sale_requires_a_shop_location(self):
        response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [
                    {'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('location', response.data)

    def test_stock_sale_checks_location_quantity_not_only_global_quantity(self):
        location = InventoryLocation.objects.create(
            name='Boutique stock limité',
            code='SALE-LOCAL-LIMIT',
            location_type='shop',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=1)
        response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [
                    {'product': self.product.id, 'quantity': 2, 'unit_price': '300000.00'}
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('quantity', response.data)
        self.assertFalse(SaleItem.objects.exists())

    def test_sale_captures_fifo_cost_at_the_time_of_sale(self):
        self.product.selling_price = Decimal('300.00')
        self.product.save(update_fields=['selling_price'])
        location = InventoryLocation.objects.create(
            name='Boutique FIFO',
            code='SHOP-FIFO-001',
            location_type='shop',
        )
        StockItem.objects.create(
            product=self.product,
            location=location,
            quantity=5,
        )
        first_layer = InventoryCostLayer.objects.create(
            product=self.product,
            location=location,
            source='receipt',
            reference='RECEIPT-FIFO-001',
            quantity_received=2,
            quantity_remaining=2,
            unit_cost=Decimal('100.00'),
        )
        second_layer = InventoryCostLayer.objects.create(
            product=self.product,
            location=location,
            source='receipt',
            reference='RECEIPT-FIFO-002',
            quantity_received=3,
            quantity_remaining=3,
            unit_cost=Decimal('200.00'),
        )

        response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [
                    {'product': self.product.id, 'quantity': 3, 'unit_price': '300.00'},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        item = SaleItem.objects.get(sale_id=response.data['id'])
        self.assertEqual(item.cost_total, Decimal('400.00'))
        self.assertEqual(
            list(item.cost_allocations.values_list('cost_layer_id', 'quantity', 'unit_cost')),
            [(first_layer.id, 2, Decimal('100.00')), (second_layer.id, 1, Decimal('200.00'))],
        )
        first_layer.refresh_from_db()
        second_layer.refresh_from_db()
        self.assertEqual(first_layer.quantity_remaining, 0)
        self.assertEqual(second_layer.quantity_remaining, 2)

    def test_shop_sale_consumes_transferred_units_without_changing_source_carton(self):
        source = InventoryLocation.objects.create(
            name='Magasin principal',
            code='WAREHOUSE-UNIT-SALE',
            location_type='warehouse',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique principale',
            code='SHOP-UNIT-SALE',
            location_type='shop',
        )
        stock_user = User.objects.create_user(
            username='stock_transfer_units',
            password='secret123',
            role='stock',
        )
        admin = User.objects.create_user(
            username='admin_transfer_units',
            password='secret123',
            role='admin',
        )
        source.authorized_users.add(stock_user)
        shop.authorized_users.add(stock_user, self.user)
        self.product.quantity = 5
        self.product.save(update_fields=['quantity'])
        StockItem.objects.create(product=self.product, location=source, quantity=5)
        carton = Carton.objects.create(
            product=self.product,
            location=source,
            reference='CT-UNIT-SALE-001',
            quantity=5,
            initial_quantity=5,
            items_per_carton=5,
        )

        stock_client = APIClient()
        stock_client.force_authenticate(user=stock_user)
        requested = stock_client.post(
            '/api/v1/transfers/',
            {
                'product': self.product.id,
                'from_location': source.id,
                'to_location': shop.id,
                'quantity': 3,
                'reference': 'TR-UNIT-SALE-001',
                'notes': 'Mise en boutique',
            },
            format='json',
        )
        self.assertEqual(requested.status_code, 201, requested.data)
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        transfer_id = requested.data['id']
        self.assertEqual(
            admin_client.post(f'/api/v1/transfers/{transfer_id}/validate/').status_code,
            200,
        )
        self.assertEqual(
            stock_client.post(f'/api/v1/transfers/{transfer_id}/ship/').status_code,
            200,
        )
        self.assertEqual(
            stock_client.post(f'/api/v1/transfers/{transfer_id}/receive/').status_code,
            200,
        )

        sale = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': shop.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [
                    {'product': self.product.id, 'quantity': 2, 'unit_price': '300000.00'},
                ],
            },
            format='json',
        )

        self.assertEqual(sale.status_code, 201, sale.data)
        carton.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(carton.location, source)
        self.assertEqual(carton.quantity, 2)
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=source).quantity,
            2,
        )
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=shop).quantity,
            1,
        )
        self.assertEqual(self.product.quantity, 3)
        self.assertEqual(
            StockUnit.objects.filter(carton=carton, status='sold', location=shop).count(),
            2,
        )
        self.assertEqual(
            StockUnit.objects.filter(carton=carton, status='available', location=shop).count(),
            1,
        )
        sale_item = SaleItem.objects.get(sale_id=sale.data['id'])
        self.assertEqual(SaleItemTrackedUnit.objects.filter(sale_item=sale_item).count(), 2)
        returned = admin_client.post(
            f"/api/sales/{sale.data['id']}/returns/",
            {
                'reason': 'Contrôle des unités retournées',
                'items': [{
                    'sale_item': sale_item.id,
                    'quantity': 2,
                    'restock_quantity': 1,
                    'quarantined_quantity': 1,
                    'quarantine_reason': 'Une pièce nécessite une inspection.',
                }],
            },
            format='json',
        )

        self.assertEqual(returned.status_code, 201, returned.data)
        return_item = SaleReturnItem.objects.get(sale_return_id=returned.data['id'])
        quarantine = return_item.quarantine
        self.assertEqual(
            StockUnit.objects.filter(carton=carton, status='available', location=shop).count(),
            2,
        )
        self.assertEqual(
            StockUnit.objects.filter(carton=carton, status='quarantined', location=shop).count(),
            1,
        )
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=shop).quantity,
            2,
        )
        self.assertEqual(
            admin_client.post(
                f'/api/sales/return-quarantines/{quarantine.id}/release/',
                {'quantity': 1, 'reason': 'Contrôle conforme.'},
                format='json',
            ).status_code,
            200,
        )
        self.assertEqual(
            StockUnit.objects.filter(carton=carton, status='available', location=shop).count(),
            3,
        )
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=shop).quantity,
            3,
        )
        self.assertEqual(StockUnit.objects.filter(carton=carton, status='sold').count(), 0)
        carton.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(carton.location, source)
        self.assertEqual(carton.quantity, 2)
        self.assertEqual(self.product.quantity, 5)

    def test_sale_return_restores_original_fifo_cost_and_revises_sale_period_report(self):
        self.product.selling_price = Decimal('300.00')
        self.product.save(update_fields=['selling_price'])
        location = InventoryLocation.objects.create(
            name='Boutique retour FIFO',
            code='SHOP-RETURN-001',
            location_type='shop',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=5)
        InventoryCostLayer.objects.create(
            product=self.product,
            location=location,
            source='receipt',
            reference='RETURN-FIFO-OLD',
            quantity_received=2,
            quantity_remaining=2,
            unit_cost=Decimal('100.00'),
        )
        InventoryCostLayer.objects.create(
            product=self.product,
            location=location,
            source='receipt',
            reference='RETURN-FIFO-NEW',
            quantity_received=3,
            quantity_remaining=3,
            unit_cost=Decimal('200.00'),
        )
        sale_response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 3, 'unit_price': '300.00'}],
            },
            format='json',
        )
        sale_item = SaleItem.objects.get(sale_id=sale_response.data['id'])

        admin = User.objects.create_user(
            username='admin_retour_fifo',
            password='secret123',
            role='admin',
        )
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        returned = admin_client.post(
            f"/api/sales/{sale_response.data['id']}/returns/",
            {
                'reason': 'Article non utilisé',
                'items': [{
                    'sale_item': sale_item.id,
                    'quantity': 2,
                    'restock_quantity': 2,
                    'quarantined_quantity': 0,
                }],
            },
            format='json',
        )

        self.assertEqual(returned.status_code, 201, returned.data)
        self.assertEqual(returned.data['returned_amount'], Decimal('600.00'))
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 4)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 9)
        return_item = SaleReturnItem.objects.get(sale_return_id=returned.data['id'])
        self.assertEqual(return_item.cost_total, Decimal('200.00'))
        restored_layer = InventoryCostLayer.objects.get(
            source='return',
            reference=f"RETURN-{returned.data['id']}",
        )
        self.assertEqual(restored_layer.quantity_remaining, 2)
        self.assertEqual(restored_layer.unit_cost, Decimal('100.00'))

        report = admin_client.get('/api/core/reports/sales/')
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['summary']['total_sales'], 300.0)
        self.assertEqual(report.data['summary']['returned_amount'], 600.0)
        self.assertEqual(report.data['summary']['returned_quantity'], 2)
        self.assertEqual(report.data['summary']['total_quantity_sold'], 1)
        self.assertEqual(report.data['summary']['total_cost'], 200.0)
        self.assertEqual(report.data['summary']['gross_margin'], 100.0)
        inventory_report = admin_client.get(
            '/api/core/reports/inventory/',
            {'period_days': 30},
        )
        self.assertEqual(inventory_report.status_code, 200)
        self.assertTrue(inventory_report.data['rotation']['returns_separately_tracked'])
        product_rotation = next(
            item for item in inventory_report.data['rotation']['products']
            if item['product_id'] == self.product.id
        )
        self.assertEqual(product_rotation['quantity_sold'], 1)

        invalid_repeat = admin_client.post(
            f"/api/sales/{sale_response.data['id']}/returns/",
            {
                'reason': 'Quantité déjà retournée',
                'items': [{
                    'sale_item': sale_item.id,
                    'quantity': 2,
                    'restock_quantity': 2,
                    'quarantined_quantity': 0,
                }],
            },
            format='json',
        )
        self.assertEqual(invalid_repeat.status_code, 400)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 4)

    def test_returned_damaged_units_stay_quarantined_until_admin_release(self):
        self.product.selling_price = Decimal('300.00')
        self.product.save(update_fields=['selling_price'])
        location = InventoryLocation.objects.create(
            name='Boutique retour isolé',
            code='SHOP-RETURN-Q-001',
            location_type='shop',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=5)
        InventoryCostLayer.objects.create(
            product=self.product,
            location=location,
            source='receipt',
            reference='RETURN-Q-ORIGINAL',
            quantity_received=5,
            quantity_remaining=5,
            unit_cost=Decimal('100.00'),
        )
        sale_response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 2, 'unit_price': '300.00'}],
            },
            format='json',
        )
        self.assertEqual(sale_response.status_code, 201, sale_response.data)
        sale_item = SaleItem.objects.get(sale_id=sale_response.data['id'])

        admin = User.objects.create_user(
            username='admin_retour_dommage',
            password='secret123',
            role='admin',
        )
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        returned = admin_client.post(
            f"/api/sales/{sale_response.data['id']}/returns/",
            {
                'reason': 'Retour avec un article abîmé',
                'items': [{
                    'sale_item': sale_item.id,
                    'quantity': 2,
                    'restock_quantity': 1,
                    'quarantined_quantity': 1,
                    'quarantine_reason': 'Emballage endommagé',
                }],
            },
            format='json',
        )
        self.assertEqual(returned.status_code, 201, returned.data)
        quarantine = SaleReturnQuarantine.objects.get()
        self.assertEqual(quarantine.quantity_remaining, 1)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 4)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 9)
        self.assertFalse(
            InventoryCostLayer.objects.get(
                product=self.product,
                location=location,
                reference__startswith=f'RETURN-{returned.data["id"]}-Q-',
            ).is_available
        )

        denied = self.client.post(
            f'/api/sales/return-quarantines/{quarantine.id}/release/',
            {'quantity': 1, 'reason': 'Contrôle'},
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(user=admin)
        pending = self.client.get(
            f"/api/sales/{sale_response.data['id']}/returns/quarantines/",
        )
        self.assertEqual(pending.status_code, 200, pending.data)
        self.assertEqual(len(pending.data), 1)
        self.assertEqual(pending.data[0]['quantity_remaining'], 1)
        released = self.client.post(
            f'/api/sales/return-quarantines/{quarantine.id}/release/',
            {'quantity': 1, 'reason': 'Article contrôlé et conforme'},
            format='json',
        )
        self.assertEqual(released.status_code, 200, released.data)
        self.assertEqual(released.data['quantity_remaining'], 0)
        self.assertEqual(released.data['status'], 'resolved')
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 5)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_sales_user_cannot_register_a_sale_return(self):
        sale_response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
            },
            format='json',
        )
        sale_item = SaleItem.objects.get(sale_id=sale_response.data['id'])
        sales_user = User.objects.create_user(
            username='vendeur_retour',
            password='secret123',
            role='sales',
        )
        self.client.force_authenticate(user=sales_user)

        response = self.client.post(
            f"/api/sales/{sale_response.data['id']}/returns/",
            {'items': [{'sale_item': sale_item.id, 'quantity': 1}]},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_sales_catalog_search_is_server_side_and_requires_a_query(self):
        extra = Product.objects.create(
            sku='SALE-SEARCH-BARCODE',
            name='Pompe hydraulique',
            barcode='BARCODE-POMPE-001',
            selling_price='72000',
        )

        empty = self.client.get('/api/v1/sales/catalog/')
        by_name = self.client.get('/api/v1/sales/catalog/', {'search': 'hydraulique'})
        by_sku = self.client.get('/api/v1/sales/catalog/', {'search': extra.sku})
        by_barcode = self.client.get('/api/v1/sales/catalog/', {'search': 'BARCODE-POMPE-001'})

        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data['results'], [])
        self.assertEqual([item['id'] for item in by_name.data['results']], [extra.id])
        self.assertEqual([item['id'] for item in by_sku.data['results']], [extra.id])
        self.assertEqual([item['id'] for item in by_barcode.data['results']], [extra.id])
        self.assertFalse(SaleReturnItem.objects.exists())

    def test_sales_catalog_searches_alternative_references_and_paginates_with_filters(self):
        category = Category.objects.create(name='Filtres')
        location = InventoryLocation.objects.create(
            name='Boutique catalogue',
            code='SHOP-CATALOG-PAGE',
            location_type='shop',
        )
        product = Product.objects.create(
            sku='SALE-ALT-REF',
            name='Filtre carburant',
            category=category,
            alternative_references='OEM-7788\nREF-ALT-99',
            selling_price='50000',
        )
        StockItem.objects.create(product=product, location=location, quantity=3)
        for index in range(30):
            Product.objects.create(
                sku=f'SALE-PAGE-{index:02d}',
                name=f'Filtre page {index:02d}',
                category=category,
            )

        first_page = self.client.get('/api/v1/sales/catalog/', {
            'search': 'OEM-7788',
            'category': category.id,
            'available': 'true',
            'page_size': 1,
        })
        second_page = self.client.get('/api/v1/sales/catalog/', {
            'search': 'filtre',
            'category': category.id,
            'page': 2,
            'page_size': 10,
        })

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.data['count'], 1)
        self.assertEqual(first_page.data['results'][0]['id'], product.id)
        self.assertNotIn('purchase_price', first_page.data['results'][0])
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.data['results']), 10)
        self.assertIsNotNone(second_page.data['previous'])

    def test_sales_users_can_only_view_their_own_sales(self):
        other_seller = User.objects.create_user(
            username='autre_vendeur',
            password='secret123',
            role='sales',
        )
        own_sale = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
            },
            format='json',
        )
        self.assertEqual(own_sale.status_code, 201)
        admin = User.objects.create_user(
            username='admin_sales_scope',
            password='secret123',
            role='admin',
        )
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        other_sale = admin_client.post(
            '/api/sales/',
            {
                'seller': other_seller.id,
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
            },
            format='json',
        )
        self.assertEqual(other_sale.status_code, 201)

        self.client.force_authenticate(user=other_seller)
        listed = self.client.get('/api/sales/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            {item['id'] for item in listed.data['results']},
            {other_sale.data['id']},
        )
        self.assertEqual(self.client.get(f"/api/sales/{own_sale.data['id']}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/sales/{other_sale.data['id']}/").status_code, 200)

    def test_sales_user_cannot_impersonate_another_seller_or_read_costs(self):
        sales_user = User.objects.create_user(
            username='vendeur_isole',
            password='secret123',
            role='sales',
        )
        self.client.force_authenticate(user=sales_user)

        response = self.client.post(
            '/api/v1/sales/',
            {
                'seller': self.user.id,
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['seller'], sales_user.id)
        self.assertNotIn('product_cost', response.data['items'][0])

    def test_sales_catalog_does_not_expose_cost_or_inventory_mutations(self):
        sales_user = User.objects.create_user(
            username='vendeur_catalogue',
            password='secret123',
            role='sales',
        )
        self.client.force_authenticate(user=sales_user)

        catalog = self.client.get('/api/v1/sales/catalog/', {'search': self.product.name})
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.data['results'][0]['id'], self.product.id)
        self.assertNotIn('cost_price', catalog.data['results'][0])
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)
        self.assertEqual(self.client.get('/api/v1/inventory/').status_code, 403)

    def test_sales_user_cannot_submit_a_stale_or_modified_price(self):
        response = self.client.post(
            '/api/v1/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{
                    'product': self.product.id,
                    'quantity': 1,
                    'unit_price': '1.00',
                }],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('unit_price', response.data)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_sales_user_cannot_apply_a_discount(self):
        response = self.client.post(
            '/api/v1/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'discount': '1.00',
                'items': [{
                    'product': self.product.id,
                    'quantity': 1,
                    'unit_price': '300000.00',
                }],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('discount', response.data)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_sales_user_cannot_sell_from_an_unauthorized_location(self):
        authorized_shop = InventoryLocation.objects.create(
            name='Boutique autorisée du vendeur',
            code='SHOP-SALES-AUTHORIZED',
            location_type='shop',
        )
        authorized_shop.authorized_users.add(self.user)
        unauthorized_shop = InventoryLocation.objects.create(
            name='Boutique non autorisée du vendeur',
            code='SHOP-SALES-UNAUTHORIZED',
            location_type='shop',
        )
        authorized_stock = StockItem.objects.create(
            product=self.product,
            location=authorized_shop,
            quantity=4,
        )
        unauthorized_stock = StockItem.objects.create(
            product=self.product,
            location=unauthorized_shop,
            quantity=5,
        )

        response = self.client.post(
            '/api/v1/sales/',
            {
                'customer': self.customer.id,
                'location': unauthorized_shop.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{
                    'product': self.product.id,
                    'quantity': 1,
                    'unit_price': '300000.00',
                }],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('location', response.data)
        authorized_stock.refresh_from_db()
        unauthorized_stock.refresh_from_db()
        self.assertEqual(authorized_stock.quantity, 4)
        self.assertEqual(unauthorized_stock.quantity, 5)
        self.assertEqual(SaleItem.objects.count(), 0)

    def test_sales_catalog_limits_stock_to_authorized_shop(self):
        sales_user = User.objects.create_user(
            username='vendeur_boutique',
            password='secret123',
            role='sales',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique autorisée',
            code='SHOP-SALES-001',
            location_type='shop',
        )
        shop.authorized_users.add(sales_user)
        other_shop = InventoryLocation.objects.create(
            name='Boutique non autorisée',
            code='SHOP-SALES-002',
            location_type='shop',
        )
        warehouse = InventoryLocation.objects.create(
            name='Entrepôt',
            code='WAREHOUSE-SALES-001',
            location_type='warehouse',
        )
        StockItem.objects.create(product=self.product, location=shop, quantity=4)
        StockItem.objects.create(product=self.product, location=other_shop, quantity=7)
        StockItem.objects.create(product=self.product, location=warehouse, quantity=9)
        self.product.quantity = 8
        self.product.save(update_fields=['quantity'])

        self.client.force_authenticate(user=sales_user)
        catalog = self.client.get('/api/v1/sales/catalog/', {'search': self.product.name})

        self.assertEqual(catalog.status_code, 200)
        product = next(item for item in catalog.data['results'] if item['id'] == self.product.id)
        self.assertEqual(product['quantity'], 4)
        self.assertEqual(
            product['stock_by_location'],
            [{'location_id': shop.id, 'location': shop.name, 'quantity': 4}],
        )
        self.assertEqual(
            [location['id'] for location in self.client.get('/api/v1/sales/locations/').data],
            [shop.id],
        )

    def test_credit_sale_requires_a_customer_and_creates_receivable(self):
        payload = {
            'location': self.location.id,
            'status': 'partial',
            'payment_method': 'credit',
            'amount_paid': '100000.00',
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
        }
        missing_customer = self.client.post('/api/sales/', payload, format='json')
        self.assertEqual(missing_customer.status_code, 400)
        self.assertIn('customer', missing_customer.data)

        response = self.client.post(
            '/api/sales/',
            {**payload, 'customer': self.customer.id},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        sale_id = response.data['id']
        ledger = CreditLedger.objects.get(sale_id=sale_id)
        self.assertEqual(ledger.balance, Decimal('200000.00'))
        self.assertEqual(Payment.objects.filter(sale_id=sale_id).count(), 1)
        self.assertTrue(response.data['invoice_number'])

    def test_credit_sale_rejects_customer_without_whatsapp_phone(self):
        customer_without_phone = Customer.objects.create(full_name='Client sans téléphone')
        response = self.client.post(
            '/api/sales/',
            {
                'customer': customer_without_phone.id,
                'location': self.location.id,
                'status': 'partial',
                'payment_method': 'credit',
                'amount_paid': '0.00',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('customer', response.data)

    def test_cash_sale_creates_finance_receipt_on_selected_account(self):
        account = FinancialAccount.objects.create(name='Caisse ventes', account_type='cash')
        payload = {
            'customer': self.customer.id,
            'location': self.location.id,
            'status': 'paid',
            'payment_method': 'cash',
            'financial_account': account.id,
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
        }
        response = self.client.post('/api/sales/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get(sale_id=response.data['id'])
        transaction = FinancialTransaction.objects.get(origin=f"payment:{payment.id}")
        self.assertEqual(transaction.account_id, account.id)
        self.assertEqual(transaction.amount, Decimal('300000.00'))

    def test_sale_rejects_unavailable_stock(self):
        self.product.quantity = 1
        self.product.save()

        response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 2, 'unit_price': '300000.00'}],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('quantity', response.data)

    def test_sale_accepts_more_than_25_invoice_lines_for_pdf_pagination(self):
        products = [
            Product.objects.create(
                sku=f'MULTI-{index:02d}',
                name=f'Produit facture {index}',
                brand='KAP',
                purchase_price='1.00',
                selling_price='2.00',
                quantity=2,
                alert_threshold=1,
            )
            for index in range(26)
        ]
        StockItem.objects.bulk_create([
            StockItem(product=product, location=self.location, quantity=2)
            for product in products
        ])
        payload = {
            'customer': self.customer.id,
            'location': self.location.id,
            'status': 'paid',
            'payment_method': 'cash',
            'items': [
                {'product': product.id, 'quantity': 1, 'unit_price': '2.00'}
                for product in products
            ],
        }

        response = self.client.post('/api/sales/', payload, format='json')

        self.assertEqual(response.status_code, 201)

    def test_invoice_generates_qr_code_when_missing(self):
        payload = {
            'customer': self.customer.id,
            'location': self.location.id,
            'status': 'paid',
            'payment_method': 'cash',
            'items': [
                {'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}
            ],
        }

        response = self.client.post('/api/sales/', payload, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['invoice_number'])
        sale = self.client.get(f"/api/sales/{response.data['id']}/")
        self.assertTrue(sale.data['invoice_qr_code'])
        self.assertTrue(sale.data['invoice_qr_code'].startswith('KAP-FAC-'))

    def test_external_sale_endpoint_forces_external_flag(self):
        from suppliers.models import Supplier

        supplier = Supplier.objects.create(name='Fournisseur externe')
        cost_layer = InventoryCostLayer.objects.create(
            product=self.product,
            location=self.location,
            source='receipt',
            reference='EXTERNAL-SALE-MUST-NOT-CONSUME',
            quantity_received=10,
            quantity_remaining=10,
            unit_cost=Decimal('100.00'),
        )
        response = self.client.post(
            '/api/v1/sales/external/',
            {
                'customer': self.customer.id,
                'external_supplier': supplier.id,
                'external_reference': 'EXT-001',
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['is_external'])
        self.product.refresh_from_db()
        cost_layer.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)
        self.assertEqual(StockItem.objects.get(product=self.product, location=self.location).quantity, 10)
        self.assertEqual(cost_layer.quantity_remaining, 10)
        sale_item = SaleItem.objects.get(sale_id=response.data['id'])
        self.assertFalse(sale_item.cost_allocations.exists())
        self.assertEqual(
            response.data['items'][0]['stock_origins'],
            [{
                'source_type': 'external_supplier',
                'reference': 'EXT-001',
                'quantity': 1,
                'carton_reference': None,
                'location': None,
                'supplier': 'Fournisseur externe',
            }],
        )
        self.assertEqual(response.data['items'][0]['stock_removed_quantity'], 0)

    def test_sale_with_location_decrements_location_stock(self):
        from inventory.models import InventoryLocation, StockItem

        location = InventoryLocation.objects.create(
            name='Boutique vente',
            code='SALE-LOCATION',
            location_type='shop',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=3)

        response = self.client.post(
            '/api/v1/sales/',
            {
                'customer': self.customer.id,
                'location': location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 2, 'unit_price': '300000.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 1)
        origin = SaleItemStockOrigin.objects.get(sale_item__sale_id=response.data['id'])
        self.assertEqual(origin.source_type, 'historical_unknown')
        self.assertEqual(origin.quantity, 2)

    def test_sale_consumes_tracked_cartons_fifo_at_the_sale_location(self):
        location = InventoryLocation.objects.create(
            name='Boutique cartons FIFO',
            code='SALE-CARTON-FIFO',
            location_type='shop',
        )
        location.authorized_users.add(self.user)
        other_location = InventoryLocation.objects.create(
            name='Entrepôt cartons FIFO',
            code='SALE-CARTON-OTHER',
            location_type='warehouse',
        )
        StockItem.objects.create(product=self.product, location=location, quantity=8)
        oldest = Carton.objects.create(
            product=self.product,
            location=location,
            reference='SALE-CARTON-001',
            quantity=3,
            items_per_carton=3,
        )
        next_carton = Carton.objects.create(
            product=self.product,
            location=location,
            reference='SALE-CARTON-002',
            quantity=4,
            items_per_carton=4,
        )
        other_carton = Carton.objects.create(
            product=self.product,
            location=other_location,
            reference='SALE-CARTON-003',
            quantity=2,
            items_per_carton=2,
        )

        response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 5, 'unit_price': '300000.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        oldest.refresh_from_db()
        next_carton.refresh_from_db()
        other_carton.refresh_from_db()
        self.assertEqual(oldest.quantity, 0)
        self.assertEqual(next_carton.quantity, 2)
        self.assertEqual(other_carton.quantity, 2)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 3)
        sale_item = SaleItem.objects.get(sale_id=response.data['id'])
        self.assertEqual(
            list(sale_item.stock_origins.order_by('reference').values_list('reference', 'quantity')),
            [('SALE-CARTON-001', 3), ('SALE-CARTON-002', 2)],
        )
        self.assertEqual(sale_item.tracked_unit_allocations.count(), 5)
        detail = self.client.get(f"/api/sales/{response.data['id']}/")
        self.assertEqual(
            [(origin['carton_reference'], origin['quantity'])
             for origin in detail.data['items'][0]['stock_origins']],
            [('SALE-CARTON-001', 3), ('SALE-CARTON-002', 2)],
        )
        self.assertEqual(
            len(detail.data['items'][0]['tracked_unit_references']),
            5,
        )

    def test_sale_delete_is_rejected(self):
        response = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
            },
            format='json',
        )

        delete_response = self.client.delete(f"/api/sales/{response.data['id']}/")
        self.assertEqual(delete_response.status_code, 405)

    def test_sale_idempotency_replays_same_response(self):
        payload = {
            'customer': self.customer.id,
            'location': self.location.id,
            'status': 'paid',
            'payment_method': 'cash',
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '300000.00'}],
        }
        first = self.client.post('/api/v1/sales/', payload, format='json', HTTP_IDEMPOTENCY_KEY='SALE-ONCE-001')
        second = self.client.post('/api/v1/sales/', payload, format='json', HTTP_IDEMPOTENCY_KEY='SALE-ONCE-001')

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data['id'], first.data['id'])


class CustomerOrderApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='customer_order_sales',
            password='secret123',
            role='sales',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.customer = Customer.objects.create(
            full_name='Client devis',
            phone='+224600009999',
        )
        self.product = Product.objects.create(
            sku='ORDER-001',
            name='Filtre à huile',
            purchase_price='100',
            selling_price='300',
            quantity=10,
        )
        self.location = InventoryLocation.objects.create(
            name='Boutique commandes',
            code='CUSTOMER-ORDER-SHOP',
            location_type='shop',
        )
        self.location.authorized_users.add(self.user)
        StockItem.objects.create(
            product=self.product,
            location=self.location,
            quantity=10,
        )

    def create_order(self, quantity=3):
        response = self.client.post(
            '/api/sales/customer-orders/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'items': [{
                    'product': self.product.id,
                    'quantity': quantity,
                    'unit_price': '300.00',
                }],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_quote_does_not_reserve_stock(self):
        order = self.create_order(quantity=8)
        self.assertEqual(order['status'], 'quote')

        sale = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{
                    'product': self.product.id,
                    'quantity': 5,
                    'unit_price': '300.00',
                }],
            },
            format='json',
        )
        self.assertEqual(sale.status_code, 201, sale.data)

    def test_customer_order_list_filters_confirmed_reservations(self):
        confirmed_order = self.create_order(quantity=2)
        quote_order = self.create_order(quantity=1)
        confirmation = self.client.post(
            f"/api/sales/customer-orders/{confirmed_order['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(confirmation.status_code, 200, confirmation.data)

        response = self.client.get(
            '/api/sales/customer-orders/',
            {'status': 'confirmed'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], confirmed_order['id'])
        self.assertNotEqual(response.data['results'][0]['id'], quote_order['id'])

        invalid_filter = self.client.get(
            '/api/sales/customer-orders/',
            {'status': 'unknown'},
        )
        self.assertEqual(invalid_filter.status_code, 400)

    def test_confirmed_order_reserves_stock_from_regular_sales(self):
        order = self.create_order(quantity=8)
        confirmation = self.client.post(
            f"/api/sales/customer-orders/{order['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(confirmation.status_code, 200, confirmation.data)
        self.assertEqual(confirmation.data['status'], 'confirmed')
        catalog = self.client.get(
            '/api/sales/catalog/',
            {'search': 'ORDER-001', 'available': 'true'},
        )
        self.assertEqual(catalog.status_code, 200, catalog.data)
        self.assertEqual(catalog.data['results'][0]['quantity'], 2)
        self.assertEqual(catalog.data['results'][0]['stock_by_location'][0]['quantity'], 2)

        sale = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{
                    'product': self.product.id,
                    'quantity': 3,
                    'unit_price': '300.00',
                }],
            },
            format='json',
        )
        self.assertEqual(sale.status_code, 400)
        self.assertFalse(SaleItem.objects.exists())

    def test_cancelled_order_releases_reservation(self):
        order = self.create_order(quantity=8)
        self.assertEqual(
            self.client.post(
                f"/api/sales/customer-orders/{order['id']}/confirm/",
                {},
                format='json',
            ).status_code,
            200,
        )
        cancelled = self.client.post(
            f"/api/sales/customer-orders/{order['id']}/cancel/",
            {},
            format='json',
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.assertEqual(cancelled.data['status'], 'cancelled')

        sale = self.client.post(
            '/api/sales/',
            {
                'customer': self.customer.id,
                'location': self.location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{
                    'product': self.product.id,
                    'quantity': 10,
                    'unit_price': '300.00',
                }],
            },
            format='json',
        )
        self.assertEqual(sale.status_code, 201, sale.data)

    def test_delivery_creates_one_sale_and_invoice_and_cannot_repeat(self):
        order = self.create_order(quantity=3)
        self.assertEqual(
            self.client.post(
                f"/api/sales/customer-orders/{order['id']}/confirm/",
                {},
                format='json',
            ).status_code,
            200,
        )

        delivered = self.client.post(
            f"/api/sales/customer-orders/{order['id']}/deliver/",
            {},
            format='json',
        )
        self.assertEqual(delivered.status_code, 200, delivered.data)
        self.assertEqual(delivered.data['status'], 'delivered')
        self.assertIsNotNone(delivered.data['sale_id'])
        self.assertTrue(Invoice.objects.filter(sale_id=delivered.data['sale_id']).exists())
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=self.location).quantity,
            7,
        )

        repeated = self.client.post(
            f"/api/sales/customer-orders/{order['id']}/deliver/",
            {},
            format='json',
        )
        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(Invoice.objects.filter(sale__customer_order__id=order['id']).count(), 1)

    def test_cannot_confirm_order_when_stock_is_insufficient(self):
        order = self.create_order(quantity=11)
        response = self.client.post(
            f"/api/sales/customer-orders/{order['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            CustomerOrder.objects.get(pk=order['id']).status,
            'quote',
        )

    def test_salesperson_cannot_read_another_salespersons_order(self):
        order = self.create_order()
        another_seller = User.objects.create_user(
            username='another_order_sales',
            password='secret123',
            role='sales',
        )
        other_client = APIClient()
        other_client.force_authenticate(user=another_seller)
        response = other_client.get(f"/api/sales/customer-orders/{order['id']}/")
        self.assertEqual(response.status_code, 404)


class SalesTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            slug='sales-tenant-a',
            name='Ventes Tenant A',
        )
        self.tenant_b = Tenant.objects.create(
            slug='sales-tenant-b',
            name='Ventes Tenant B',
        )
        self.user_a = User.objects.create_user(
            username='sales_tenant_a_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant_a,
        )
        self.user_b = User.objects.create_user(
            username='sales_tenant_b_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant_b,
        )
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        self.customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            full_name='Client ventes A',
            phone='+224600001011',
        )
        self.customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            full_name='Client ventes B',
            phone='+224600001012',
        )
        self.product_a = Product.objects.create(
            tenant=self.tenant_a,
            sku='SALES-TENANT-A',
            name='Produit ventes A',
            selling_price='20.00',
            quantity=5,
        )
        self.product_b = Product.objects.create(
            tenant=self.tenant_b,
            sku='SALES-TENANT-B',
            name='Produit ventes B',
            selling_price='30.00',
            quantity=5,
        )
        self.location_a = InventoryLocation.objects.create(
            tenant=self.tenant_a,
            name='Boutique ventes A',
            code='SALES-TENANT-A-SHOP',
            location_type='shop',
        )
        self.location_b = InventoryLocation.objects.create(
            tenant=self.tenant_b,
            name='Boutique ventes B',
            code='SALES-TENANT-B-SHOP',
            location_type='shop',
        )
        StockItem.objects.create(
            product=self.product_a,
            location=self.location_a,
            quantity=5,
        )
        StockItem.objects.create(
            product=self.product_b,
            location=self.location_b,
            quantity=5,
        )

        self.sale_a = Sale.objects.create(
            tenant=self.tenant_a,
            customer=self.customer_a,
            seller=self.user_a,
            location=self.location_a,
            status='paid',
            total_amount=Decimal('20.00'),
        )
        SaleItem.objects.create(
            sale=self.sale_a,
            product=self.product_a,
            quantity=1,
            unit_price=Decimal('20.00'),
        )
        self.sale_b = Sale.objects.create(
            tenant=self.tenant_b,
            customer=self.customer_b,
            seller=self.user_b,
            location=self.location_b,
            status='paid',
            total_amount=Decimal('30.00'),
        )
        SaleItem.objects.create(
            sale=self.sale_b,
            product=self.product_b,
            quantity=1,
            unit_price=Decimal('30.00'),
        )
        self.order_a = CustomerOrder.objects.create(
            tenant=self.tenant_a,
            customer=self.customer_a,
            location=self.location_a,
            created_by=self.user_a,
        )
        CustomerOrderItem.objects.create(
            order=self.order_a,
            product=self.product_a,
            quantity=1,
            unit_price=Decimal('20.00'),
        )
        self.order_b = CustomerOrder.objects.create(
            tenant=self.tenant_b,
            customer=self.customer_b,
            location=self.location_b,
            created_by=self.user_b,
        )
        CustomerOrderItem.objects.create(
            order=self.order_b,
            product=self.product_b,
            quantity=1,
            unit_price=Decimal('30.00'),
        )

    @staticmethod
    def response_ids(response):
        data = response.data.get('results', response.data)
        return {item['id'] for item in data}

    def test_sales_and_customer_orders_are_visible_only_within_their_tenant(self):
        sales_a = self.client_a.get('/api/sales/')
        orders_a = self.client_a.get('/api/sales/customer-orders/')
        sales_b = self.client_b.get('/api/sales/')
        orders_b = self.client_b.get('/api/sales/customer-orders/')

        self.assertEqual(sales_a.status_code, 200)
        self.assertEqual(orders_a.status_code, 200)
        self.assertEqual(sales_b.status_code, 200)
        self.assertEqual(orders_b.status_code, 200)
        self.assertEqual(self.response_ids(sales_a), {self.sale_a.pk})
        self.assertEqual(self.response_ids(orders_a), {self.order_a.pk})
        self.assertEqual(self.response_ids(sales_b), {self.sale_b.pk})
        self.assertEqual(self.response_ids(orders_b), {self.order_b.pk})
        self.assertEqual(
            self.client_a.get(f'/api/sales/{self.sale_b.pk}/').status_code,
            404,
        )
        self.assertEqual(
            self.client_a.get(
                f'/api/sales/customer-orders/{self.order_b.pk}/',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client_a.post(
                f'/api/sales/customer-orders/{self.order_b.pk}/confirm/',
                {},
                format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client_a.post(
                f'/api/sales/{self.sale_b.pk}/returns/',
                {'items': []},
                format='json',
            ).status_code,
            404,
        )

    def test_sale_and_order_creation_reject_foreign_relations_and_assign_tenant(self):
        cross_tenant_sale = self.client_a.post(
            '/api/sales/',
            {
                'customer': self.customer_a.pk,
                'location': self.location_a.pk,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{
                    'product': self.product_b.pk,
                    'quantity': 1,
                    'unit_price': '30.00',
                }],
            },
            format='json',
        )
        cross_tenant_order = self.client_a.post(
            '/api/sales/customer-orders/',
            {
                'customer': self.customer_b.pk,
                'location': self.location_a.pk,
                'items': [{
                    'product': self.product_a.pk,
                    'quantity': 1,
                    'unit_price': '20.00',
                }],
            },
            format='json',
        )

        self.assertEqual(cross_tenant_sale.status_code, 400)
        self.assertEqual(cross_tenant_order.status_code, 400)
        self.assertEqual(Sale.objects.filter(tenant=self.tenant_a).count(), 1)
        self.assertEqual(CustomerOrder.objects.filter(tenant=self.tenant_a).count(), 1)

        created_order = self.client_a.post(
            '/api/sales/customer-orders/',
            {
                'customer': self.customer_a.pk,
                'location': self.location_a.pk,
                'items': [{
                    'product': self.product_a.pk,
                    'quantity': 1,
                    'unit_price': '20.00',
                }],
            },
            format='json',
        )
        self.assertEqual(created_order.status_code, 201, created_order.data)
        self.assertEqual(
            CustomerOrder.objects.get(pk=created_order.data['id']).tenant_id,
            self.tenant_a.pk,
        )
