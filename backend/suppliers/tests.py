import tempfile
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook
from reportlab.pdfgen import canvas
from rest_framework.test import APIClient

from core.models import Tenant
from products.models import Product
from purchases.models import PurchaseOrder
from users.models import User

from .models import ExchangeRate, Supplier, SupplierImport


class SupplierApiTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_settings.enable()
        self.user = User.objects.create_user(
            username='fournisseur_admin',
            password='secret123',
            pin_code='1234',
            role='admin',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        for import_record in SupplierImport.objects.all():
            if import_record.source_file:
                import_record.source_file.delete(save=False)
        self.media_settings.disable()
        self.media_directory.cleanup()

    def test_create_supplier(self):
        payload = {
            'name': 'SOGEM',
            'contact_name': 'Amadou Diallo',
            'phone': '+224600000100',
            'email': 'contact@sogem.sn',
            'address': 'Conakry',
            'company_name': 'SOGEM SARL',
            'notes': 'Fournisseur principal'
        }
        response = self.client.post('/api/suppliers/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Supplier.objects.count(), 1)
        self.assertEqual(response.data['name'], 'SOGEM')

    def test_list_suppliers(self):
        Supplier.objects.create(name='SUP1', phone='+224600000200')
        response = self.client.get('/api/suppliers/')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)

    def test_search_supplier_by_name(self):
        Supplier.objects.create(name='Alpha Distribution', phone='+224600000300')
        response = self.client.get('/api/suppliers/?search=Alpha')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['name'] == 'Alpha Distribution' for item in response.data))

    def test_supplier_and_import_access_is_scoped_to_tenant(self):
        tenant_a = Tenant.objects.get(slug='kourouma-auto-parts')
        tenant_b = Tenant.objects.create(
            slug='suppliers-tenant-b',
            name='Suppliers Tenant B',
            status='active',
        )
        self.user.tenant = tenant_a
        self.user.save(update_fields=['tenant'])
        supplier_a = Supplier.objects.create(name='Fournisseur A', tenant=tenant_a)
        supplier_b = Supplier.objects.create(name='Fournisseur B', tenant=tenant_b)
        product_b = Product.objects.create(
            sku='SUPPLIER-B-PRODUCT',
            name='Produit fournisseur B',
            tenant=tenant_b,
        )
        user_b = User.objects.create_user(
            username='supplier_user_b',
            password='secret123',
            role='admin',
            tenant=tenant_b,
        )
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        import_b = client_b.post(
            '/api/suppliers/imports/',
            {
                'file': SimpleUploadedFile(
                    'supplier-b.csv',
                    b'reference,name,quantity,unit_price,currency\n'
                    b'SUPPLIER-B-PRODUCT,Produit fournisseur B,1,100,GNF',
                    content_type='text/csv',
                ),
                'supplier': supplier_b.pk,
            },
            format='multipart',
        )
        self.assertEqual(import_b.status_code, 201, import_b.data)

        suppliers = self.client.get('/api/suppliers/')
        foreign_supplier_import = self.client.post(
            '/api/suppliers/imports/',
            {
                'file': SimpleUploadedFile(
                    'supplier-a.csv',
                    b'reference,name,quantity,unit_price,currency\n'
                    b'SUPPLIER-B-PRODUCT,Produit fournisseur B,1,100,GNF',
                    content_type='text/csv',
                ),
                'supplier': supplier_b.pk,
            },
            format='multipart',
        )
        foreign_detail = self.client.get(f'/api/suppliers/{supplier_b.pk}/')
        foreign_document = self.client.get(
            f"/api/suppliers/imports/{import_b.data['id']}/document/",
        )
        foreign_confirmation = self.client.post(
            f"/api/suppliers/imports/{import_b.data['id']}/confirm/",
            format='json',
        )
        supplier_a_import = self.client.post(
            '/api/suppliers/imports/',
            {
                'file': SimpleUploadedFile(
                    'supplier-a-own.csv',
                    b'reference,name,quantity,unit_price,currency\n'
                    b'SUPPLIER-B-PRODUCT,Produit fournisseur B,1,100,GNF',
                    content_type='text/csv',
                ),
                'supplier': supplier_a.pk,
            },
            format='multipart',
        )
        cross_tenant_product_match = self.client.post(
            (
                f"/api/suppliers/imports/{supplier_a_import.data['id']}/"
                f"rows/{supplier_a_import.data['rows'][0]['id']}/match/"
            ),
            {'product': product_b.pk},
            format='json',
        )

        self.assertEqual(suppliers.status_code, 200)
        self.assertEqual([item['id'] for item in suppliers.data], [supplier_a.pk])
        self.assertEqual(foreign_supplier_import.status_code, 404)
        self.assertEqual(foreign_detail.status_code, 404)
        self.assertEqual(foreign_document.status_code, 404)
        self.assertEqual(foreign_confirmation.status_code, 404)
        self.assertEqual(supplier_a_import.status_code, 201, supplier_a_import.data)
        self.assertEqual(
            supplier_a_import.data['rows'][0]['matched_product_id'],
            None,
        )
        self.assertEqual(cross_tenant_product_match.status_code, 400)
        self.assertTrue(Product.objects.filter(pk=product_b.pk).exists())

    def test_create_exchange_rate(self):
        payload = {
            'source_currency': 'USD',
            'target_currency': 'GNF',
            'rate': '9000.00',
            'effective_date': timezone.localdate().isoformat(),
        }
        response = self.client.post(
            '/api/suppliers/exchange-rates/',
            payload,
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['source_currency'], 'USD')
        self.assertEqual(response.data['created_by'], self.user.id)
        self.assertEqual(response.data['created_by_name'], self.user.username)

        changed_rate = self.client.post(
            '/api/suppliers/exchange-rates/',
            {**payload, 'rate': '9100.00'},
            format='json',
        )
        self.assertEqual(changed_rate.status_code, 201, changed_rate.data)
        history = self.client.get(
            '/api/suppliers/exchange-rates/',
            {'source_currency': 'USD', 'target_currency': 'GNF'},
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data['count'], 2)

    def test_import_supplier_csv(self):
        supplier = Supplier.objects.create(name='Import Supplier', phone='+224600000400')
        csv_file = SimpleUploadedFile(
            'supplier_import.csv',
            b'reference,name,quantity,unit_price,currency\nSKU-001,Produit A,10,2500,USD\nSKU-002,Produit B,5,3750,USD',
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/suppliers/imports/',
            {'file': csv_file, 'supplier': supplier.id},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertGreaterEqual(response.data['parsed_rows'], 2)

    def test_import_supplier_supports_common_aliases_and_excel(self):
        supplier = Supplier.objects.create(name='Import Alias Supplier', phone='+224600000500')
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Commande'
        sheet.append(['Product Code', 'Description', 'Qty', 'Unit Price', 'Currency'])
        sheet.append(['SKU-101', 'Filtre Toyota', '12', '4.50', 'USD'])

        buffer = BytesIO()
        workbook.save(buffer)
        excel_file = SimpleUploadedFile(
            'supplier_aliases.xlsx',
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        response = self.client.post(
            '/api/suppliers/imports/',
            {'file': excel_file, 'supplier': supplier.id},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['parsed_rows'], 1)
        self.assertEqual(response.data['rows'][0]['reference'], 'SKU-101')
        self.assertEqual(response.data['rows'][0]['name'], 'Filtre Toyota')
        self.assertEqual(response.data['rows'][0]['currency'], 'USD')

    def test_supplier_import_rejects_unrecognized_stock_workbook_without_saving_it(self):
        supplier = Supplier.objects.create(name='Internal Stock Workbook Supplier')
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Stock'
        sheet.append([
            'N°',
            'Libellé (Désignation)',
            'Référence',
            'Quantité (carton)',
            'Notation prix/qte',
            'Prix détail (GNF)',
            'Prix détail (USD)',
            'Prix vente (GNF)',
            'Prix vente (USD)',
        ])
        sheet.append(['1', 'Filtre à huile', 'BSG', '77', '50P', None, None, None, None])

        buffer = BytesIO()
        workbook.save(buffer)
        stock_file = SimpleUploadedFile(
            'entrepot_stock.xlsx',
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        response = self.client.post(
            '/api/suppliers/imports/',
            {'file': stock_file, 'supplier': supplier.id},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Aucune ligne fournisseur exploitable', response.data['file'][0])
        self.assertEqual(SupplierImport.objects.count(), 0)
        self.assertEqual(Product.objects.count(), 0)

    def test_supplier_import_preview_matches_products_without_creating_new_products(self):
        supplier = Supplier.objects.create(name='Matching Supplier')
        existing = Product.objects.create(sku='SKU-MATCH-1', name='Produit reconnu')
        csv_file = SimpleUploadedFile(
            'matching.csv',
            b'reference,name,quantity,unit_price,currency\nSKU-MATCH-1,Produit fournisseur,2,125,USD\nUNKNOWN-1,Nouveau produit,3,250,USD',
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/suppliers/imports/',
            {'file': csv_file, 'supplier': supplier.id},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['rows'][0]['matched_product'], existing.name)
        self.assertEqual(response.data['rows'][1]['matched_product'], '')
        self.assertEqual(Product.objects.count(), 1)

    def test_versioned_purchase_import_can_be_confirmed_once(self):
        supplier = Supplier.objects.create(name='Import API v1')
        Product.objects.create(sku='SKU-101', name='Produit API')
        ExchangeRate.objects.create(source_currency='USD', target_currency='GNF', rate='9000', effective_date='2026-09-12')
        csv_file = SimpleUploadedFile(
            'purchase.csv',
            b'reference,name,quantity,unit_price,currency\nSKU-101,Produit API,3,1200,USD',
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/v1/purchase-imports/',
            {'file': csv_file, 'supplier': supplier.id},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        import_id = response.data['id']
        confirmation = self.client.post(f'/api/v1/purchase-imports/{import_id}/confirm/', format='json')
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.data['status'], 'validated')

        repeated_confirmation = self.client.post(f'/api/v1/purchase-imports/{import_id}/confirm/', format='json')
        self.assertEqual(repeated_confirmation.status_code, 409)

    def test_supplier_import_confirmation_creates_draft_purchase_order(self):
        supplier = Supplier.objects.create(name='Import to Order Supplier', phone='+224600000600')
        Product.objects.create(sku='SKU-PO-1', name='Produit commande')
        ExchangeRate.objects.create(source_currency='USD', target_currency='GNF', rate='9000', effective_date='2026-09-12')
        csv_file = SimpleUploadedFile(
            'order_import.csv',
            'reference,name,quantity,unit_price,currency\nSKU-PO-1,Produit commande,4,1500,USD'.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/suppliers/imports/',
            {'file': csv_file, 'supplier': supplier.id},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        confirmation = self.client.post(f"/api/suppliers/imports/{response.data['id']}/confirm/", format='json')
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.data['status'], 'validated')
        self.assertIn('purchase_order', confirmation.data)
        self.assertEqual(confirmation.data['purchase_order']['status'], 'draft')
        self.assertEqual(confirmation.data['purchase_order']['items'][0]['quantity'], 4)

    def test_unknown_products_are_blocked_until_matched_and_never_auto_created(self):
        supplier = Supplier.objects.create(name='Unknown Product Supplier')
        csv_file = SimpleUploadedFile(
            'unknown.csv',
            b'reference,name,quantity,unit_price,currency\nSKU-UNKNOWN,Produit inconnu,3,250,GNF',
            content_type='text/csv',
        )
        preview = self.client.post(
            '/api/suppliers/imports/',
            {'file': csv_file, 'supplier': supplier.id},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201)
        unknown_product_count = Product.objects.count()

        blocked = self.client.post(
            f"/api/suppliers/imports/{preview.data['id']}/confirm/",
            format='json',
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(Product.objects.count(), unknown_product_count)

        existing = Product.objects.create(sku='INTERNAL-1', name='Pièce existante')
        matched = self.client.post(
            f"/api/suppliers/imports/{preview.data['id']}/rows/{preview.data['rows'][0]['id']}/match/",
            {'product': existing.id},
            format='json',
        )
        self.assertEqual(matched.status_code, 200)
        confirmation = self.client.post(
            f"/api/suppliers/imports/{preview.data['id']}/confirm/",
            format='json',
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.data['purchase_order']['items'][0]['product'], existing.id)
        self.assertEqual(Product.objects.count(), unknown_product_count + 1)

    def test_invalid_import_values_are_reported_and_cannot_create_order(self):
        supplier = Supplier.objects.create(name='Invalid Import Supplier')
        Product.objects.create(sku='SKU-INVALID', name='Produit invalide')
        csv_file = SimpleUploadedFile(
            'invalid.csv',
            b'reference,name,quantity,unit_price,currency\nSKU-INVALID,Produit invalide,1.5,,',
            content_type='text/csv',
        )
        preview = self.client.post(
            '/api/suppliers/imports/',
            {'file': csv_file, 'supplier': supplier.id},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201)
        self.assertEqual(len(preview.data['rows'][0]['validation_errors']), 3)
        confirmation = self.client.post(
            f"/api/suppliers/imports/{preview.data['id']}/confirm/",
            format='json',
        )
        self.assertEqual(confirmation.status_code, 400)
        self.assertFalse(Supplier.objects.get(pk=supplier.id).purchase_orders.exists())

        row_id = preview.data['rows'][0]['id']
        correction = self.client.patch(
            f"/api/suppliers/imports/{preview.data['id']}/rows/{row_id}/correction/",
            {'quantity': '2', 'unit_price': '55', 'currency': 'GNF'},
            format='json',
        )
        self.assertEqual(correction.status_code, 200)
        self.assertEqual(correction.data['rows'][0]['validation_errors'], [])
        confirmation = self.client.post(
            f"/api/suppliers/imports/{preview.data['id']}/confirm/",
            format='json',
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.data['purchase_order']['items'][0]['quantity'], 2)

    def test_import_with_mixed_currencies_cannot_create_order_or_change_stock(self):
        supplier = Supplier.objects.create(name='Mixed Currency Supplier')
        Product.objects.create(sku='SKU-GNF', name='Produit GNF')
        Product.objects.create(sku='SKU-USD', name='Produit USD')
        csv_file = SimpleUploadedFile(
            'mixed-currency.csv',
            b'reference,name,quantity,unit_price,currency\nSKU-GNF,Produit GNF,2,100,GNF\nSKU-USD,Produit USD,1,5,USD',
            content_type='text/csv',
        )

        preview = self.client.post(
            '/api/suppliers/imports/',
            {'file': csv_file, 'supplier': supplier.id},
            format='multipart',
        )
        self.assertEqual(preview.status_code, 201)
        confirmation = self.client.post(
            f"/api/suppliers/imports/{preview.data['id']}/confirm/",
            format='json',
        )

        self.assertEqual(confirmation.status_code, 400)
        self.assertIn('plusieurs devises', confirmation.data['detail'])
        self.assertFalse(supplier.purchase_orders.exists())
        self.assertEqual(list(Product.objects.values_list('quantity', flat=True)), [0, 0])

    def test_import_preserves_original_and_marks_same_file_as_possible_duplicate(self):
        supplier = Supplier.objects.create(name='Retained File Supplier')
        content = b'reference,name,quantity,unit_price,currency\nSKU-RETAIN,Piece,2,100,GNF'
        for _ in range(2):
            response = self.client.post(
                '/api/suppliers/imports/',
                {
                    'file': SimpleUploadedFile('retained.csv', content, content_type='text/csv'),
                    'supplier': supplier.id,
                },
                format='multipart',
            )
            self.assertEqual(response.status_code, 201)
        first, second = Supplier.objects.get(name='Retained File Supplier').supplier_imports.order_by('created_at')
        self.assertTrue(first.source_file)
        self.assertEqual(first.uploaded_by, self.user)
        self.assertEqual(first.file_sha256, second.file_sha256)
        self.assertEqual(second.possible_duplicate_of_id, first.id)
        self.assertNotIn(str(settings.MEDIA_ROOT), first.source_file.path)
        download = self.client.get(f'/api/suppliers/imports/{first.id}/document/')
        self.assertEqual(download.status_code, 200)
        downloaded_content = b''.join(download.streaming_content)
        for close_resource in download._resource_closers:
            close_resource()
        self.assertEqual(downloaded_content, content)

    def test_stock_can_read_suppliers_and_import_but_cannot_edit_supplier_or_exchange_rates(self):
        stock_user = User.objects.create_user(
            username='supplier_stock',
            password='secret123',
            pin_code='2345',
            role='stock',
        )
        supplier = Supplier.objects.create(name='Stock Import Supplier')
        stock_client = APIClient()
        stock_client.force_authenticate(user=stock_user)
        self.assertEqual(stock_client.get('/api/suppliers/').status_code, 200)
        self.assertEqual(stock_client.post('/api/suppliers/', {'name': 'Interdit'}, format='json').status_code, 403)
        self.assertEqual(
            stock_client.post(
                '/api/suppliers/exchange-rates/',
                {'source_currency': 'USD', 'target_currency': 'GNF', 'rate': '9000', 'effective_date': '2026-09-12'},
                format='json',
            ).status_code,
            403,
        )
        Product.objects.create(sku='SKU-STOCK', name='Produit existant')
        upload = stock_client.post(
            '/api/suppliers/imports/',
            {
                'file': SimpleUploadedFile(
                    'stock.csv',
                    b'reference,name,quantity,unit_price,currency\nSKU-STOCK,Produit existant,2,100,GNF',
                    content_type='text/csv',
                ),
                'supplier': supplier.id,
            },
            format='multipart',
        )
        self.assertEqual(upload.status_code, 201)
        document = stock_client.get(f"/api/suppliers/imports/{upload.data['id']}/document/")
        self.assertEqual(document.status_code, 200)
        for close_resource in document._resource_closers:
            close_resource()
        confirmation = stock_client.post(
            f"/api/suppliers/imports/{upload.data['id']}/confirm/",
            format='json',
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(Product.objects.get(sku='SKU-STOCK').quantity, 0)
        order_id = confirmation.data['purchase_order']['id']
        self.assertEqual(
            PurchaseOrder.objects.get(pk=order_id).tenant_id,
            Tenant.objects.get(slug='kourouma-auto-parts').pk,
        )
        self.assertEqual(stock_client.post(f'/api/v1/purchase-orders/{order_id}/confirm/').status_code, 403)
        self.assertEqual(stock_client.post(f'/api/v1/purchase-orders/{order_id}/send/').status_code, 200)

    def test_text_pdf_is_imported_but_scanned_pdf_is_rejected_with_manual_entry_message(self):
        supplier = Supplier.objects.create(name='PDF Import Supplier')
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(40, 800, 'reference  name  quantity  unit_price  currency')
        pdf.drawString(40, 780, 'SKU-PDF  Filtre huile  2  150  GNF')
        pdf.save()
        response = self.client.post(
            '/api/suppliers/imports/',
            {
                'file': SimpleUploadedFile('text.pdf', buffer.getvalue(), content_type='application/pdf'),
                'supplier': supplier.id,
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['rows'][0]['reference'], 'SKU-PDF')

        scanned = BytesIO()
        blank_pdf = canvas.Canvas(scanned)
        blank_pdf.showPage()
        blank_pdf.save()
        rejected = self.client.post(
            '/api/suppliers/imports/',
            {
                'file': SimpleUploadedFile('scan.pdf', scanned.getvalue(), content_type='application/pdf'),
                'supplier': supplier.id,
            },
            format='multipart',
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn('saisie manuelle', rejected.data['file'][0])

    def test_supplier_import_rejects_non_csv_files(self):
        supplier = Supplier.objects.create(name='Import validation')
        file_obj = SimpleUploadedFile('purchase.txt', b'not,csv', content_type='text/plain')

        response = self.client.post(
            '/api/v1/purchase-imports/',
            {'file': file_obj, 'supplier': supplier.id},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
