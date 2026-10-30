from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from pypdf import PdfReader
from django.utils import timezone
from PIL import Image, ImageDraw

from core.models import Company, Tenant
from customers.models import Customer
from products.models import Product
from sales.models import Invoice, Sale
from users.models import User


def create_test_signing_material(directory):
    now = timezone.now()
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'KAP Test Root')])
    signing_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'KAP Test Invoice Signer')])

    def make_certificate(subject, public_key, issuer, issuer_key, serial, is_ca):
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(public_key)
            .serial_number(serial)
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=is_ca,
                    crl_sign=is_ca,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .sign(issuer_key, hashes.SHA256())
        )

    root_certificate = make_certificate(root_name, root_key.public_key(), root_name, root_key, 1, True)
    signing_certificate = make_certificate(
        signing_name,
        signing_key.public_key(),
        root_name,
        root_key,
        2,
        False,
    )
    password = b'visual-test-secret'
    p12_path = Path(directory) / 'invoice-test.p12'
    root_path = Path(directory) / 'trusted-root.pem'
    p12_path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b'KAP invoice test',
            signing_key,
            signing_certificate,
            [root_certificate],
            serialization.BestAvailableEncryption(password),
        )
    )
    root_path.write_bytes(root_certificate.public_bytes(serialization.Encoding.PEM))
    return p12_path, root_path, password.decode()


class InvoiceApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='invoice_sales',
            password='secret123',
            pin_code='1234',
            role='sales',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.customer = Customer.objects.create(full_name='Aly Diallo', phone='+224600010001')
        self.product = Product.objects.create(
            sku='INV-001',
            name='Produit facture',
            brand='NEXORA',
            purchase_price='25000',
            selling_price='40000',
            quantity=5,
            alert_threshold=1,
        )

    def test_invoice_list_endpoint_exposes_invoice_data(self):
        from sales.models import Invoice

        sale = Sale.objects.create(
            customer=self.customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('40000.00'),
        )
        sale.items.create(product=self.product, quantity=1, unit_price=Decimal('40000.00'))

        invoice = Invoice.objects.create(
            sale=sale,
            invoice_number='INV-TEST-0001',
            total_amount=sale.total_amount,
            paid_amount=sale.amount_paid,
        )
        invoice.generate_qr_code()
        invoice.save(update_fields=['qr_code'])

        response = self.client.get('/api/invoices/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data['results']) >= 1)
        self.assertTrue(
            any(
                item['invoice_number'] == invoice.invoice_number
                for item in response.data['results']
            )
        )

    def test_invoice_pdf_and_qr_endpoints(self):
        from sales.models import Invoice

        sale = Sale.objects.create(
            customer=self.customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('40000.00'),
        )
        invoice = Invoice.objects.create(
            sale=sale,
            invoice_number='INV-PDF-0001',
            total_amount=sale.total_amount,
            paid_amount=sale.amount_paid,
        )

        pdf_response = self.client.get(f'/api/v1/invoices/{invoice.id}/pdf/')
        qr_response = self.client.get(f'/api/v1/invoices/{invoice.id}/qr/')

        self.assertEqual(pdf_response.status_code, 409)
        self.assertIn('signé', pdf_response.data['detail'])
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response.data['qr_code'], invoice.qr_code)

    def test_invoice_verification_token_is_secure_and_publicly_resolvable(self):
        from sales.models import Invoice

        sale = Sale.objects.create(
            customer=self.customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('40000.00'),
        )
        invoice = Invoice.objects.create(
            sale=sale,
            invoice_number='INV-VERIFY-0001',
            total_amount=sale.total_amount,
            paid_amount=sale.amount_paid,
        )

        verify_response = self.client.get(f'/api/invoices/verify/{invoice.verification_token}/')
        qr_image_response = self.client.get(f'/api/invoices/{invoice.id}/qr-image/')

        self.assertEqual(verify_response.status_code, 200)
        self.assertFalse(verify_response.data['valid'])
        self.assertFalse(verify_response.data['signature_valid'])
        self.assertEqual(verify_response.data['signature_status'], 'unsigned')
        self.assertEqual(verify_response.data['invoice_number'], invoice.invoice_number)
        self.assertEqual(qr_image_response.status_code, 200)
        self.assertEqual(qr_image_response['Content-Type'], 'image/png')

    def test_cancelled_invoice_verification_remains_resolvable(self):
        from sales.models import Invoice

        sale = Sale.objects.create(
            customer=self.customer,
            status='cancelled',
            payment_method='cash',
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('0.00'),
        )
        invoice = Invoice.objects.create(
            sale=sale,
            invoice_number='INV-CANCELLED-0001',
            total_amount=sale.total_amount,
            paid_amount=sale.amount_paid,
        )

        response = self.client.get(f'/api/invoices/verify/{invoice.verification_token}/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['valid'])
        self.assertEqual(response.data['status'], 'cancelled')

    def test_invoice_verification_url_uses_frontend_verification_route(self):
        from django.conf import settings
        from invoices.serializers import invoice_verification_url
        from sales.models import Invoice

        sale = Sale.objects.create(
            customer=self.customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('40000.00'),
        )
        invoice = Invoice.objects.create(sale=sale)

        self.assertEqual(
            invoice_verification_url(invoice),
            f'{settings.INVOICE_VERIFICATION_BASE_URL}{invoice.verification_token}',
        )
        self.assertIn('/verifier/', settings.INVOICE_VERIFICATION_BASE_URL)

    def test_invoice_number_and_company_stamp_are_generated_for_business_invoice(self):
        sale = Sale.objects.create(
            customer=self.customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('40000.00'),
        )

        invoice = Invoice.objects.create(
            sale=sale,
            total_amount=sale.total_amount,
            paid_amount=sale.amount_paid,
            validated_by=self.user,
        )

        self.assertRegex(invoice.invoice_number, r'^FAC-\d{4}-\d{6}$')
        self.assertEqual(invoice.company_name, 'KOUROUMA AUTO PARTS')
        self.assertTrue(invoice.validation_reference)
        self.assertIn('VALIDEE', invoice.stamp_text.upper())

    def test_invoice_branding_lists_are_readable_and_admin_editable(self):
        from invoices.models import InvoiceBranding

        read_response = self.client.get('/api/v1/invoices/branding/')

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.data['company_name'], 'Kourouma Auto Parts')
        self.assertEqual(read_response.data['phone_numbers'], [])
        self.assertEqual(read_response.data['email_addresses'], [])
        self.assertFalse(read_response.data['is_configured'])
        self.assertFalse(InvoiceBranding.objects.filter(pk=1).exists())

        InvoiceBranding.objects.create(
            pk=1,
            tenant=Tenant.objects.get(slug='kourouma-auto-parts'),
        )
        legacy_defaults_response = self.client.get('/api/v1/invoices/branding/')
        self.assertEqual(legacy_defaults_response.status_code, 200)
        self.assertFalse(legacy_defaults_response.data['is_configured'])

        forbidden_response = self.client.patch(
            '/api/v1/invoices/branding/',
            {'phone_numbers': ['+224 600 00 00 00']},
            format='json',
        )
        self.assertEqual(forbidden_response.status_code, 403)

        administrator = User.objects.create_user(
            username='invoice_branding_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=administrator)
        update_response = self.client.patch(
            '/api/v1/invoices/branding/',
            {
                'phone_numbers': ['+224 600 00 00 00', '+224 611 11 11 11'],
                'email_addresses': ['contact@example.test', 'billing@example.test'],
                'additional_lines': ['Horaires : lundi au samedi'],
            },
            format='json',
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(len(update_response.data['phone_numbers']), 2)
        self.assertEqual(len(update_response.data['email_addresses']), 2)
        self.assertEqual(update_response.data['additional_lines'], ['Horaires : lundi au samedi'])
        self.assertTrue(update_response.data['is_configured'])

    def test_admin_can_configure_and_preview_uploaded_invoice_stamp(self):
        from invoices.models import InvoiceBranding
        from invoices.rendering import build_invoice_snapshot, render_invoice_pdf
        from invoices.storage import private_invoice_storage

        administrator = User.objects.create_user(
            username='invoice_stamp_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=administrator)
        settings_response = self.client.patch(
            '/api/v1/invoices/branding/',
            {
                'stamp_position': 'right',
                'stamp_size_mm': 26,
                'stamp_opacity': 65,
            },
            format='json',
        )

        self.assertEqual(settings_response.status_code, 200, settings_response.data)
        self.assertEqual(settings_response.data['stamp_position'], 'right')
        self.assertEqual(settings_response.data['stamp_size_mm'], 26)
        self.assertEqual(settings_response.data['stamp_opacity'], 65)

        previous_storage_location = private_invoice_storage.location
        with TemporaryDirectory() as directory:
            private_invoice_storage.location = directory
            try:
                stamp_buffer = BytesIO()
                Image.new('RGB', (32, 32), color='white').save(stamp_buffer, format='PNG')
                upload = SimpleUploadedFile(
                    'company-stamp.png',
                    stamp_buffer.getvalue(),
                    content_type='image/png',
                )
                upload_response = self.client.patch(
                    '/api/v1/invoices/branding/',
                    {'stamp_image': upload},
                    format='multipart',
                )

                self.assertEqual(upload_response.status_code, 200, upload_response.data)
                self.assertTrue(upload_response.data['stamp_image_url'].endswith('/stamp/'))
                asset_response = self.client.get('/api/v1/invoices/branding/assets/stamp/')
                stamp_content = b''.join(asset_response.streaming_content)
                self.assertEqual(asset_response.status_code, 200)
                self.assertEqual(asset_response['Cache-Control'], 'private, no-store')
                self.assertTrue(stamp_content.startswith(b'\x89PNG\r\n\x1a\n'))

                sale = Sale.objects.create(
                    customer=self.customer,
                    status='paid',
                    payment_method='cash',
                    total_amount=Decimal('40000.00'),
                    amount_paid=Decimal('40000.00'),
                )
                sale.items.create(product=self.product, quantity=1, unit_price=Decimal('40000.00'))
                invoice = Invoice.objects.create(
                    sale=sale,
                    total_amount=sale.total_amount,
                    paid_amount=sale.amount_paid,
                )
                snapshot = build_invoice_snapshot(invoice)
                self.assertEqual(snapshot['company']['stamp_position'], 'right')
                self.assertEqual(snapshot['company']['stamp_size_mm'], 26)
                self.assertEqual(snapshot['company']['stamp_opacity'], 65)
                self.assertTrue(Path(snapshot['company']['stamp_path']).is_file())
                pdf_bytes, page_count = render_invoice_pdf(snapshot)
                self.assertEqual(page_count, 1)
                self.assertEqual(len(PdfReader(BytesIO(pdf_bytes)).pages), 1)
            finally:
                branding = InvoiceBranding.objects.filter(pk=1).first()
                if branding and branding.stamp_image:
                    branding.stamp_image.delete(save=False)
                private_invoice_storage.location = previous_storage_location

    def test_invoice_stamp_configuration_rejects_out_of_range_values(self):
        administrator = User.objects.create_user(
            username='invoice_stamp_limits_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=administrator)

        response = self.client.patch(
            '/api/v1/invoices/branding/',
            {'stamp_size_mm': 27, 'stamp_opacity': 10, 'stamp_position': 'outside'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('stamp_size_mm', response.data)
        self.assertIn('stamp_opacity', response.data)
        self.assertIn('stamp_position', response.data)

    def test_generated_invoice_stamp_includes_company_status_and_document_type(self):
        from invoices.rendering import render_invoice_pdf

        snapshot = {
            'company': {
                'name': 'KOUROUMA AUTO PARTS',
                'header_color': '#123D60',
                'stamp_size_mm': 20,
                'stamp_opacity': 100,
                'show': {},
            },
            'invoice_number': 'FAC-STAMP-0001',
            'issued_at': '2026-10-15T08:00:00+00:00',
            'verification_url': 'https://example.test/verifier/stamp',
            'validation_reference': 'VAL-STAMP-0001',
            'customer': {'name': 'Client test', 'phone': '', 'address': ''},
            'seller': 'Vendeur test',
            'payment_method': 'cash',
            'items': [{
                'description': 'Produit test',
                'reference': 'STAMP-001',
                'quantity': 1,
                'unit_price': '1000.00',
                'amount': '1000.00',
            }],
            'payments': [],
            'subtotal': '1000.00',
            'discount': '0.00',
            'total': '1000.00',
            'paid': '1000.00',
            'balance_due': '0.00',
            'stamp_text': 'VALIDEE',
            'commercial_note': 'Mention de test.',
        }

        pdf_bytes, page_count = render_invoice_pdf(snapshot)
        page_text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()

        self.assertEqual(page_count, 1)
        self.assertIn('KOUROUMA AUTO PARTS', page_text)
        self.assertIn('VALIDEE', page_text)
        self.assertIn('FACTURE', page_text)

    def test_admin_signature_is_private_and_rendered_in_its_own_invoice_box(self):
        from invoices.models import InvoiceBranding
        from invoices.rendering import build_invoice_snapshot, render_invoice_pdf
        from invoices.storage import private_invoice_storage

        self.client.force_authenticate(user=self.user)
        forbidden_response = self.client.patch(
            '/api/v1/invoices/branding/',
            {'seller_signature_name': 'Responsable'},
            format='json',
        )
        self.assertEqual(forbidden_response.status_code, 403)

        administrator = User.objects.create_user(
            username='invoice_signature_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=administrator)
        previous_storage_location = private_invoice_storage.location
        with TemporaryDirectory() as directory:
            private_invoice_storage.location = directory
            try:
                signature_buffer = BytesIO()
                signature_image = Image.new('RGBA', (320, 100), color=(255, 255, 255, 0))
                ImageDraw.Draw(signature_image).line(
                    [(20, 72), (90, 25), (140, 65), (220, 20), (300, 60)],
                    fill=(18, 61, 96, 255),
                    width=7,
                )
                signature_image.save(signature_buffer, format='PNG')
                upload_response = self.client.patch(
                    '/api/v1/invoices/branding/',
                    {
                        'seller_signature_image': SimpleUploadedFile(
                            'seller-signature.png',
                            signature_buffer.getvalue(),
                            content_type='image/png',
                        ),
                        'seller_signature_name': 'Mamadou Kourouma',
                        'seller_signature_title': 'Responsable des ventes',
                        'show_seller_signature': 'true',
                    },
                    format='multipart',
                )
                self.assertEqual(upload_response.status_code, 200, upload_response.data)
                self.assertTrue(upload_response.data['seller_signature_image_url'].endswith('/signature/'))
                self.assertEqual(upload_response.data['seller_signature_name'], 'Mamadou Kourouma')

                asset_response = self.client.get('/api/v1/invoices/branding/assets/signature/')
                signature_content = b''.join(asset_response.streaming_content)
                self.assertEqual(asset_response.status_code, 200)
                self.assertEqual(asset_response['Cache-Control'], 'private, no-store')
                self.assertTrue(signature_content.startswith(b'\x89PNG\r\n\x1a\n'))

                sale = Sale.objects.create(
                    customer=self.customer,
                    seller=administrator,
                    status='paid',
                    payment_method='cash',
                    total_amount=Decimal('40000.00'),
                    amount_paid=Decimal('40000.00'),
                )
                sale.items.create(product=self.product, quantity=1, unit_price=Decimal('40000.00'))
                invoice = Invoice.objects.create(
                    sale=sale,
                    total_amount=sale.total_amount,
                    paid_amount=sale.amount_paid,
                )
                snapshot = build_invoice_snapshot(invoice)
                self.assertEqual(snapshot['company']['seller_signature_name'], 'Mamadou Kourouma')
                self.assertTrue(Path(snapshot['company']['seller_signature_path']).is_file())

                pdf_bytes, page_count = render_invoice_pdf(snapshot)
                page_text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()
                self.assertEqual(page_count, 1)
                self.assertIn('Signature du client', page_text)
                self.assertIn('Signature du vendeur', page_text)
                self.assertIn('Mamadou Kourouma', page_text)
                self.assertIn('Responsable des ventes', page_text)
                self.assertIn('Validation et cachet', page_text)
                self.assertIn('Vérification de la facture', page_text)
            finally:
                branding = InvoiceBranding.objects.filter(pk=1).first()
                if branding and branding.seller_signature_image:
                    branding.seller_signature_image.delete(save=False)
                private_invoice_storage.location = previous_storage_location

    @override_settings(PDF_SIGNING_PKCS12_PATH='', PDF_SIGNING_TRUST_ROOT_PATH='')
    def test_issue_without_certificate_is_audited_and_not_downloadable(self):
        sale = Sale.objects.create(
            customer=self.customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('40000.00'),
        )
        sale.items.create(product=self.product, quantity=1, unit_price=Decimal('40000.00'))
        invoice = Invoice.objects.create(sale=sale, total_amount=sale.total_amount, paid_amount=sale.amount_paid)

        issue_response = self.client.post(f'/api/v1/invoices/{invoice.id}/issue/', {}, format='json')
        invoice.refresh_from_db()
        pdf_response = self.client.get(f'/api/v1/invoices/{invoice.id}/pdf/')

        self.assertEqual(issue_response.status_code, 503)
        self.assertEqual(invoice.document_status, 'signature_failed')
        self.assertEqual(invoice.document_attempts.count(), 1)
        self.assertEqual(invoice.document_attempts.first().status, 'failed')
        self.assertEqual(pdf_response.status_code, 409)

    def test_trusted_certificate_signs_stores_and_verifies_pdf(self):
        from invoices.storage import private_invoice_storage

        sale = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='mobile_money',
            total_amount=Decimal('80000.00'),
            amount_paid=Decimal('40000.00'),
        )
        sale.items.create(product=self.product, quantity=2, unit_price=Decimal('40000.00'))
        invoice = Invoice.objects.create(
            sale=sale,
            total_amount=sale.total_amount,
            paid_amount=sale.amount_paid,
            validated_by=self.user,
        )

        with TemporaryDirectory() as directory:
            p12_path, root_path, passphrase = create_test_signing_material(directory)
            previous_storage_location = private_invoice_storage.location
            private_invoice_storage.location = str(Path(directory) / 'private-pdfs')
            try:
                with override_settings(
                    DEBUG=True,
                    INVOICE_VERIFICATION_BASE_URL='https://nexora.example/verifier/',
                    PDF_SIGNING_PKCS12_PATH=str(p12_path),
                    PDF_SIGNING_PKCS12_PASSPHRASE=passphrase,
                    PDF_SIGNING_TRUST_ROOT_PATH=str(root_path),
                    PDF_SIGNING_REVOCATION_MODE='soft-fail',
                    PRIVATE_INVOICE_ROOT=str(Path(directory) / 'private-pdfs'),
                ):
                    issue_response = self.client.post(
                        f'/api/v1/invoices/{invoice.id}/issue/',
                        {},
                        format='json',
                    )
                    invoice.refresh_from_db()
                    pdf_response = self.client.get(f'/api/v1/invoices/{invoice.id}/pdf/')
                    verify_response = self.client.get(
                        f'/api/invoices/verify/{invoice.verification_token}/',
                    )

                    self.assertEqual(
                        issue_response.status_code,
                        201,
                        (issue_response.data, invoice.signature_error),
                    )
                    self.assertEqual(invoice.document_status, 'signed')
                    self.assertEqual(invoice.document_pages, 1)
                    self.assertEqual(pdf_response.status_code, 200)
                    self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
                    self.assertTrue(pdf_response.content.startswith(b'%PDF-'))
                    self.assertEqual(len(PdfReader(BytesIO(pdf_response.content)).pages), 1)
                    self.assertTrue(verify_response.data['signature_valid'])
                    self.assertEqual(verify_response.data['signature_status'], 'valid')
                    self.assertNotIn('customer', verify_response.data)
            finally:
                private_invoice_storage.location = previous_storage_location

    def test_invoice_renderer_paginates_in_groups_of_25(self):
        from invoices.rendering import render_invoice_pdf

        for item_count, expected_pages in [
            (1, 1), (2, 1), (4, 1), (9, 1), (25, 1),
            (26, 2), (32, 2), (50, 2), (51, 3),
        ]:
            snapshot = {
                'company': {
                    'name': 'KOUROUMA AUTO PART',
                    'activity': 'Pièces automobiles',
                    'distributor': 'Distributeur BSG',
                    'address': 'Madina, Conakry',
                    'phone': '+224600000000',
                    'phones': ['+224600000000', '+224611111111'],
                    'email': 'contact@example.test',
                    'emails': ['contact@example.test', 'billing@example.test'],
                    'additional_lines': ['Horaires : lundi au samedi'],
                    'rccm': '',
                    'nif': '',
                },
                'invoice_number': 'FAC-2026-000001',
                'issued_at': '2026-10-14T08:00:00+00:00',
                'verification_url': 'https://example.test/verifier/test-token',
                'validation_reference': 'VAL-TEST',
                'customer': {'name': 'Client test', 'phone': '', 'address': ''},
                'seller': 'Vendeur test',
                'payment_method': 'cash',
                'items': [
                    {
                        'description': f'Pièce {index:03d}',
                        'reference': f'P-{index:03d}',
                        'quantity': 1,
                        'unit_price': '1000.00',
                        'amount': '1000.00',
                    }
                    for index in range(1, item_count + 1)
                ],
                'payments': [],
                'subtotal': str(item_count * 1000),
                'discount': '0',
                'total': str(item_count * 1000),
                'paid': '0',
                'balance_due': str(item_count * 1000),
                'stamp_text': 'VALIDEE',
                'commercial_note': 'Mention commerciale de test.',
            }

            pdf_bytes, page_count = render_invoice_pdf(snapshot)
            reader = PdfReader(BytesIO(pdf_bytes))

            self.assertEqual(page_count, expected_pages)
            self.assertEqual(len(reader.pages), expected_pages)
            for page_index, page in enumerate(reader.pages):
                page_text = page.extract_text()
                self.assertIn(f'PAGE {page_index + 1}/{expected_pages}', page_text)
            if item_count == 32:
                first_page = reader.pages[0].extract_text()
                second_page = reader.pages[1].extract_text()
                self.assertIn('Pièce 025', first_page)
                self.assertNotIn('Pièce 026', first_page)
                self.assertIn('Pièce 026', second_page)
                self.assertIn('Pièce 032', second_page)
                self.assertNotIn('Pièce 033', second_page)
            if item_count == 4:
                first_page = reader.pages[0].extract_text()
                self.assertIn('Tél. +224600000000', first_page)
                self.assertIn('E-mail : billing@example.test', first_page)
                self.assertIn('Horaires : lundi au samedi', first_page)

    def test_carnet_mode_pads_to_25_rows_without_extra_page(self):
        from invoices.rendering import render_invoice_pdf

        snapshot = {
            'company': {
                'name': 'KOUROUMA AUTO PARTS',
                'activity': 'Pièces automobiles',
                'distributor': 'Distributeur BSG',
                'address': 'Madina, Conakry',
                'phone': '',
                'phones': [],
                'email': '',
                'emails': [],
                'rccm': '',
                'nif': '',
                'additional_lines': [],
                'line_display_mode': 'carnet',
                'header_alignment': 'center',
                'header_color': '#123D60',
                'text_color': '#FFFFFF',
                'show': {},
            },
            'invoice_number': 'FAC-2026-000001',
            'issued_at': '2026-10-14T08:00:00+00:00',
            'verification_url': 'https://example.test/verifier/test-token',
            'validation_reference': 'VAL-TEST',
            'customer': {'name': 'Client test', 'phone': '', 'address': ''},
            'seller': 'Vendeur test',
            'payment_method': 'cash',
            'items': [
                {
                    'description': f'Pièce {index:03d}',
                    'reference': f'P-{index:03d}',
                    'quantity': 1,
                    'unit_price': '1000.00',
                    'amount': '1000.00',
                }
                for index in range(1, 3)
            ],
            'payments': [],
            'subtotal': '2000',
            'discount': '0',
            'total': '2000',
            'paid': '0',
            'balance_due': '2000',
            'stamp_text': 'VALIDEE',
            'commercial_note': 'Mention commerciale de test.',
        }

        pdf_bytes, page_count = render_invoice_pdf(snapshot)
        page_text = PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()

        self.assertEqual(page_count, 1)
        self.assertIn('Pièce 001', page_text)
        self.assertIn('Pièce 002', page_text)
        self.assertIn('25', page_text)
        self.assertNotIn('Pièce 003', page_text)


class InvoiceTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug='invoice-tenant-a', name='Factures A')
        self.tenant_b = Tenant.objects.create(slug='invoice-tenant-b', name='Factures B')
        self.company_a = Company.objects.create(
            tenant=self.tenant_a,
            name='Société Factures A',
            address='Adresse A',
            phone='+224600009101',
            email='a@example.test',
        )
        self.company_b = Company.objects.create(
            tenant=self.tenant_b,
            name='Société Factures B',
            address='Adresse B',
            phone='+224600009102',
            email='b@example.test',
        )
        self.user_a = User.objects.create_user(
            username='invoice_tenant_a',
            password='secret123',
            role='admin',
            tenant=self.tenant_a,
        )
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.user_b = User.objects.create_user(
            username='invoice_tenant_b',
            password='secret123',
            role='admin',
            tenant=self.tenant_b,
        )
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            full_name='Client facture A',
            phone='+224600009001',
        )
        customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            full_name='Client facture B',
            phone='+224600009002',
        )
        sale_a = Sale.objects.create(
            tenant=self.tenant_a,
            customer=customer_a,
            status='paid',
            total_amount=Decimal('100.00'),
        )
        sale_b = Sale.objects.create(
            tenant=self.tenant_b,
            customer=customer_b,
            status='paid',
            total_amount=Decimal('200.00'),
        )
        self.invoice_a = Invoice.objects.create(
            sale=sale_a,
            invoice_number='INV-TENANT-A',
            total_amount=sale_a.total_amount,
        )
        self.invoice_b = Invoice.objects.create(
            sale=sale_b,
            invoice_number='INV-TENANT-B',
            total_amount=sale_b.total_amount,
        )

    def test_invoice_list_and_private_endpoints_are_tenant_scoped(self):
        list_response = self.client_a.get('/api/invoices/')

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            [item['invoice_number'] for item in list_response.data['results']],
            [self.invoice_a.invoice_number],
        )

        foreign_urls = [
            f'/api/v1/invoices/{self.invoice_b.id}/',
            f'/api/v1/invoices/{self.invoice_b.id}/qr/',
            f'/api/v1/invoices/{self.invoice_b.id}/qr-image/',
            f'/api/v1/invoices/{self.invoice_b.id}/pdf/',
        ]
        for url in foreign_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client_a.get(url).status_code, 404)

        issue_response = self.client_a.post(
            f'/api/v1/invoices/{self.invoice_b.id}/issue/',
            {},
            format='json',
        )
        self.assertEqual(issue_response.status_code, 404)

    def test_invoice_branding_is_configurable_and_isolated_per_tenant(self):
        from invoices.models import InvoiceBranding

        initial_a = self.client_a.get('/api/v1/invoices/branding/')
        initial_b = self.client_b.get('/api/v1/invoices/branding/')

        self.assertEqual(initial_a.status_code, 200)
        self.assertEqual(initial_a.data['company_name'], self.company_a.name)
        self.assertEqual(initial_a.data['address'], self.company_a.address)
        self.assertEqual(initial_b.status_code, 200)
        self.assertEqual(initial_b.data['company_name'], self.company_b.name)
        self.assertEqual(initial_b.data['address'], self.company_b.address)
        self.assertFalse(InvoiceBranding.objects.exists())

        update_response = self.client_a.patch(
            '/api/v1/invoices/branding/',
            {'company_name': 'Marque facture A'},
            format='json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.data)
        self.assertEqual(update_response.data['company_name'], 'Marque facture A')

        refreshed_b = self.client_b.get('/api/v1/invoices/branding/')
        self.assertEqual(refreshed_b.status_code, 200)
        self.assertEqual(refreshed_b.data['company_name'], self.company_b.name)
        self.assertEqual(InvoiceBranding.objects.count(), 1)

    def test_invoice_snapshot_uses_only_its_tenant_branding(self):
        from invoices.models import InvoiceBranding
        from invoices.rendering import build_invoice_snapshot

        InvoiceBranding.objects.create(
            tenant=self.tenant_a,
            company_name='Marque facture A',
            phone_numbers=['+224600001111'],
        )

        snapshot_a = build_invoice_snapshot(self.invoice_a)
        snapshot_b = build_invoice_snapshot(self.invoice_b)

        self.assertEqual(snapshot_a['company']['name'], 'Marque facture A')
        self.assertEqual(snapshot_a['company']['phone'], '+224600001111')
        self.assertEqual(snapshot_b['company']['name'], self.company_b.name)
        self.assertEqual(snapshot_b['company']['phone'], self.company_b.phone)

    def test_invoice_branding_asset_is_not_shared_between_tenants(self):
        from invoices.models import InvoiceBranding
        from invoices.storage import private_invoice_storage

        previous_storage_location = private_invoice_storage.location
        with TemporaryDirectory() as directory:
            private_invoice_storage.location = directory
            try:
                image_buffer = BytesIO()
                Image.new('RGB', (16, 16), color='blue').save(image_buffer, format='PNG')
                image_data = image_buffer.getvalue()
                for client in (self.client_a, self.client_b):
                    upload = SimpleUploadedFile(
                        'company-logo.png',
                        image_data,
                        content_type='image/png',
                    )
                    update_response = client.patch(
                        '/api/v1/invoices/branding/',
                        {'logo_image': upload},
                        format='multipart',
                    )
                    self.assertEqual(update_response.status_code, 200, update_response.data)

                branding_a = InvoiceBranding.objects.get(tenant=self.tenant_a)
                branding_b = InvoiceBranding.objects.get(tenant=self.tenant_b)
                self.assertTrue(
                    branding_a.logo_image.name.startswith(
                        f'tenants/{self.tenant_a.pk}/invoice-branding/',
                    ),
                )
                self.assertTrue(
                    branding_b.logo_image.name.startswith(
                        f'tenants/{self.tenant_b.pk}/invoice-branding/',
                    ),
                )
                self.assertNotEqual(branding_a.logo_image.name, branding_b.logo_image.name)

                asset_url = '/api/v1/invoices/branding/assets/logo/'
                for client in (self.client_a, self.client_b):
                    asset_response = client.get(asset_url)
                    self.assertEqual(asset_response.status_code, 200)
                    b''.join(asset_response.streaming_content)
                    asset_response.close()
            finally:
                private_invoice_storage.location = previous_storage_location
