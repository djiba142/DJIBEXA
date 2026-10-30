from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import AuditLog
from core.models import Tenant
from inventory.models import InventoryLocation, StockItem
from users.models import User
from .models import Category, Product, ProductCatalogImport


class ProductApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='stock_user',
            password='secret123',
            pin_code='1234',
            role='stock',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.category = Category.objects.create(name='Électronique', description='Produits tech')

    def tearDown(self):
        for record in ProductCatalogImport.objects.all():
            record.source_file.delete(save=False)

    def test_create_product(self):
        payload = {
            'sku': 'PRD-001',
            'name': 'Laptop Pro',
            'category': self.category.id,
            'brand': 'NEXORA',
            'unit': 'piece',
            'purchase_price': '500000',
            'selling_price': '750000',
            'currency': 'GNF',
            'quantity': 0,
            'alert_threshold': 3,
            'barcode': '123456789',
            'qr_code': 'qr-001',
            'image': 'https://example.com/laptop.png',
        }
        response = self.client.post('/api/products/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(response.data['name'], 'Laptop Pro')
        product = Product.objects.get(sku='PRD-001')
        self.assertEqual(product.quantity, 0)
        self.assertFalse(StockItem.objects.filter(product=product).exists())

    def test_stock_user_cannot_set_opening_quantity_when_creating_product(self):
        response = self.client.post(
            '/api/products/',
            {
                'sku': 'PRD-OPENING-001',
                'name': 'Produit avec stock initial',
                'quantity': 12,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('quantity', response.data)
        self.assertFalse(Product.objects.filter(sku='PRD-OPENING-001').exists())
        self.assertFalse(StockItem.objects.exists())

    def test_admin_must_use_inventory_flow_for_opening_quantity(self):
        admin = User.objects.create_user(
            username='admin_product_create',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=admin)

        response = self.client.post(
            '/api/products/',
            {
                'sku': 'PRD-OPENING-ADMIN',
                'name': 'Produit créé par admin',
                'quantity': 12,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('quantity', response.data)
        self.assertFalse(Product.objects.filter(sku='PRD-OPENING-ADMIN').exists())
        self.assertFalse(StockItem.objects.exists())
        self.assertFalse(InventoryLocation.objects.filter(code='WH-DEFAULT').exists())

    def test_list_products(self):
        Product.objects.create(
            sku='PRD-002',
            name='Téléphone X',
            category=self.category,
            purchase_price='250000',
            selling_price='350000',
            quantity=8,
            alert_threshold=2,
        )
        response = self.client.get('/api/products/')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)

    def test_sales_can_read_catalog_and_stock_without_cost_data_or_mutations(self):
        product = Product.objects.create(
            sku='PRD-SALES-001',
            name='Filtre à huile',
            purchase_price='25000',
            cost_price='27000',
            selling_price='42000',
            quantity=6,
        )
        seller = User.objects.create_user(
            username='seller_catalog',
            pin_code='2468',
            role='sales',
        )
        self.client.force_authenticate(user=seller)

        catalog = self.client.get('/api/products/')
        self.assertEqual(catalog.status_code, 200)
        listed = next(item for item in catalog.data if item['id'] == product.id)
        self.assertEqual(listed['selling_price'], '42000.00')
        self.assertNotIn('purchase_price', listed)
        self.assertNotIn('cost_price', listed)
        self.assertNotIn('margin_amount', listed)

        stock = self.client.get(f'/api/products/{product.id}/stock/')
        self.assertEqual(stock.status_code, 200)
        self.assertEqual(stock.data['quantity'], 0)
        changed = self.client.patch(
            f'/api/products/{product.id}/',
            {'selling_price': '1'},
            format='json',
        )
        self.assertEqual(changed.status_code, 403)

    def test_search_product_by_name_or_sku(self):
        Product.objects.create(
            sku='PRD-003',
            name='Casque Bluetooth',
            category=self.category,
            purchase_price='100000',
            selling_price='180000',
            quantity=5,
            alert_threshold=1,
        )
        response = self.client.get('/api/products/?search=Bluetooth')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['name'] == 'Casque Bluetooth' for item in response.data))

    def test_catalog_reads_and_category_links_are_scoped_to_the_user_tenant(self):
        tenant_a = Tenant.objects.get(slug='kourouma-auto-parts')
        tenant_b = Tenant.objects.create(
            slug='catalogue-tenant-b',
            name='Catalogue Tenant B',
            status='active',
        )
        self.user.tenant = tenant_a
        self.user.save(update_fields=['tenant'])
        category_a = Category.objects.create(name='Freinage A', tenant=tenant_a)
        category_b = Category.objects.create(name='Freinage B', tenant=tenant_b)
        product_a = Product.objects.create(
            sku='CATALOG-A-001',
            name='Plaquette A',
            category=category_a,
            tenant=tenant_a,
        )
        product_b = Product.objects.create(
            sku='CATALOG-B-001',
            name='Plaquette B',
            category=category_b,
            tenant=tenant_b,
        )
        user_b = User.objects.create_user(
            username='catalogue_user_b',
            password='secret123',
            role='stock',
            tenant=tenant_b,
        )
        self.client.force_authenticate(user=user_b)
        products_b = self.client.get('/api/products/')
        self.assertEqual(products_b.status_code, 200)
        self.assertEqual([item['id'] for item in products_b.data], [product_b.pk])

        unassigned_user = User.objects.create_user(
            username='catalogue_user_unassigned',
            password='secret123',
            role='stock',
        )
        self.client.force_authenticate(user=unassigned_user)
        unassigned_response = self.client.get('/api/products/')
        self.assertEqual(unassigned_response.status_code, 403)
        self.client.force_authenticate(user=self.user)

        products = self.client.get('/api/products/')
        categories = self.client.get('/api/products/categories/')
        other_product = self.client.get(f'/api/products/{product_b.pk}/')
        invalid_category = self.client.post(
            '/api/products/',
            {
                'sku': 'CATALOG-A-INVALID',
                'name': 'Produit avec catégorie étrangère',
                'category': category_b.pk,
            },
            format='json',
        )

        self.assertEqual(products.status_code, 200)
        self.assertEqual([item['id'] for item in products.data], [product_a.pk])
        self.assertEqual(categories.status_code, 200)
        self.assertEqual(
            [item['id'] for item in categories.data['results']],
            [category_a.pk],
        )
        self.assertEqual(other_product.status_code, 404)
        self.assertEqual(invalid_category.status_code, 400)
        self.assertFalse(Product.objects.filter(sku='CATALOG-A-INVALID').exists())
        self.assertNotIn(product_b.pk, [item['id'] for item in products.data])
        created_product = self.client.post(
            '/api/products/',
            {
                'sku': 'CATALOG-A-CREATED',
                'name': 'Pièce créée par tenant A',
                'category': category_a.pk,
            },
            format='json',
        )
        self.assertEqual(created_product.status_code, 201, created_product.data)
        self.assertEqual(
            Product.objects.get(pk=created_product.data['id']).tenant_id,
            tenant_a.pk,
        )

    def test_catalog_import_mapping_cannot_be_accessed_from_another_tenant(self):
        tenant_a = Tenant.objects.get(slug='kourouma-auto-parts')
        tenant_b = Tenant.objects.create(
            slug='catalog-import-tenant-b',
            name='Import Tenant B',
            status='active',
        )
        self.user.tenant = tenant_a
        self.user.save(update_fields=['tenant'])
        user_b = User.objects.create_user(
            username='catalog_import_b',
            password='secret123',
            role='stock',
            tenant=tenant_b,
        )
        self.client.force_authenticate(user=user_b)
        preview = self.client.post(
            '/api/products/catalog-import/',
            {
                'file': SimpleUploadedFile(
                    'tenant-b.csv',
                    b'reference,name\nTENANT-B-001,Produit tenant B\n',
                    content_type='text/csv',
                ),
            },
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201, preview.data)
        import_record = ProductCatalogImport.objects.get(pk=preview.data['id'])
        self.assertEqual(import_record.tenant_id, tenant_b.pk)

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f"/api/products/catalog-import/{import_record.pk}/mapping/",
            {'mapping': {'reference': 'sku', 'name': 'name'}},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        import_record.refresh_from_db()
        self.assertEqual(import_record.column_mapping['reference'], 'sku')

    def test_catalog_import_creates_products_without_stock_or_stock_movements(self):
        upload = SimpleUploadedFile(
            'catalogue.csv',
            (
                'reference,manufacturer_reference,name,category,brand,unit,purchase_price,selling_price,extra\n'
                'FLT-001,OEM-001,Filtre huile,Électronique,ACME,piece,12000,18000,note\n'
            ).encode(),
            content_type='text/csv',
        )
        preview = self.client.post(
            '/api/products/catalog-import/',
            {'file': upload},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201, preview.data)
        self.assertEqual(preview.data['unknown_columns'], ['extra'])
        self.assertEqual(preview.data['valid_rows'], 1)

        confirmed = self.client.post(
            f"/api/products/catalog-import/{preview.data['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        product = Product.objects.get(sku='FLT-001')
        self.assertEqual(product.manufacturer_reference, 'OEM-001')
        self.assertEqual(product.quantity, 0)
        self.assertFalse(StockItem.objects.filter(product=product).exists())
        self.assertTrue(AuditLog.objects.filter(
            model_name='ProductCatalogImport',
            record_id=preview.data['id'],
        ).exists())

    def test_catalog_import_reports_duplicate_references_before_confirmation(self):
        upload = SimpleUploadedFile(
            'doublons.csv',
            b'reference,name\nFLT-DUP,Premier filtre\nFLT-DUP,Second filtre\n',
            content_type='text/csv',
        )
        preview = self.client.post(
            '/api/products/catalog-import/',
            {'file': upload},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201, preview.data)
        self.assertEqual(preview.data['valid_rows'], 1)
        self.assertEqual(preview.data['error_rows'], 1)
        self.assertIn('Référence en double', preview.data['rows'][1]['errors'][0])
        confirmed = self.client.post(
            f"/api/products/catalog-import/{preview.data['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(confirmed.status_code, 400)
        self.assertFalse(Product.objects.filter(sku='FLT-DUP').exists())

    def test_catalog_import_updates_existing_product_without_changing_stock_or_restricted_prices(self):
        product = Product.objects.create(
            sku='FLT-UPDATE',
            name='Ancienne désignation',
            quantity=4,
            selling_price='15000',
        )
        upload = SimpleUploadedFile(
            'mise-a-jour.csv',
            b'reference,name,selling_price\nFLT-UPDATE,Nouvelle designation,22000\n',
            content_type='text/csv',
        )
        preview = self.client.post(
            '/api/products/catalog-import/',
            {'file': upload},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201, preview.data)
        self.assertEqual(preview.data['rows'][0]['action'], 'update')
        self.assertEqual(preview.data['valid_rows'], 1)
        self.assertTrue(preview.data['rows'][0]['warnings'])

        confirmed = self.client.post(
            f"/api/products/catalog-import/{preview.data['id']}/confirm/",
            {},
            format='json',
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data['summary']['updated'], 1)
        product.refresh_from_db()
        self.assertEqual(product.name, 'Nouvelle designation')
        self.assertEqual(product.selling_price, 15000)
        self.assertEqual(product.quantity, 4)
        self.assertFalse(StockItem.objects.filter(product=product).exists())

    def test_catalog_import_can_create_missing_categories_only_for_admin(self):
        upload = SimpleUploadedFile(
            'categories.csv',
            'reference,name,category\nFLT-CAT,Filtre,Freinage\n'.encode(),
            content_type='text/csv',
        )
        preview = self.client.post(
            '/api/products/catalog-import/',
            {'file': upload},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201, preview.data)
        denied = self.client.post(
            f"/api/products/catalog-import/{preview.data['id']}/confirm/",
            {'create_categories': True},
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

        admin = User.objects.create_user(
            username='catalog_admin',
            password='secret123',
            pin_code='5678',
            role='admin',
        )
        self.client.force_authenticate(user=admin)
        confirmed = self.client.post(
            f"/api/products/catalog-import/{preview.data['id']}/confirm/",
            {'create_categories': True},
            format='json',
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(Product.objects.get(sku='FLT-CAT').category.name, 'Freinage')

    def test_manufacturer_reference_and_optional_packaging_are_searchable_and_editable(self):
        created = self.client.post(
            '/api/products/',
            {
                'sku': 'PRD-PACK-001',
                'manufacturer_reference': 'OEM-FILTER-204',
                'name': 'Filtre à huile long',
                'unit': 'piece',
                'package_unit': 'carton',
                'units_per_package': 20,
                'selling_price': '45000',
            },
            format='json',
        )

        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['manufacturer_reference'], 'OEM-FILTER-204')
        self.assertEqual(created.data['units_per_package'], 20)

        found = self.client.get('/api/products/', {'search': 'OEM-FILTER-204'})
        self.assertEqual(found.status_code, 200)
        self.assertTrue(any(item['id'] == created.data['id'] for item in found.data))

        updated = self.client.patch(
            f"/api/products/{created.data['id']}/",
            {'manufacturer_reference': 'OEM-FILTER-205', 'units_per_package': 24},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['manufacturer_reference'], 'OEM-FILTER-205')
        self.assertEqual(updated.data['units_per_package'], 24)

    def test_product_conditioning_requires_both_package_unit_and_unit_count(self):
        response = self.client.post(
            '/api/products/',
            {
                'sku': 'PRD-PACK-INVALID',
                'name': 'Filtre sans contenu carton',
                'unit': 'piece',
                'package_unit': 'carton',
                'selling_price': '45000',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('units_per_package', response.data)

    def test_product_alternative_references_are_saved_and_searchable(self):
        product = Product.objects.create(
            sku='PRD-ALT-001',
            name='Filtre carburant',
            alternative_references='OEM-7788\nREF-ALT-99',
        )

        listed = self.client.get('/api/products/', {'search': 'REF-ALT-99'})

        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(item['id'] == product.id for item in listed.data))
        detail = self.client.get(f'/api/products/{product.id}/')
        self.assertEqual(detail.data['alternative_references'], 'OEM-7788\nREF-ALT-99')

    def test_product_generates_qr_code_when_missing(self):
        product = Product.objects.create(
            sku='PRD-QR-001',
            name='Scanner USB',
            category=self.category,
            purchase_price='120000',
            selling_price='180000',
            quantity=5,
            alert_threshold=1,
            qr_code='',
        )

        self.assertTrue(product.qr_code)
        self.assertTrue(product.qr_code.startswith('NEXORA-'))

    def test_product_can_be_archived_without_being_deleted(self):
        product = Product.objects.create(
            sku='PRD-ARCHIVE-001',
            name='Produit à archiver',
            quantity=4,
        )

        response = self.client.post(f'/api/products/{product.id}/archive/', format='json')

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertTrue(Product.objects.filter(pk=product.id).exists())
        self.assertTrue(AuditLog.objects.filter(
            user=self.user,
            action='stock',
            model_name='Product',
            record_id=product.id,
        ).exists())

    def test_product_delete_is_rejected(self):
        product = Product.objects.create(sku='PRD-NODELETE-001', name='Produit protégé')

        response = self.client.delete(f'/api/products/{product.id}/')

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Product.objects.filter(pk=product.id).exists())

    def test_product_quantity_cannot_be_changed_directly(self):
        product = Product.objects.create(
            sku='PRD-QUANTITY-LOCK',
            name='Produit quantité protégée',
            quantity=8,
        )

        response = self.client.patch(
            f'/api/products/{product.id}/',
            {'quantity': 99},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        product.refresh_from_db()
        self.assertEqual(product.quantity, 8)

    def test_product_stock_returns_quantities_by_location(self):
        from inventory.models import InventoryLocation, StockItem

        product = Product.objects.create(sku='PRD-STOCK-001', name='Produit stock')
        location = InventoryLocation.objects.create(name='Entrepôt stock', code='STOCK-LOC-01')
        StockItem.objects.create(product=product, location=location, quantity=9)

        response = self.client.get(f'/api/products/{product.id}/stock/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['quantity'], 9)
        self.assertEqual(response.data['locations'][0]['location'], location.id)

    def test_product_pricing_endpoint_recommends_selling_price_from_cost(self):
        product = Product.objects.create(
            sku='PRD-PRICE-001',
            name='Produit prix conseillé',
            category=self.category,
            cost_price='120000',
            selling_price='150000',
            quantity=10,
        )

        self.assertEqual(
            self.client.get(f'/api/products/{product.id}/pricing/?margin_percent=50').status_code,
            403,
        )
        admin = User.objects.create_user(
            username='pricing_admin_read',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=admin)
        response = self.client.get(f'/api/products/{product.id}/pricing/?margin_percent=50')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.data['cost_price']), 120000.0)
        self.assertEqual(float(response.data['recommended_selling_price']), 180000.0)
        self.assertEqual(float(response.data['margin_amount']), 60000.0)
        self.assertEqual(float(response.data['margin_percent']), 50.0)

    def test_product_pricing_endpoint_can_apply_recommended_selling_price(self):
        product = Product.objects.create(
            sku='PRD-PRICE-002',
            name='Produit prix final',
            category=self.category,
            cost_price='120000',
            selling_price='140000',
            quantity=10,
        )

        self.assertEqual(
            self.client.post(
                f'/api/products/{product.id}/pricing/',
                {'margin_percent': '50'},
                format='json',
            ).status_code,
            403,
        )
        admin = User.objects.create_user(
            username='pricing_admin_write',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            f'/api/products/{product.id}/pricing/',
            {'margin_percent': '50'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.data['recommended_selling_price']), 180000.0)
        product.refresh_from_db()
        self.assertEqual(float(product.selling_price), 180000.0)
