from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from core.models import AuditLog, Tenant
from customers.models import Customer
from finance.models import FinancialAccount, FinancialTransaction
from inventory.models import (
    Carton,
    InventoryCostLayer,
    InventoryLocation,
    StockItem,
    StockMovement,
)
from products.models import Product
from purchases.models import (
    ExternalPurchase,
    ExternalPurchaseMovement,
    ExternalPurchasePayment,
    ExternalPurchasePaymentAllocation,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    ReceiptQuarantine,
)
from suppliers.models import ExchangeRate, Supplier
from sales.models import Sale, SaleItem
from users.models import User


class PurchaseOrderApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='achats_admin',
            password='secret123',
            pin_code='1234',
            role='admin',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.admin = User.objects.create_user(
            username='achats_validator',
            password='secret123',
            pin_code='4321',
            role='admin',
        )
        self.supplier = Supplier.objects.create(
            name='Alpha Distribution',
            contact_name='Moussa Bah',
            phone='+224600001000',
            email='moussa@alpha.sn',
            company_name='Alpha Distribution',
        )
        self.product = Product.objects.create(
            sku='ACH-001',
            name='Ordinateur portable',
            purchase_price='300000',
            selling_price='450000',
            quantity=0,
            alert_threshold=2,
        )
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        self.location = InventoryLocation.objects.create(
            name='Entrepôt des achats',
            code='PURCHASE-RECEIPTS',
            location_type='warehouse',
        )

    def create_approved_order(self, reference, items, endpoint='/api/purchases/orders/'):
        response = self.client.post(
            endpoint,
            {
                'supplier': self.supplier.id,
                'reference': reference,
                'items': items,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        if endpoint == '/api/v1/purchase-orders/':
            action_root = f'/api/v1/purchase-orders/{response.data["id"]}'
        else:
            action_root = f'/api/purchases/orders/{response.data["id"]}'
        sent = self.client.post(f'{action_root}/send/', format='json')
        self.assertEqual(sent.status_code, 200, sent.data)
        approved = self.client.post(f'{action_root}/confirm/', format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        return approved

    def submit_and_validate_receipt(self, receipt_id):
        submitted = self.client.post(
            f'/api/purchases/receipts/{receipt_id}/submit/',
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        validated = self.admin_client.post(
            f'/api/purchases/receipts/{receipt_id}/validate/',
            {
                'version': submitted.data['version'],
                'reviewed_item_ids': [item['id'] for item in submitted.data['items']],
            },
            format='json',
        )
        self.assertEqual(validated.status_code, 200, validated.data)
        return validated

    def test_purchase_order_email_attaches_pdf_and_submits_without_changing_stock(self):
        order_response = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier.id,
                'reference': 'PO-EMAIL-001',
                'items': [{
                    'product': self.product.id,
                    'quantity': 3,
                    'unit_cost': '125000.00',
                }],
            },
            format='json',
        )
        self.assertEqual(order_response.status_code, 201, order_response.data)
        uploaded_pdf = SimpleUploadedFile(
            'PO-EMAIL-001.pdf',
            b'%PDF-1.4\npurchase-order-test',
            content_type='application/pdf',
        )

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend'):
            with patch('purchases.views.create_branded_email') as email_message:
                email_message.return_value.send.return_value = 1
                response = self.client.post(
                    f'/api/v1/purchase-orders/{order_response.data["id"]}/email/',
                    {'file': uploaded_pdf},
                    format='multipart',
                )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'submitted')
        self.assertEqual(
            email_message.call_args.kwargs['recipient_list'],
            [self.supplier.email],
        )
        attachment = email_message.return_value.attach.call_args.args
        self.assertEqual(attachment[0], 'PO-EMAIL-001.pdf')
        self.assertEqual(attachment[1], b'%PDF-1.4\npurchase-order-test')
        order = PurchaseOrder.objects.get(pk=order_response.data['id'])
        self.assertEqual(order.status, 'submitted')
        self.assertFalse(StockItem.objects.filter(product=self.product).exists())

    def test_purchase_order_email_rejects_unconfigured_email_and_invalid_pdf(self):
        order_response = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier.id,
                'reference': 'PO-EMAIL-002',
                'items': [{
                    'product': self.product.id,
                    'quantity': 1,
                    'unit_cost': '100.00',
                }],
            },
            format='json',
        )
        self.assertEqual(order_response.status_code, 201, order_response.data)
        endpoint = f'/api/v1/purchase-orders/{order_response.data["id"]}/email/'

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'):
            unconfigured = self.client.post(
                endpoint,
                {'file': SimpleUploadedFile('order.pdf', b'%PDF-1.4\nfile')},
                format='multipart',
            )
        self.assertEqual(unconfigured.status_code, 503, unconfigured.data)

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend'):
            invalid_pdf = self.client.post(
                endpoint,
                {'file': SimpleUploadedFile('order.pdf', b'not a PDF')},
                format='multipart',
            )
        self.assertEqual(invalid_pdf.status_code, 400, invalid_pdf.data)
        order = PurchaseOrder.objects.get(pk=order_response.data['id'])
        self.assertEqual(order.status, 'draft')

    def test_receipt_import_matches_existing_order_product_and_waits_for_validation(self):
        order = self.create_approved_order(
            'PO-IMPORT-001',
            [{'product': self.product.id, 'quantity': 4, 'unit_cost': '125000.00'}],
        )

        def workbook_file():
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(['N° bon de réception interne', 'BR-SUP-19'])
            sheet.append(['Date de réception', '18/01/2025'])
            sheet.append(['Fournisseur', self.supplier.name])
            sheet.append(['N° commande fournisseur', 'PO-IMPORT-001'])
            sheet.append(['Facture / bon de livraison fournisseur', 'BL-SUP-778'])
            sheet.append(['Devise achat', 'GNF'])
            sheet.append([])
            sheet.append([
                'Référence article NEXORA',
                'Référence article fournisseur',
                'Désignation / description',
                'Quantité commandée',
                'Quantité réellement reçue',
                'Quantité acceptée',
                'À isoler',
                "Prix d'achat unitaire",
                'Pièces par carton',
                'Motif écart / réserves',
                'État / conformité',
                'État emballage / qualité',
                'N° lot / réf. livraison',
                'Commentaire',
            ])
            sheet.append([
                'ACH-001',
                'SUP-ACH-001',
                self.product.name,
                4,
                3,
                2,
                1,
                130000,
                1,
                'Une unité isolée pour emballage endommagé.',
                'Réception partielle',
                'Carton ouvert',
                'LOT-77',
                'À contrôler avant rangement.',
            ])
            content = BytesIO()
            workbook.save(content)
            return SimpleUploadedFile(
                'bon-reception-test.xlsx',
                content.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )

        endpoint = '/api/purchases/receipts/import/'
        preview = self.client.post(
            endpoint,
            {
                'purchase_order': order.data['id'],
                'location': self.location.id,
                'file': workbook_file(),
            },
            format='multipart',
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data['valid_rows'], 1, preview.data)
        self.assertEqual(preview.data['supplier_document_reference'], 'BL-SUP-778')
        self.assertEqual(preview.data['rows'][0]['product'], self.product.id)

        created = self.client.post(
            endpoint,
            {
                'purchase_order': order.data['id'],
                'location': self.location.id,
                'action': 'confirm',
                'discrepancy_reason': 'Réception partielle avec une unité isolée.',
                'file': workbook_file(),
            },
            format='multipart',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(len(created.data), 1)
        receipt = PurchaseReceipt.objects.get(pk=created.data[0]['id'])
        self.assertEqual(receipt.status, 'draft')
        self.assertEqual(receipt.supplier_document_reference, 'BL-SUP-778')
        item = receipt.items.get()
        self.assertEqual(item.supplier_reference, 'SUP-ACH-001')
        self.assertEqual(item.supplier_lot_reference, 'LOT-77')
        self.assertEqual(item.condition_status, 'Réception partielle')
        self.assertEqual(item.packaging_condition, 'Carton ouvert')
        self.assertEqual(item.notes, 'À contrôler avant rangement.')
        self.assertFalse(StockItem.objects.filter(product=self.product).exists())

        self.submit_and_validate_receipt(receipt.pk)
        self.assertEqual(
            StockItem.objects.get(product=self.product, location=self.location).quantity,
            2,
        )

    def test_batch_receipt_drafts_can_be_allocated_to_multiple_warehouses_without_stock_change(self):
        second_location = InventoryLocation.objects.create(
            name='Entrepôt secondaire',
            code='PURCHASE-RECEIPTS-2',
            location_type='warehouse',
        )
        order = self.create_approved_order(
            'PO-BATCH-WAREHOUSE',
            [{'product': self.product.id, 'quantity': 10, 'unit_cost': '125000.00'}],
        )
        response = self.client.post(
            '/api/purchases/receipts/batch/',
            {
                'receipts': [
                    {
                        'purchase_order': order.data['id'],
                        'location': self.location.id,
                        'reference': 'RCPT-BATCH-1',
                        'discrepancy_reason': 'Répartition de la livraison entre les entrepôts.',
                        'items': [{
                            'product': self.product.id,
                            'quantity_received': 4,
                            'unit_cost': '125000.00',
                        }],
                    },
                    {
                        'purchase_order': order.data['id'],
                        'location': second_location.id,
                        'reference': 'RCPT-BATCH-2',
                        'discrepancy_reason': 'Répartition de la livraison entre les entrepôts.',
                        'items': [{
                            'product': self.product.id,
                            'quantity_received': 6,
                            'unit_cost': '125000.00',
                        }],
                    },
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data), 2)
        self.assertEqual({receipt['location'] for receipt in response.data}, {
            self.location.id,
            second_location.id,
        })
        self.assertTrue(all(receipt['status'] == 'draft' for receipt in response.data))
        self.assertFalse(StockItem.objects.filter(product=self.product).exists())

    def test_batch_receipt_rejects_allocation_above_ordered_quantity(self):
        second_location = InventoryLocation.objects.create(
            name='Entrepôt secondaire',
            code='PURCHASE-RECEIPTS-OVER',
            location_type='warehouse',
        )
        order = self.create_approved_order(
            'PO-BATCH-OVER',
            [{'product': self.product.id, 'quantity': 10, 'unit_cost': '125000.00'}],
        )
        response = self.client.post(
            '/api/purchases/receipts/batch/',
            {
                'receipts': [
                    {
                        'purchase_order': order.data['id'],
                        'location': self.location.id,
                        'reference': 'RCPT-BATCH-OVER-1',
                        'discrepancy_reason': 'Répartition de la livraison.',
                        'items': [{'product': self.product.id, 'quantity_received': 7}],
                    },
                    {
                        'purchase_order': order.data['id'],
                        'location': second_location.id,
                        'reference': 'RCPT-BATCH-OVER-2',
                        'discrepancy_reason': 'Répartition de la livraison.',
                        'items': [{'product': self.product.id, 'quantity_received': 4}],
                    },
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=order.data['id']).exists())
        self.assertFalse(StockItem.objects.filter(product=self.product).exists())

    def test_replenishment_suggestions_include_approved_inbound_and_explain_missing_inputs(self):
        StockItem.objects.create(product=self.product, location=self.location, quantity=1)
        self.create_approved_order(
            'PO-INBOUND-REPLENISH',
            [{'product': self.product.id, 'quantity': 3, 'unit_cost': '100'}],
            endpoint='/api/v1/purchase-orders/',
        )
        low_stock = Product.objects.create(
            sku='ACH-LOW-002',
            name='Filtre à huile',
            quantity=2,
            alert_threshold=5,
        )
        response = self.client.get('/api/v1/purchase-orders/replenishment-suggestions/')
        self.assertEqual(response.status_code, 200)
        suggestions = {row['product_id']: row for row in response.data['suggestions']}
        self.assertNotIn(self.product.id, suggestions)
        self.assertEqual(suggestions[low_stock.id]['suggested_quantity'], 3)
        self.assertTrue(any('réservations' in note for note in response.data['limitations']))

    def test_create_purchase_order_with_items(self):
        payload = {
            'supplier': self.supplier.id,
            'reference': 'PO-2026-001',
            'status': 'draft',
            'notes': 'Commande initiale',
            'items': [
                {'product': self.product.id, 'quantity': 3, 'unit_cost': '250000.00'}
            ],
        }
        response = self.client.post('/api/purchases/orders/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['reference'], 'PO-2026-001')
        self.assertEqual(float(response.data['total_amount']), 750000.0)

    def test_usd_purchase_uses_and_preserves_reference_rate_snapshot(self):
        effective_date = timezone.localdate()
        ExchangeRate.objects.create(
            source_currency='USD',
            target_currency='GNF',
            rate='9000',
            effective_date=effective_date,
            created_by=self.user,
        )
        response = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier.id,
                'reference': 'PO-USD-REFERENCE',
                'currency': 'USD',
                'items': [{'product': self.product.id, 'quantity': 2, 'unit_cost': '10.50'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = PurchaseOrder.objects.get(pk=response.data['id'])
        self.assertEqual(order.currency, 'USD')
        self.assertEqual(order.exchange_rate, Decimal('9000'))
        self.assertEqual(order.reference_exchange_rate, Decimal('9000'))
        self.assertEqual(order.exchange_rate_date, effective_date)
        self.assertEqual(order.exchange_rate_applied_by, self.user)
        self.assertEqual(order.total_amount, Decimal('21.00'))

        ExchangeRate.objects.create(
            source_currency='USD',
            target_currency='GNF',
            rate='9200',
            effective_date=effective_date,
            created_by=self.admin,
        )
        order.refresh_from_db()
        self.assertEqual(order.exchange_rate, Decimal('9000'))
        self.assertEqual(order.reference_exchange_rate, Decimal('9000'))

    def test_usd_receipt_uses_purchase_snapshot_after_reference_rate_changes(self):
        effective_date = timezone.localdate()
        ExchangeRate.objects.create(
            source_currency='USD',
            target_currency='GNF',
            rate='9000',
            effective_date=effective_date,
        )
        created = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier.id,
                'reference': 'PO-USD-HISTORICAL-RATE',
                'currency': 'USD',
                'items': [{'product': self.product.id, 'quantity': 2, 'unit_cost': '10'}],
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)

        ExchangeRate.objects.create(
            source_currency='USD',
            target_currency='GNF',
            rate='9200',
            effective_date=effective_date,
        )
        order_id = created.data['id']
        self.assertEqual(
            self.client.post(f'/api/purchases/orders/{order_id}/send/', format='json').status_code,
            200,
        )
        approved = self.client.post(
            f'/api/purchases/orders/{order_id}/confirm/',
            format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        receipt = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order_id,
                'location': self.location.id,
                'reference': 'RCPT-USD-HISTORICAL-RATE',
                'items': [{
                    'product': self.product.id,
                    'quantity_received': 2,
                    'quantity_accepted': 2,
                    'quantity_quarantined': 0,
                    'unit_cost': '10',
                }],
            },
            format='json',
        )
        self.assertEqual(receipt.status_code, 201, receipt.data)
        self.assertEqual(receipt.data['currency'], 'USD')
        self.assertEqual(receipt.data['exchange_rate'], '9000.000000')
        self.assertEqual(receipt.data['reference_exchange_rate'], '9000.000000')

        self.submit_and_validate_receipt(receipt.data['id'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price, Decimal('90000.00'))
        self.assertEqual(self.product.cost_price, Decimal('90000.00'))

    def test_usd_purchase_requires_reference_and_authorized_override_reason(self):
        payload = {
            'supplier': self.supplier.id,
            'reference': 'PO-USD-NO-RATE',
            'currency': 'USD',
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_cost': '10'}],
        }
        no_rate = self.client.post('/api/purchases/orders/', payload, format='json')
        self.assertEqual(no_rate.status_code, 400)
        self.assertIn('currency', no_rate.data)

        ExchangeRate.objects.create(
            source_currency='USD',
            target_currency='GNF',
            rate='9000',
            effective_date=timezone.localdate(),
        )
        no_reason = self.client.post(
            '/api/purchases/orders/',
            {**payload, 'reference': 'PO-USD-NO-REASON', 'exchange_rate': '9200'},
            format='json',
        )
        self.assertEqual(no_reason.status_code, 400)
        self.assertIn('exchange_rate_reason', no_reason.data)

        stock_user = User.objects.create_user(
            username='stock_purchase_rate',
            role='stock',
            pin_code='1357',
        )
        stock_client = APIClient()
        stock_client.force_authenticate(user=stock_user)
        forbidden_override = stock_client.post(
            '/api/purchases/orders/',
            {
                **payload,
                'reference': 'PO-USD-STOCK-OVERRIDE',
                'exchange_rate': '9200',
                'exchange_rate_reason': 'Taux convenu avec le fournisseur',
            },
            format='json',
        )
        self.assertEqual(forbidden_override.status_code, 400)
        self.assertIn('exchange_rate', forbidden_override.data)

        override = self.client.post(
            '/api/purchases/orders/',
            {
                **payload,
                'reference': 'PO-USD-OVERRIDE',
                'exchange_rate': '9200',
                'exchange_rate_reason': 'Taux négocié avec le fournisseur',
            },
            format='json',
        )
        self.assertEqual(override.status_code, 201, override.data)
        self.assertEqual(override.data['exchange_rate'], '9200.000000')
        self.assertEqual(override.data['reference_exchange_rate'], '9000.000000')
        self.assertEqual(
            override.data['exchange_rate_reason'],
            'Taux négocié avec le fournisseur',
        )
        self.assertEqual(override.data['exchange_rate_applied_by_name'], self.user.username)

    def test_gnf_purchase_remains_in_gnf_without_currency_conversion(self):
        response = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier.id,
                'reference': 'PO-GNF-ONLY',
                'currency': 'GNF',
                'exchange_rate': '9200',
                'items': [{'product': self.product.id, 'quantity': 1, 'unit_cost': '250000'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['currency'], 'GNF')
        self.assertEqual(response.data['exchange_rate'], '1.000000')
        self.assertIsNone(response.data['reference_exchange_rate'])

    def test_stock_manager_can_create_and_submit_own_draft_but_cannot_approve_or_submit_other_drafts(self):
        stock_user = User.objects.create_user(
            username='stock_purchase_access',
            role='stock',
            pin_code='2468',
        )
        stock_client = APIClient()
        stock_client.force_authenticate(user=stock_user)
        payload = {
            'supplier': self.supplier.id,
            'reference': 'PO-STOCK-FORBIDDEN',
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_cost': '250000.00'}],
        }

        created = stock_client.post('/api/purchases/orders/', payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['created_by'], stock_user.id)
        self.assertNotIn('total_amount', created.data)
        submitted = stock_client.post(
            f"/api/purchases/orders/{created.data['id']}/send/",
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertEqual(
            stock_client.get(f"/api/purchases/orders/{created.data['id']}/").status_code,
            200,
        )
        self.assertEqual(
            stock_client.post(f"/api/purchases/orders/{created.data['id']}/confirm/").status_code,
            403,
        )

        admin_payload = {**payload, 'reference': 'PO-ADMIN-OWNED'}
        order = self.client.post('/api/purchases/orders/', admin_payload, format='json')
        self.assertEqual(order.status_code, 201, order.data)
        denied_transition = stock_client.post(
            f"/api/purchases/orders/{order.data['id']}/send/",
            format='json',
        )
        self.assertEqual(denied_transition.status_code, 403)

    def test_stock_receipt_hides_costs_and_waits_for_admin_validation(self):
        location = InventoryLocation.objects.create(
            name='Réserve autorisée',
            code='RECEIPT-STOCK-01',
            location_type='warehouse',
        )
        stock_user = User.objects.create_user(
            username='reception_stock',
            password='secret123',
            pin_code='2468',
            role='stock',
        )
        location.authorized_users.add(stock_user)
        order = self.create_approved_order(
            'PO-STOCK-001',
            [{'product': self.product.id, 'quantity': 4, 'unit_cost': '125000.00'}],
        )
        self.assertEqual(order.status_code, 200)

        self.client.force_authenticate(user=stock_user)
        visible_orders = self.client.get('/api/purchases/orders/')
        self.assertEqual(visible_orders.status_code, 200)
        listed_orders = visible_orders.data.get('results', visible_orders.data)
        self.assertEqual([item['reference'] for item in listed_orders], ['PO-STOCK-001'])
        self.assertNotIn('unit_cost', listed_orders[0]['items'][0])
        self.assertNotIn('total_amount', listed_orders[0])

        receipt = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order.data['id'],
                'location': location.id,
                'reference': 'RCPT-STOCK-001',
                'discrepancy_reason': 'Une unité manque sur le bon de livraison.',
                'transport_cost': '999999',
                'items': [{
                    'product': self.product.id,
                    'quantity_received': 3,
                    'unit_cost': '1',
                }],
            },
            format='json',
        )
        self.assertEqual(receipt.status_code, 201)
        self.assertNotIn('total_cost', receipt.data)
        self.assertNotIn('transport_cost', receipt.data)
        self.assertNotIn('unit_cost', receipt.data['items'][0])
        self.assertEqual(receipt.data['status'], 'draft')
        self.assertEqual(PurchaseReceipt.objects.get(pk=receipt.data['id']).items.get().unit_cost, 125000)
        self.assertFalse(StockItem.objects.filter(product=self.product, location=location).exists())

        denied = self.client.post(f"/api/purchases/receipts/{receipt.data['id']}/validate/", format='json')
        self.assertEqual(denied.status_code, 403)
        self.client.force_authenticate(user=stock_user)
        submitted = self.client.post(
            f"/api/purchases/receipts/{receipt.data['id']}/submit/",
            format='json',
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'submitted')
        validated = self.admin_client.post(
            f"/api/purchases/receipts/{receipt.data['id']}/validate/",
            {
                'version': submitted.data['version'],
                'reviewed_item_ids': [item['id'] for item in submitted.data['items']],
            },
            format='json',
        )
        self.assertEqual(validated.status_code, 200)
        self.assertEqual(StockItem.objects.get(product=self.product, location=location).quantity, 3)

    def test_list_purchase_orders(self):
        self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier.id,
                'reference': 'PO-2026-002',
                'status': 'draft',
                'items': [{'product': self.product.id, 'quantity': 2, 'unit_cost': '100000.00'}],
            },
            format='json',
        )
        response = self.client.get('/api/purchases/orders/')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)

    def test_purchase_order_actions_follow_business_transitions(self):
        response = self.client.post(
            '/api/v1/purchase-orders/',
            {
                'supplier': self.supplier.id,
                'reference': 'PO-ACTIONS-001',
                'items': [{'product': self.product.id, 'quantity': 2, 'unit_cost': '100000.00'}],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        order_id = response.data['id']

        self.assertEqual(self.client.post(f'/api/v1/purchase-orders/{order_id}/send/', format='json').status_code, 200)
        self.assertEqual(self.client.post(f'/api/v1/purchase-orders/{order_id}/confirm/', format='json').status_code, 200)
        self.assertEqual(self.client.post(f'/api/v1/purchase-orders/{order_id}/close/', format='json').status_code, 409)
        self.assertEqual(self.client.post(f'/api/v1/purchase-orders/{order_id}/send/', format='json').status_code, 409)

    def test_create_then_validate_purchase_receipt_updates_stock_and_costs(self):
        order = self.create_approved_order(
            'PO-2026-003',
            [{'product': self.product.id, 'quantity': 4, 'unit_cost': '200000.00'}],
        )

        response = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order.data['id'],
                'location': self.location.id,
                'reference': 'RCPT-2026-001',
                'received_date': '2026-09-12T10:00:00Z',
                'status': 'received',
                'items': [
                    {'product': self.product.id, 'quantity_received': 4, 'unit_cost': '200000.00'}
                ],
                'transport_cost': '5000.00',
                'customs_cost': '3000.00',
                'insurance_cost': '2000.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(float(response.data['total_cost']), 810000.0)
        self.assertEqual(float(response.data['items'][0]['real_unit_cost']), 202500.0)
        self.assertEqual(response.data['status'], 'draft')
        self.assertFalse(self.product.stock_items.exists())

        stock_user = User.objects.create_user(
            username='receipt_stock_validation',
            role='stock',
            pin_code='2222',
        )
        self.client.force_authenticate(user=stock_user)
        denied_validation = self.client.post(
            f"/api/v1/receipts/{response.data['id']}/validate/",
            format='json',
        )
        self.assertEqual(denied_validation.status_code, 403)
        submitted = self.client.post(
            f"/api/v1/receipts/{response.data['id']}/submit/",
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        validation = self.admin_client.post(
            f"/api/v1/receipts/{response.data['id']}/validate/",
            {
                'version': submitted.data['version'],
                'reviewed_item_ids': [item['id'] for item in submitted.data['items']],
            },
            format='json',
        )
        self.assertEqual(validation.status_code, 200)
        self.assertEqual(validation.data['status'], 'received')
        self.assertEqual(self.product.stock_items.get().quantity, 4)
        cost_layer = InventoryCostLayer.objects.get(
            product=self.product,
            location=self.product.stock_items.get().location,
            reference='RCPT-2026-001',
        )
        self.assertEqual(cost_layer.quantity_remaining, 4)
        self.assertEqual(cost_layer.unit_cost, 202500)
        cartons = Carton.objects.filter(purchase_receipt_id=response.data['id'])
        self.assertEqual(cartons.count(), 1)
        self.assertEqual(cartons.get().quantity, 4)
        self.assertEqual(cartons.get().initial_quantity, 4)
        self.assertTrue(cartons.get().qr_code.startswith('KAP-CTN-'))

        repeated_validation = self.admin_client.post(
            f"/api/v1/receipts/{response.data['id']}/validate/",
            {
                'version': submitted.data['version'],
                'reviewed_item_ids': [item['id'] for item in submitted.data['items']],
            },
            format='json',
        )
        self.assertEqual(repeated_validation.status_code, 409)
        self.assertTrue(AuditLog.objects.filter(model_name='PurchaseReceipt', action='stock', record_id=response.data['id']).exists())

    def test_receipt_packaging_creates_full_and_partial_cartons(self):
        order = self.create_approved_order(
            'PO-2026-CARTONS',
            [{'product': self.product.id, 'quantity': 12, 'unit_cost': '200000.00'}],
        )
        receipt = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order.data['id'],
                'location': self.location.id,
                'reference': 'RCPT-2026-CARTONS',
                'items': [{
                    'product': self.product.id,
                    'quantity_received': 12,
                    'unit_cost': '200000.00',
                    'items_per_carton': 5,
                    'supplier_reference': 'SUP-REF-12',
                    'supplier_barcode': '1234567890123',
                }],
            },
            format='json',
        )

        self.assertEqual(receipt.status_code, 201)
        submitted = self.client.post(
            f"/api/v1/receipts/{receipt.data['id']}/submit/",
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        validation = self.admin_client.post(
            f"/api/v1/receipts/{receipt.data['id']}/validate/",
            {
                'version': submitted.data['version'],
                'reviewed_item_ids': [item['id'] for item in submitted.data['items']],
            },
            format='json',
        )
        self.assertEqual(validation.status_code, 200)

        cartons = list(Carton.objects.filter(purchase_receipt_id=receipt.data['id']).order_by('id'))
        self.assertEqual([carton.quantity for carton in cartons], [5, 5, 2])
        self.assertEqual(len({carton.qr_code for carton in cartons}), 3)
        self.assertTrue(all(carton.initial_quantity == carton.quantity for carton in cartons))
        self.assertTrue(all(carton.supplier_reference == 'SUP-REF-12' for carton in cartons))
        self.assertTrue(all(carton.supplier_barcode == '1234567890123' for carton in cartons))

    def test_partial_receipt_keeps_order_open(self):
        order_response = self.create_approved_order(
            'PO-2026-PARTIAL',
            [{'product': self.product.id, 'quantity': 10, 'unit_cost': '200000.00'}],
        )

        response = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order_response.data['id'],
                'reference': 'RCPT-2026-PARTIAL',
                'items': [{'product': self.product.id, 'quantity_received': 4, 'unit_cost': '200000.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'draft')
        order_detail = self.client.get(f"/api/purchases/orders/{order_response.data['id']}/")
        self.assertEqual(order_detail.data['status'], 'approved')

    def test_acquisition_costs_endpoint_exposes_real_costs(self):
        order_response = self.create_approved_order(
            'PO-2026-ACQ',
            [{'product': self.product.id, 'quantity': 2, 'unit_cost': '150000.00'}],
            endpoint='/api/v1/purchase-orders/',
        )

        receipt_response = self.client.post(
            '/api/v1/receipts/',
            {
                'purchase_order': order_response.data['id'],
                'reference': 'RCPT-2026-ACQ',
                'items': [{'product': self.product.id, 'quantity_received': 2, 'unit_cost': '150000.00'}],
                'transport_cost': '5000.00',
                'customs_cost': '3000.00',
            },
            format='json',
        )

        self.assertEqual(receipt_response.status_code, 201)

        response = self.client.get('/api/v1/acquisition-costs/')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data['count'], 1)

        detail_response = self.client.get(f"/api/v1/acquisition-costs/{receipt_response.data['id']}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(float(detail_response.data['total_cost']), 308000.0)
        self.assertEqual(float(detail_response.data['items'][0]['real_unit_cost']), 154000.0)

    def test_acquisition_costs_endpoint_supports_create_and_patch(self):
        order_response = self.create_approved_order(
            'PO-2026-ACQ-UPDATE',
            [{'product': self.product.id, 'quantity': 2, 'unit_cost': '150000.00'}],
            endpoint='/api/v1/purchase-orders/',
        )

        create_response = self.client.post(
            '/api/v1/acquisition-costs/',
            {
                'purchase_order': order_response.data['id'],
                'reference': 'RCPT-2026-ACQ-UPDATE',
                'items': [{'product': self.product.id, 'quantity_received': 2, 'unit_cost': '150000.00'}],
                'transport_cost': '5000.00',
                'customs_cost': '3000.00',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)

        patch_response = self.client.patch(
            f"/api/v1/acquisition-costs/{create_response.data['id']}/",
            {'transport_cost': '8000.00'},
            format='json',
        )

        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(float(patch_response.data['transport_cost']), 8000.0)

    def test_receipt_supports_value_based_allocation_method(self):
        product_b = Product.objects.create(
            sku='ACH-002',
            name='Écran de travail',
            purchase_price='200000',
            selling_price='300000',
            quantity=0,
            alert_threshold=2,
        )

        order_response = self.create_approved_order(
            'PO-2026-ALLOC',
            [
                {'product': self.product.id, 'quantity': 2, 'unit_cost': '100000.00'},
                {'product': product_b.id, 'quantity': 1, 'unit_cost': '200000.00'},
            ],
        )

        receipt_response = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order_response.data['id'],
                'reference': 'RCPT-2026-ALLOC',
                'allocation_method': 'value',
                'items': [
                    {'product': self.product.id, 'quantity_received': 2, 'unit_cost': '100000.00'},
                    {'product': product_b.id, 'quantity_received': 1, 'unit_cost': '200000.00'},
                ],
                'transport_cost': '6000.00',
                'customs_cost': '4000.00',
            },
            format='json',
        )

        self.assertEqual(receipt_response.status_code, 201)
        self.assertEqual(receipt_response.data['allocation_method'], 'value')
        self.assertEqual(float(receipt_response.data['items'][0]['real_unit_cost']), 102500.0)
        self.assertEqual(float(receipt_response.data['items'][1]['real_unit_cost']), 205000.0)

    def test_receipt_supports_weight_and_volume_allocation_methods(self):
        product_b = Product.objects.create(
            sku='ACH-002',
            name='Écran de travail',
            purchase_price='200000',
            selling_price='300000',
            quantity=0,
            alert_threshold=2,
            weight='1.00',
            volume='2.00',
        )
        self.product.weight = '2.00'
        self.product.volume = '4.00'
        self.product.save(update_fields=['weight', 'volume'])

        order_response = self.create_approved_order(
            'PO-2026-ALLOC-WV',
            [
                {'product': self.product.id, 'quantity': 2, 'unit_cost': '100000.00'},
                {'product': product_b.id, 'quantity': 1, 'unit_cost': '200000.00'},
            ],
        )

        for allocation_method, expected_values in [
            ('weight', [104000.0, 202000.0]),
            ('volume', [104000.0, 202000.0]),
        ]:
            receipt_response = self.client.post(
                '/api/purchases/receipts/',
                {
                    'purchase_order': order_response.data['id'],
                    'reference': f'RCPT-2026-ALLOC-{allocation_method.upper()}',
                    'allocation_method': allocation_method,
                    'items': [
                        {'product': self.product.id, 'quantity_received': 2, 'unit_cost': '100000.00'},
                        {'product': product_b.id, 'quantity_received': 1, 'unit_cost': '200000.00'},
                    ],
                    'transport_cost': '6000.00',
                    'customs_cost': '4000.00',
                },
                format='json',
            )

            self.assertEqual(receipt_response.status_code, 201)
            self.assertEqual(receipt_response.data['allocation_method'], allocation_method)
            self.assertEqual(float(receipt_response.data['items'][0]['real_unit_cost']), expected_values[0])
            self.assertEqual(float(receipt_response.data['items'][1]['real_unit_cost']), expected_values[1])

    def test_partial_damaged_receipt_is_quarantined_and_later_release_is_audited(self):
        order = self.create_approved_order(
            'PO-DAMAGED-PARTIAL',
            [{'product': self.product.id, 'quantity': 100, 'unit_cost': '100.00'}],
        )
        first_receipt = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order.data['id'],
                'location': self.location.id,
                'reference': 'RCPT-DAMAGED-92',
                'items': [{
                    'product': self.product.id,
                    'quantity_received': 92,
                    'quantity_accepted': 88,
                    'quantity_quarantined': 4,
                    'discrepancy_reason': 'Quatre filtres sont endommagés.',
                    'unit_cost': '100.00',
                }],
            },
            format='json',
        )
        self.assertEqual(first_receipt.status_code, 201, first_receipt.data)
        submitted = self.client.post(
            f"/api/purchases/receipts/{first_receipt.data['id']}/submit/",
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertFalse(StockItem.objects.filter(product=self.product, location=self.location).exists())
        validated = self.admin_client.post(
            f"/api/purchases/receipts/{first_receipt.data['id']}/validate/",
            {
                'version': submitted.data['version'],
                'reviewed_item_ids': [line['id'] for line in submitted.data['items']],
            },
            format='json',
        )
        self.assertEqual(validated.status_code, 200, validated.data)
        self.assertEqual(StockItem.objects.get(product=self.product, location=self.location).quantity, 88)
        self.assertEqual(
            PurchaseReceipt.objects.get(pk=first_receipt.data['id']).purchase_order.status,
            'partial_received',
        )

        second_receipt = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order.data['id'],
                'location': self.location.id,
                'reference': 'RCPT-DAMAGED-8',
                'items': [{
                    'product': self.product.id,
                    'quantity_received': 8,
                    'unit_cost': '100.00',
                }],
            },
            format='json',
        )
        self.assertEqual(second_receipt.status_code, 201, second_receipt.data)
        second_validated = self.submit_and_validate_receipt(second_receipt.data['id'])
        self.assertEqual(second_validated.data['status'], 'received')
        self.assertEqual(StockItem.objects.get(product=self.product, location=self.location).quantity, 96)

        quarantine = self.admin_client.get('/api/purchases/quarantines/')
        self.assertEqual(quarantine.status_code, 200)
        quarantine_data = quarantine.data.get('results', quarantine.data)[0]
        release = self.admin_client.post(
            f"/api/purchases/quarantines/{quarantine_data['id']}/release/",
            {'quantity': 2, 'reason': 'Contrôle conforme après nettoyage.'},
            format='json',
        )
        self.assertEqual(release.status_code, 200, release.data)
        self.assertEqual(release.data['quantity_remaining'], 2)
        self.assertEqual(release.data['status'], 'partially_released')
        self.assertEqual(StockItem.objects.get(product=self.product, location=self.location).quantity, 98)
        available_cost = sum(
            InventoryCostLayer.objects.filter(
                product=self.product,
                location=self.location,
                is_available=True,
            ).values_list('quantity_remaining', flat=True),
        )
        self.assertEqual(available_cost, 98)

    def test_rejected_receipt_never_changes_official_stock(self):
        order = self.create_approved_order(
            'PO-REJECTED-RECEIPT',
            [{'product': self.product.id, 'quantity': 2, 'unit_cost': '100.00'}],
        )
        receipt = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': order.data['id'],
                'location': self.location.id,
                'reference': 'RCPT-REJECTED',
                'items': [{'product': self.product.id, 'quantity_received': 2}],
            },
            format='json',
        )
        self.assertEqual(receipt.status_code, 201, receipt.data)
        submitted = self.client.post(
            f"/api/purchases/receipts/{receipt.data['id']}/submit/",
            format='json',
        )
        self.assertEqual(submitted.status_code, 200, submitted.data)
        rejected = self.admin_client.post(
            f"/api/purchases/receipts/{receipt.data['id']}/decision/reject/",
            {'reason': 'Le produit ne correspond pas au bon de commande.'},
            format='json',
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(rejected.data['status'], 'rejected')
        validate = self.admin_client.post(
            f"/api/purchases/receipts/{receipt.data['id']}/validate/",
            {
                'version': submitted.data['version'],
                'reviewed_item_ids': [line['id'] for line in submitted.data['items']],
            },
            format='json',
        )
        self.assertEqual(validate.status_code, 409)
        self.assertFalse(StockItem.objects.filter(product=self.product, location=self.location).exists())


class PurchaseTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.get(slug='kourouma-auto-parts')
        self.tenant_b = Tenant.objects.create(
            slug='purchases-tenant-b',
            name='Achats Tenant B',
            status='active',
        )
        self.user = User.objects.create_user(
            username='purchases_tenant_a_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant_a,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.supplier_a = Supplier.objects.create(
            name='Fournisseur A',
            tenant=self.tenant_a,
        )
        self.supplier_b = Supplier.objects.create(
            name='Fournisseur B',
            tenant=self.tenant_b,
        )
        self.product_a = Product.objects.create(
            sku='PUR-TENANT-A',
            name='Produit A',
            quantity=0,
            alert_threshold=10,
            tenant=self.tenant_a,
        )
        self.product_b = Product.objects.create(
            sku='PUR-TENANT-B',
            name='Produit B',
            quantity=0,
            alert_threshold=2,
            tenant=self.tenant_b,
        )
        self.order_a = self.create_order(
            self.tenant_a,
            self.supplier_a,
            self.product_a,
            'PO-TENANT-A',
        )
        self.order_b = self.create_order(
            self.tenant_b,
            self.supplier_b,
            self.product_b,
            'PO-TENANT-B',
        )
        self.receipt_a = self.create_receipt(
            self.order_a,
            self.product_a,
            'RCPT-TENANT-A',
        )
        self.receipt_b = self.create_receipt(
            self.order_b,
            self.product_b,
            'RCPT-TENANT-B',
        )
        self.quarantine_a = self.create_quarantine(self.receipt_a)
        self.quarantine_b = self.create_quarantine(self.receipt_b)

    def create_order(self, tenant, supplier, product, reference):
        order = PurchaseOrder.objects.create(
            tenant=tenant,
            supplier=supplier,
            reference=reference,
            status='approved',
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            product=product,
            quantity=3,
            unit_cost=100,
        )
        return order

    def create_receipt(self, order, product, reference):
        receipt = PurchaseReceipt.objects.create(
            purchase_order=order,
            reference=reference,
            status='received',
            created_by=self.user,
        )
        item = PurchaseReceiptItem.objects.create(
            purchase_receipt=receipt,
            product=product,
            quantity_received=1,
            quantity_accepted=1,
            unit_cost=100,
        )
        receipt.test_item = item
        return receipt

    def create_quarantine(self, receipt):
        location = InventoryLocation.objects.create(
            name=f'Quarantaine {receipt.reference}',
            code=f'Q-{receipt.reference}',
            location_type='warehouse',
        )
        return ReceiptQuarantine.objects.create(
            receipt_item=receipt.test_item,
            location=location,
            quantity=1,
            quantity_remaining=1,
            reason='Contrôle qualité',
        )

    def test_orders_receipts_quarantines_and_purchase_report_are_tenant_scoped(self):
        orders = self.client.get('/api/purchases/orders/')
        receipts = self.client.get('/api/purchases/receipts/')
        acquisition_costs = self.client.get('/api/v1/acquisition-costs/')
        quarantines = self.client.get('/api/purchases/quarantines/')
        replenishment = self.client.get(
            '/api/v1/purchase-orders/replenishment-suggestions/',
        )
        report = self.client.get('/api/v1/reports/purchases/')

        self.assertEqual(orders.status_code, 200)
        self.assertEqual(receipts.status_code, 200)
        self.assertEqual(acquisition_costs.status_code, 200)
        self.assertEqual(quarantines.status_code, 200)
        self.assertEqual(replenishment.status_code, 200)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(
            {item['id'] for item in orders.data.get('results', orders.data)},
            {self.order_a.pk},
        )
        self.assertEqual(
            {item['id'] for item in receipts.data.get('results', receipts.data)},
            {self.receipt_a.pk},
        )
        self.assertEqual(
            {item['id'] for item in acquisition_costs.data.get('results', acquisition_costs.data)},
            {self.receipt_a.pk},
        )
        self.assertEqual(
            {item['id'] for item in quarantines.data.get('results', quarantines.data)},
            {self.quarantine_a.pk},
        )
        self.assertEqual(
            {item['product_id'] for item in replenishment.data['suggestions']},
            {self.product_a.pk},
        )
        self.assertEqual(
            {item['supplier_id'] for item in report.data['suppliers']},
            {self.supplier_a.pk},
        )

        self.assertEqual(
            self.client.get(f'/api/purchases/orders/{self.order_b.pk}/').status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/purchases/orders/{self.order_b.pk}/send/',
                format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f'/api/purchases/receipts/{self.receipt_b.pk}/').status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/purchases/receipts/{self.receipt_b.pk}/submit/',
                format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/purchases/receipts/{self.receipt_b.pk}/decision/reject/',
                {'reason': 'Hors périmètre'},
                format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/purchases/receipts/{self.receipt_b.pk}/validate/',
                {},
                format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f'/api/v1/acquisition-costs/{self.receipt_b.pk}/',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/purchases/quarantines/{self.quarantine_b.pk}/release/',
                {'quantity': 1, 'reason': 'Hors périmètre'},
                format='json',
            ).status_code,
            404,
        )

    def test_order_creation_rejects_foreign_supplier_and_foreign_product(self):
        foreign_supplier = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier_b.pk,
                'reference': 'PO-FOREIGN-SUPPLIER',
                'items': [{
                    'product': self.product_b.pk,
                    'quantity': 1,
                    'unit_cost': '100',
                }],
            },
            format='json',
        )
        foreign_product = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier_a.pk,
                'reference': 'PO-FOREIGN-PRODUCT',
                'items': [{
                    'product': self.product_b.pk,
                    'quantity': 1,
                    'unit_cost': '100',
                }],
            },
            format='json',
        )
        own_order = self.client.post(
            '/api/purchases/orders/',
            {
                'supplier': self.supplier_a.pk,
                'reference': 'PO-CREATED-TENANT-A',
                'items': [{
                    'product': self.product_a.pk,
                    'quantity': 1,
                    'unit_cost': '100',
                }],
            },
            format='json',
        )

        self.assertEqual(foreign_supplier.status_code, 400)
        self.assertEqual(foreign_product.status_code, 400)
        self.assertEqual(own_order.status_code, 201, own_order.data)
        self.assertEqual(
            PurchaseOrder.objects.get(pk=own_order.data['id']).tenant_id,
            self.tenant_a.pk,
        )

    def test_receipt_creation_rejects_foreign_purchase_order(self):
        response = self.client.post(
            '/api/purchases/receipts/',
            {
                'purchase_order': self.order_b.pk,
                'reference': 'RCPT-FOREIGN-ORDER',
                'items': [{
                    'product': self.product_b.pk,
                    'quantity_received': 1,
                }],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            PurchaseReceipt.objects.filter(reference='RCPT-FOREIGN-ORDER').exists(),
        )


class ExternalPurchaseWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.get(slug='kourouma-auto-parts')
        self.user = User.objects.create_user(
            username='external_purchase_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.supplier = Supplier.objects.create(
            name='Commerçant voisin',
            phone='+224600003000',
            tenant=self.tenant,
        )
        self.customer = Customer.objects.create(
            full_name='Client externe',
            phone='+224600004000',
            tenant=self.tenant,
        )
        self.account = FinancialAccount.objects.create(
            name='Caisse règlements externes',
            account_type='cash',
            currency='GNF',
            opening_balance='1000000.00',
            tenant=self.tenant,
        )
        self.warehouse = InventoryLocation.objects.create(
            name='Entrepôt articles ponctuels',
            code='EXTERNAL-PURCHASE-WH',
            location_type='warehouse',
            tenant=self.tenant,
        )

    def create_external_sale(self):
        response = self.client.post(
            '/api/v1/external-sales/',
            {
                'customer': self.customer.pk,
                'supplier': self.supplier.pk,
                'sale_payment_method': 'credit',
                'sale_amount_paid': '0.00',
                'items': [
                    {
                        'item_name': 'Alternateur hors catalogue',
                        'item_reference': 'ALT-EXT-01',
                        'quantity': 2,
                        'unit_price': '180000.00',
                        'unit_cost': '150000.00',
                        'purchase_quantity': 2,
                        'additional_cost': '0.00',
                        'delivery_mode': 'direct',
                    },
                    {
                        'item_name': 'Démarreur ponctuel',
                        'item_reference': 'DEM-EXT-02',
                        'quantity': 1,
                        'unit_price': '130000.00',
                        'unit_cost': '100000.00',
                        'purchase_quantity': 1,
                        'additional_cost': '0.00',
                        'delivery_mode': 'warehouse',
                    },
                ],
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='external-sale-purchase-test',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_external_invoice_and_supplier_purchase_preserve_catalog_and_stock(self):
        response = self.create_external_sale()
        sale = Sale.objects.get(pk=response.data['sale']['id'])
        self.assertTrue(sale.is_external)
        self.assertEqual(sale.items.count(), 2)
        self.assertTrue(all(item.product_id is None for item in sale.items.all()))
        self.assertEqual(
            [item['product_name'] for item in response.data['sale']['items']],
            ['Alternateur hors catalogue', 'Démarreur ponctuel'],
        )
        self.assertEqual(
            [line['description'] for line in sale.invoice.document_snapshot['items']],
            ['Alternateur hors catalogue', 'Démarreur ponctuel'],
        )
        self.assertEqual(ExternalPurchase.objects.filter(sale=sale).count(), 2)
        summary = self.client.get('/api/v1/external-purchases/summary/')
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data['purchase_total'], Decimal('400000.00'))
        self.assertEqual(summary.data['balance_due'], Decimal('400000.00'))
        self.assertFalse(StockItem.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_mixed_sale_creates_only_line_linked_external_purchase_and_preserves_stock(self):
        shop = InventoryLocation.objects.create(
            name='Boutique vente mixte',
            code='MIXED-SALE-SHOP',
            location_type='shop',
            tenant=self.tenant,
        )
        product = Product.objects.create(
            sku='MIX-001',
            name='Filtre catalogue',
            purchase_price='10000.00',
            selling_price='18000.00',
            quantity=4,
            tenant=self.tenant,
        )
        stock_item = StockItem.objects.create(
            product=product,
            location=shop,
            quantity=4,
        )
        due_date = (timezone.localdate() + timedelta(days=5)).isoformat()

        response = self.client.post(
            '/api/v1/sales/',
            {
                'customer': self.customer.pk,
                'location': shop.pk,
                'payment_method': 'credit',
                'status': 'partial',
                'amount_paid': '0.00',
                'items': [
                    {
                        'product': product.pk,
                        'quantity': 2,
                        'unit_price': '18000.00',
                    },
                    {
                        'product': None,
                        'item_name': 'Pompe à eau ponctuelle',
                        'item_reference': 'POMPE-EXT-1',
                        'quantity': 1,
                        'unit_price': '50000.00',
                        'external_purchase': {
                            'supplier': self.supplier.pk,
                            'unit_cost': '35000.00',
                            'additional_cost': '1500.00',
                            'delivery_mode': 'direct',
                            'payment_terms': 'deferred',
                            'due_date': due_date,
                        },
                    },
                ],
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='mixed-sale-external-purchase-test',
        )

        self.assertEqual(response.status_code, 201, response.data)
        sale = Sale.objects.get(pk=response.data['id'])
        sale_items = list(sale.items.order_by('id'))
        purchase = ExternalPurchase.objects.get(sale=sale)
        stock_item.refresh_from_db()
        product.refresh_from_db()

        self.assertFalse(sale.is_external)
        self.assertEqual(len(sale_items), 2)
        self.assertEqual(stock_item.quantity, 2)
        self.assertEqual(product.quantity, 2)
        self.assertEqual(StockMovement.objects.filter(reference=f'SALE-{sale.pk}').count(), 1)
        self.assertEqual(purchase.sale_item_id, sale_items[1].pk)
        self.assertEqual(purchase.quantity, sale_items[1].quantity)
        self.assertEqual(purchase.balance_due, Decimal('36500.00'))
        self.assertEqual(sale_items[1].cost_total, Decimal('36500.00'))
        self.assertEqual(ExternalPurchasePayment.objects.count(), 0)
        self.assertEqual(
            [item['description'] for item in sale.invoice.document_snapshot['items']],
            ['Filtre catalogue', 'Pompe à eau ponctuelle'],
        )

    def test_sales_role_can_load_minimal_external_supplier_choices(self):
        sales_user = User.objects.create_user(
            username='external_purchase_sales',
            password='secret123',
            role='sales',
            tenant=self.tenant,
        )
        sales_client = APIClient()
        sales_client.force_authenticate(user=sales_user)

        response = sales_client.get('/api/v1/sales/external-suppliers/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, [{'id': self.supplier.pk, 'name': self.supplier.name}])

    def test_purchase_report_includes_external_supplier_debt_without_treating_it_as_stock(self):
        self.create_external_sale()

        response = self.client.get('/api/v1/reports/purchases/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['summary']['external_purchase_count'], 2)
        self.assertEqual(response.data['summary']['external_purchase_quantity'], 3)
        self.assertEqual(response.data['summary']['external_purchase_amount'], 400000.0)
        self.assertEqual(response.data['summary']['external_paid_amount'], 0)
        self.assertEqual(response.data['summary']['external_balance_due'], 400000.0)
        self.assertTrue(response.data['summary']['external_purchases_are_not_stock'])
        finance_report = self.client.get('/api/v1/reports/finance/')
        self.assertEqual(finance_report.status_code, 200, finance_report.data)
        self.assertEqual(finance_report.data['external_supplier_payables'], 400000.0)
        supplier = next(
            item for item in response.data['suppliers']
            if item['supplier_id'] == self.supplier.pk
        )
        self.assertEqual(supplier['external_balance_due'], 400000.0)

    def test_direct_delivery_does_not_create_internal_stock_movements(self):
        response = self.create_external_sale()
        direct_purchase = ExternalPurchase.objects.get(
            pk=response.data['purchases'][0]['id'],
        )
        delivery = self.client.post(
            f'/api/v1/external-purchases/{direct_purchase.pk}/movements/',
            {
                'movement_type': 'direct_delivery',
                'quantity': 2,
                'reference': 'DELIVERY-DIRECT-001',
                'proof_reference': 'BL-CLIENT-001',
            },
            format='json',
        )
        self.assertEqual(delivery.status_code, 201, delivery.data)
        self.assertEqual(delivery.data['location'], None)
        self.assertFalse(StockItem.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_warehouse_goods_are_received_before_delivery_and_not_catalogued(self):
        response = self.create_external_sale()
        warehouse_purchase = ExternalPurchase.objects.get(
            pk=response.data['purchases'][1]['id'],
        )
        receive = self.client.post(
            f'/api/v1/external-purchases/{warehouse_purchase.pk}/movements/',
            {
                'movement_type': 'received',
                'location': self.warehouse.pk,
                'quantity': 1,
                'reference': 'RECEIVE-WH-001',
            },
            format='json',
        )
        self.assertEqual(receive.status_code, 201, receive.data)
        delivery = self.client.post(
            f'/api/v1/external-purchases/{warehouse_purchase.pk}/movements/',
            {
                'movement_type': 'delivered',
                'location': self.warehouse.pk,
                'quantity': 1,
                'reference': 'DELIVERY-WH-001',
            },
            format='json',
        )
        self.assertEqual(delivery.status_code, 201, delivery.data)
        duplicate_delivery = self.client.post(
            f'/api/v1/external-purchases/{warehouse_purchase.pk}/movements/',
            {
                'movement_type': 'delivered',
                'location': self.warehouse.pk,
                'quantity': 1,
            },
            format='json',
        )
        self.assertEqual(duplicate_delivery.status_code, 400)
        self.assertFalse(StockItem.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertEqual(
            ExternalPurchaseMovement.objects.filter(purchase=warehouse_purchase).count(),
            2,
        )

    def test_grouped_partial_payments_create_one_cash_transaction_each(self):
        response = self.create_external_sale()
        first_purchase, second_purchase = [
            ExternalPurchase.objects.get(pk=item['id'])
            for item in response.data['purchases']
        ]
        payment_payload = {
            'supplier': self.supplier.pk,
            'purchase_ids': [first_purchase.pk, second_purchase.pk],
            'amount': '250000.00',
            'payment_method': 'cash',
            'financial_account': self.account.pk,
            'proof_reference': 'RECU-PAIEMENT-001',
        }
        first_payment_response = self.client.post(
            '/api/v1/external-payments/',
            payment_payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='external-payment-partial-1',
        )
        self.assertEqual(first_payment_response.status_code, 201, first_payment_response.data)
        first_payment = ExternalPurchasePayment.objects.get(
            pk=first_payment_response.data['id'],
        )
        self.assertEqual(
            list(first_payment.allocations.values_list('purchase_id', 'amount')),
            [(first_purchase.pk, Decimal('250000.00'))],
        )
        self.assertEqual(first_purchase.balance_due, Decimal('50000.00'))
        self.assertEqual(second_purchase.balance_due, Decimal('100000.00'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, Decimal('750000.00'))
        self.assertEqual(
            FinancialTransaction.objects.filter(origin=first_payment.reference).count(),
            1,
        )
        partial_report = self.client.get('/api/v1/reports/purchases/')
        self.assertEqual(partial_report.status_code, 200, partial_report.data)
        self.assertEqual(partial_report.data['summary']['external_paid_amount'], 250000.0)
        self.assertEqual(partial_report.data['summary']['external_balance_due'], 150000.0)
        partial_finance_report = self.client.get('/api/v1/reports/finance/')
        self.assertEqual(partial_finance_report.status_code, 200, partial_finance_report.data)
        self.assertEqual(
            partial_finance_report.data['external_supplier_payables'],
            150000.0,
        )

        payment_payload['amount'] = '150000.00'
        payment_payload['proof_reference'] = 'RECU-PAIEMENT-002'
        second_payment_response = self.client.post(
            '/api/v1/external-payments/',
            payment_payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='external-payment-partial-2',
        )
        self.assertEqual(second_payment_response.status_code, 201, second_payment_response.data)
        first_purchase.refresh_from_db()
        second_purchase.refresh_from_db()
        self.assertEqual(first_purchase.balance_due, Decimal('0.00'))
        self.assertEqual(second_purchase.balance_due, Decimal('0.00'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, Decimal('600000.00'))
        self.assertEqual(ExternalPurchasePayment.objects.count(), 2)
        self.assertEqual(
            ExternalPurchasePaymentAllocation.objects.filter(
                payment_id=second_payment_response.data['id'],
            ).count(),
            2,
        )
        self.assertEqual(
            FinancialTransaction.objects.filter(
                transaction_type='payment',
                origin__startswith='FPP-',
            ).count(),
            2,
        )
        settled_report = self.client.get('/api/v1/reports/purchases/')
        self.assertEqual(settled_report.status_code, 200, settled_report.data)
        self.assertEqual(settled_report.data['summary']['external_paid_amount'], 400000.0)
        self.assertEqual(settled_report.data['summary']['external_balance_due'], 0)
        settled_finance_report = self.client.get('/api/v1/reports/finance/')
        self.assertEqual(settled_finance_report.status_code, 200, settled_finance_report.data)
        self.assertEqual(settled_finance_report.data['external_supplier_payables'], 0)
