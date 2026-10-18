from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Tenant
from .models import Document
from .models import DeliveryNote
from customers.models import Customer
from sales.models import Sale
from users.models import User


class DocumentApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='doc_admin',
            password='secret123',
            pin_code='1234',
            role='admin',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_document_record(self):
        response = self.client.post(
            '/api/documents/',
            {
                'title': 'Facture fournisseur',
                'document_type': 'invoice',
                'file_name': 'facture-001.pdf',
                'file_url': 'https://example.com/files/facture-001.pdf',
                'related_model': 'purchase',
                'related_id': 12,
                'status': 'active',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Facture fournisseur')

    def test_list_documents(self):
        self.client.post(
            '/api/documents/',
            {
                'title': 'Bon de réception',
                'document_type': 'receipt',
                'file_name': 'bon-01.pdf',
                'file_url': 'https://example.com/files/bon-01.pdf',
                'related_model': 'purchase',
                'related_id': 3,
                'status': 'active',
            },
            format='json',
        )

        response = self.client.get('/api/documents/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(item['title'] == 'Bon de réception' for item in response.data['results'])
        )

    def test_archive_document_instead_of_hard_delete(self):
        response = self.client.post(
            '/api/documents/',
            {
                'title': 'Facture à archiver',
                'document_type': 'invoice',
                'file_name': 'facture-archive.pdf',
                'file_url': 'https://example.com/files/facture-archive.pdf',
                'related_model': 'sale',
                'related_id': 9,
                'status': 'active',
            },
            format='json',
        )
        document_id = response.data['id']

        delete_response = self.client.delete(f'/api/documents/{document_id}/')

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.data['status'], 'archived')
        self.assertTrue(Document.objects.filter(pk=document_id, status='archived').exists())

    def test_public_delivery_verification_does_not_disclose_customer_name(self):
        customer = Customer.objects.create(
            full_name='Client privé',
            phone='+224600010099',
        )
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount='10000.00',
            amount_paid='10000.00',
        )
        note = DeliveryNote.objects.create(
            reference='BL-PRIVACY-0001',
            sale=sale,
        )

        response = APIClient().get(
            f'/api/documents/delivery-notes/verify/{note.verification_token}/'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['valid'])
        self.assertNotIn('customer', response.data)
        self.assertNotIn(customer.full_name, response.content.decode())


class DeliveryNoteTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.get(slug='kourouma-auto-parts')
        self.tenant_b = Tenant.objects.create(
            slug='delivery-notes-tenant-b',
            name='Delivery Notes Tenant B',
            status='active',
        )
        self.user_a = User.objects.create_user(
            username='delivery_sales_a',
            password='secret123',
            role='sales',
            tenant=self.tenant_a,
        )
        self.user_b = User.objects.create_user(
            username='delivery_sales_b',
            password='secret123',
            role='sales',
            tenant=self.tenant_b,
        )
        self.sale_a = self.create_sale(self.tenant_a, 'Client Tenant A')
        self.sale_b = self.create_sale(self.tenant_b, 'Client Tenant B')
        self.note_a = DeliveryNote.objects.create(
            reference='BL-TENANT-A-0001',
            sale=self.sale_a,
        )
        self.note_b = DeliveryNote.objects.create(
            reference='BL-TENANT-B-0001',
            sale=self.sale_b,
        )
        self.client = APIClient()

    @staticmethod
    def create_sale(tenant, customer_name):
        customer = Customer.objects.create(full_name=customer_name)
        return Sale.objects.create(
            customer=customer,
            tenant=tenant,
            status='paid',
            payment_method='cash',
            total_amount='10000.00',
            amount_paid='10000.00',
        )

    def test_delivery_note_list_and_detail_are_scoped_to_the_user_tenant(self):
        self.client.force_authenticate(user=self.user_a)

        listed = self.client.get('/api/documents/delivery-notes/')
        foreign_detail = self.client.get(
            f'/api/documents/delivery-notes/{self.note_b.pk}/'
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [note['id'] for note in listed.data['results']],
            [self.note_a.pk],
        )
        self.assertEqual(foreign_detail.status_code, 404)

    def test_delivery_note_cannot_be_created_or_reassigned_to_another_tenant_sale(self):
        self.client.force_authenticate(user=self.user_a)

        created = self.client.post(
            '/api/documents/delivery-notes/',
            {'sale': self.sale_b.pk},
            format='json',
        )
        reassigned = self.client.patch(
            f'/api/documents/delivery-notes/{self.note_a.pk}/',
            {'sale': self.sale_b.pk},
            format='json',
        )

        self.assertEqual(created.status_code, 400)
        self.assertEqual(reassigned.status_code, 400)
        self.assertEqual(DeliveryNote.objects.count(), 2)
        self.note_a.refresh_from_db()
        self.assertEqual(self.note_a.sale_id, self.sale_a.pk)

    def test_each_tenant_can_read_its_own_delivery_note(self):
        for user, note in ((self.user_a, self.note_a), (self.user_b, self.note_b)):
            self.client.force_authenticate(user=user)
            response = self.client.get(
                f'/api/documents/delivery-notes/{note.pk}/'
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['id'], note.pk)
