from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Tenant
from users.models import User
from .models import Customer


class CustomerApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='client_manager',
            password='secret123',
            pin_code='1234',
            role='sales',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_customer(self):
        payload = {
            'full_name': 'Mamadou Bah',
            'phone': '+224600000500',
            'email': 'mamadou@example.com',
            'address': 'Kipé',
            'city': 'Conakry',
            'company_name': 'Bah Enterprise',
            'is_active': True,
        }
        response = self.client.post('/api/customers/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(response.data['full_name'], 'Mamadou Bah')
        self.assertEqual(
            Customer.objects.get(pk=response.data['id']).tenant_id,
            Tenant.objects.get(slug='kourouma-auto-parts').pk,
        )

    def test_customer_list_detail_and_history_are_scoped_by_tenant(self):
        tenant_a = Tenant.objects.get(slug='kourouma-auto-parts')
        tenant_b = Tenant.objects.create(
            slug='customers-tenant-b',
            name='Customers Tenant B',
            status='active',
        )
        self.user.tenant = tenant_a
        self.user.save(update_fields=['tenant'])
        customer_a = Customer.objects.create(
            full_name='Client Tenant A',
            tenant=tenant_a,
        )
        customer_b = Customer.objects.create(
            full_name='Client Tenant B',
            tenant=tenant_b,
        )

        listed = self.client.get('/api/customers/')
        detail = self.client.get(f'/api/customers/{customer_b.pk}/')
        history = self.client.get(f'/api/v1/customers/{customer_b.pk}/sales/')
        created = self.client.post(
            '/api/customers/',
            {'full_name': 'Nouveau client A'},
            format='json',
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            {row['id'] for row in listed.data['results']},
            {customer_a.pk},
        )
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(history.status_code, 404)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(
            Customer.objects.get(pk=created.data['id']).tenant_id,
            tenant_a.pk,
        )

    def test_unassigned_customer_access_is_denied_when_tenant_is_ambiguous(self):
        Tenant.objects.create(
            slug='customers-tenant-extra',
            name='Customers Extra Tenant',
            status='active',
        )
        unassigned = User.objects.create_user(
            username='unassigned_customer_user',
            password='secret123',
            role='sales',
        )
        self.client.force_authenticate(user=unassigned)

        listed = self.client.get('/api/customers/')
        created = self.client.post(
            '/api/customers/',
            {'full_name': 'Client sans tenant'},
            format='json',
        )

        self.assertEqual(listed.status_code, 403)
        self.assertEqual(created.status_code, 403)
        self.assertFalse(Customer.objects.filter(full_name='Client sans tenant').exists())

    def test_list_customers(self):
        Customer.objects.create(full_name='Sophie Camara', phone='+224600000600')
        response = self.client.get('/api/customers/')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)

    def test_search_customer_by_name(self):
        Customer.objects.create(full_name='Tamba Sow', phone='+224600000700')
        response = self.client.get('/api/customers/?search=Sow')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['full_name'] == 'Tamba Sow' for item in response.data['results']))

    def test_sales_user_can_access_customers_module(self):
        sales_user = User.objects.create_user(
            username='sales_customers',
            password='secret123',
            pin_code='4321',
            role='sales',
        )
        client = APIClient()
        client.force_authenticate(user=sales_user)

        response = client.get('/api/customers/')

        self.assertEqual(response.status_code, 200)

    def test_customer_history_and_credit_endpoints(self):
        from decimal import Decimal
        from payments.models import Payment
        from sales.models import Sale

        customer = Customer.objects.create(full_name='Client historique')
        sale = Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='cash',
            total_amount=Decimal('10000.00'),
            amount_paid=Decimal('4000.00'),
        )
        Payment.objects.create(
            customer=customer,
            sale=sale,
            amount=Decimal('4000.00'),
            payment_method='cash',
            reference='PAY-HISTORY-001',
        )

        sales_response = self.client.get(f'/api/v1/customers/{customer.id}/sales/')
        payments_response = self.client.get(f'/api/v1/customers/{customer.id}/payments/')
        credit_response = self.client.get(f'/api/v1/customers/{customer.id}/credit/')

        self.assertEqual(sales_response.status_code, 200)
        self.assertEqual(len(sales_response.data), 1)
        self.assertEqual(payments_response.status_code, 200)
        self.assertEqual(len(payments_response.data), 1)
        self.assertEqual(credit_response.status_code, 200)
        self.assertEqual(credit_response.data['balance'], 6000.0)
