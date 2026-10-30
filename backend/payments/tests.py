from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AuditLog, Tenant
from customers.models import Customer
from finance.models import FinancialTransaction
from notifications.models import Notification
from payments.models import Payment, PaymentAllocation
from sales.models import Invoice, Sale
from users.models import User


class PaymentApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='paiement_sales',
            password='secret123',
            pin_code='1234',
            role='sales',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.customer = Customer.objects.create(full_name='Fode Diaby', phone='+224600003000')
        self.sale = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='500000.00',
            amount_paid='250000.00',
        )
        opening_payment = Payment.objects.create(
            customer=self.customer,
            sale=self.sale,
            amount='250000.00',
            payment_method='cash',
            reference='PAY-OPENING-001',
            created_by=self.user,
        )
        PaymentAllocation.objects.create(
            payment=opening_payment,
            sale=self.sale,
            amount=opening_payment.amount,
        )

    def test_create_payment_registers_credit_reduction(self):
        response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'sale': self.sale.id,
                'amount': '250000.00',
                'payment_method': 'cash',
                'reference': 'PAY-001',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(float(response.data['amount']), 250000.0)

    def test_create_payment_creates_one_validated_finance_transaction(self):
        response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'sale': self.sale.id,
                'amount': '250000.00',
                'payment_method': 'cash',
                'reference': 'PAY-FINANCE-001',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        transaction = FinancialTransaction.objects.get(origin=f"payment:{response.data['id']}")
        self.assertEqual(transaction.status, 'validated')
        self.assertEqual(transaction.direction, 'in')
        self.assertEqual(transaction.amount, Decimal('250000.00'))

    def test_payment_idempotency_prevents_duplicate_payment(self):
        payload = {
            'customer': self.customer.id,
            'sale': self.sale.id,
            'amount': '25000.00',
            'payment_method': 'cash',
            'reference': 'PAY-IDEMPOTENT-001',
        }
        first = self.client.post(
            '/api/payments/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='PAYMENT-ONCE-001',
        )
        repeated = self.client.post(
            '/api/payments/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='PAYMENT-ONCE-001',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeated.status_code, 201)
        self.assertEqual(repeated.data['id'], first.data['id'])
        self.assertEqual(Payment.objects.filter(reference='PAY-IDEMPOTENT-001').count(), 1)
        self.assertEqual(
            FinancialTransaction.objects.filter(origin=f"payment:{first.data['id']}").count(),
            1,
        )

    def test_credit_balance_is_calculated(self):
        response = self.client.get(f'/api/payments/customer/{self.customer.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('balance', response.data)

    def test_payment_creation_registers_audit_log(self):
        initial_count = AuditLog.objects.filter(action='payment').count()

        response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'sale': self.sale.id,
                'amount': '5000.00',
                'payment_method': 'cash',
                'reference': 'PAY-TRACE-001',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AuditLog.objects.filter(action='payment').count(), initial_count + 1)

    def test_payment_creation_creates_internal_admin_notification(self):
        response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'sale': self.sale.id,
                'amount': '15000.00',
                'payment_method': 'cash',
                'reference': 'PAY-ADMIN-NOTIF',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Notification.objects.filter(
                sale=self.sale,
                event_type='payment_received',
                channel='internal',
                status='sent',
            ).exists()
        )
        whatsapp = Notification.objects.get(
            sale=self.sale,
            event_type='payment_received',
            channel='whatsapp',
        )
        self.assertEqual(whatsapp.status, 'pending')
        self.assertIn('GNF', whatsapp.message)

    def test_credit_summary_excludes_cash_sales_and_aggregates_multiple_credit_sales(self):
        Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='paid',
            payment_method='cash',
            total_amount='900000.00',
            amount_paid='900000.00',
        )
        second_credit_sale = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='300000.00',
            amount_paid='0.00',
        )
        response = self.client.get(f'/api/payments/customer/{self.customer.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['sales_count'], 2)
        self.assertEqual(Decimal(str(response.data['sales_total'])), Decimal('800000'))
        self.assertEqual(Decimal(str(response.data['balance'])), Decimal('550000'))

        Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='200000.00',
            amount_paid='0.00',
        )
        list_response = self.client.get('/api/payments/credits/')

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(Decimal(str(list_response.data[0]['balance'])), Decimal('750000'))

    def test_credit_detail_exposes_sales_and_payment_history(self):
        credit_sale = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='500000.00',
            amount_paid='0.00',
        )
        self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'sale': credit_sale.id,
                'amount': '150000.00',
                'payment_method': 'cash',
                'reference': 'PAY-HISTORY-001',
            },
            format='json',
        )
        response = self.client.get(f'/api/payments/customer/{self.customer.id}/credits/')

        self.assertEqual(Decimal(str(response.data['balance'])), Decimal('600000'))
        self.assertEqual(len(response.data['sales']), 2)
        self.assertEqual(len(response.data['payments']), 2)

    def test_credit_list_exposes_aging_buckets(self):
        old_customer = Customer.objects.create(full_name='Client ancien', phone='+224600003100')
        old_sale = Sale.objects.create(
            customer=old_customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='150000.00',
            amount_paid='0.00',
        )
        old_sale.sale_date = timezone.now() - timedelta(days=95)
        old_sale.save(update_fields=['sale_date'])

        response = self.client.get('/api/payments/credits/')

        self.assertEqual(response.status_code, 200)
        customer_entry = next(item for item in response.data if item['customer_id'] == old_customer.id)
        self.assertEqual(customer_entry['aging_bucket'], '90+')
        self.assertGreaterEqual(customer_entry['days_overdue'], 90)

    def test_customer_payment_is_allocated_fifo_across_multiple_credit_sales(self):
        first = self.sale
        second = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='400000.00',
            amount_paid='0.00',
        )
        response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'amount': '400000.00',
                'payment_method': 'mobile_money',
                'reference': 'PAY-MULTI-001',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        allocations = response.data['allocations']
        self.assertEqual(len(allocations), 2)
        self.assertEqual(Decimal(str(allocations[0]['amount'])), Decimal('250000.00'))
        self.assertEqual(Decimal(str(allocations[1]['amount'])), Decimal('150000.00'))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.amount_paid, first.total_amount)
        self.assertEqual(second.amount_paid, Decimal('150000.00'))
        self.assertEqual(response.data['created_by_name'], self.user.display_name)

    def test_customer_payment_cannot_exceed_combined_open_credit(self):
        response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'amount': '250001.00',
                'payment_method': 'cash',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('dépasse la dette restante', str(response.data['amount']))

    def test_credit_dashboard_aggregates_and_searches_customers(self):
        response = self.client.get('/api/payments/credits/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['sales_count'], 1)
        self.assertEqual(Decimal(str(response.data[0]['total_credit'])), Decimal('500000'))
        self.assertEqual(Decimal(str(response.data[0]['balance'])), Decimal('250000'))
        filtered = self.client.get('/api/payments/credits/', {'search': '600003000'})
        self.assertEqual(len(filtered.data), 1)
        no_match = self.client.get('/api/payments/credits/', {'search': 'no-customer'})
        self.assertEqual(no_match.data, [])

    def test_sales_user_only_sees_credit_sales_assigned_to_them(self):
        seller = User.objects.create_user(
            username='vendeur_credit',
            password='secret123',
            role='sales',
        )
        self.sale.seller = seller
        self.sale.save(update_fields=['seller'])
        another_sale = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='300000.00',
            amount_paid='0.00',
        )
        client = APIClient()
        client.force_authenticate(user=seller)

        credits = client.get('/api/payments/credits/')
        summary = client.get(f'/api/payments/customer/{self.customer.id}/')
        detail = client.get(f'/api/payments/customer/{self.customer.id}/credits/')

        self.assertEqual(credits.status_code, 200)
        self.assertEqual(len(credits.data), 1)
        self.assertEqual(credits.data[0]['sales_count'], 1)
        self.assertEqual(Decimal(str(credits.data[0]['total_credit'])), Decimal('500000'))
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data['sales_count'], 1)
        self.assertEqual(Decimal(str(summary.data['balance'])), Decimal('250000'))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['sales_count'], 1)
        self.assertEqual(detail.data['sales'][0]['sale_id'], self.sale.id)
        self.assertNotEqual(detail.data['sales'][0]['sale_id'], another_sale.id)
        other_sale_payment = client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'sale': another_sale.id,
                'amount': '1000.00',
                'payment_method': 'cash',
            },
            format='json',
        )
        combined_credit_payment = client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'amount': '250001.00',
                'payment_method': 'cash',
            },
            format='json',
        )
        self.assertEqual(other_sale_payment.status_code, 400)
        self.assertIn('sale', other_sale_payment.data)
        self.assertEqual(combined_credit_payment.status_code, 400)
        self.assertIn('amount', combined_credit_payment.data)

    def test_sales_user_cannot_read_another_sellers_payment_or_receipt(self):
        seller = User.objects.create_user(
            username='vendeur_paiement',
            password='secret123',
            role='sales',
        )
        self.sale.seller = seller
        self.sale.save(update_fields=['seller'])
        another_sale = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='300000.00',
            amount_paid='0.00',
        )
        payment_response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'sale': another_sale.id,
                'amount': '10000.00',
                'payment_method': 'cash',
            },
            format='json',
        )
        self.assertEqual(payment_response.status_code, 201, payment_response.data)

        client = APIClient()
        client.force_authenticate(user=seller)
        payments = client.get('/api/payments/')
        detail = client.get(f"/api/payments/{payment_response.data['id']}/")
        receipt = client.get(f"/api/payments/{payment_response.data['id']}/receipt/")

        self.assertEqual(payments.status_code, 200)
        self.assertNotIn(
            payment_response.data['id'],
            [item['id'] for item in payments.data['results']],
        )
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(receipt.status_code, 404)

    def test_invoice_search_keeps_the_customer_global_credit_totals(self):
        second_sale = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='300000.00',
            amount_paid='0.00',
        )
        Invoice.objects.create(
            sale=second_sale,
            invoice_number='FAC-SEARCH-002',
            total_amount=second_sale.total_amount,
        )

        response = self.client.get('/api/payments/credits/', {'search': 'FAC-SEARCH-002'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['sales_count'], 2)
        self.assertEqual(Decimal(str(response.data[0]['total_credit'])), Decimal('800000'))
        self.assertEqual(Decimal(str(response.data[0]['balance'])), Decimal('550000'))

    def test_every_customer_payment_creates_confirmation_with_global_balance(self):
        second = Sale.objects.create(
            customer=self.customer,
            seller=self.user,
            status='partial',
            payment_method='credit',
            total_amount='300000.00',
            amount_paid='0.00',
        )
        response = self.client.post(
            '/api/payments/',
            {
                'customer': self.customer.id,
                'amount': '500000.00',
                'payment_method': 'cash',
                'reference': 'PAY-GLOBAL-001',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        message = Notification.objects.get(
            customer=self.customer,
            event_type='payment_received',
            channel='whatsapp',
            status='pending',
        )
        self.assertIn('500000.00 GNF', message.message)
        self.assertIn('Votre solde restant est de 50000.00 GNF', message.message)
        self.assertEqual(response.data['allocations'][0]['sale'], self.sale.id)
        self.assertEqual(response.data['allocations'][1]['sale'], second.id)


class PaymentTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug='payments-tenant-a', name='Paiements A')
        self.tenant_b = Tenant.objects.create(slug='payments-tenant-b', name='Paiements B')
        self.user_a = User.objects.create_user(
            username='payments_tenant_a',
            password='secret123',
            role='admin',
            tenant=self.tenant_a,
        )
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            full_name='Client paiement A',
            phone='+224600008001',
        )
        self.customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            full_name='Client paiement B',
            phone='+224600008002',
        )
        self.sale_a = Sale.objects.create(
            tenant=self.tenant_a,
            customer=self.customer_a,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('100.00'),
            amount_paid=Decimal('0.00'),
        )
        self.sale_b = Sale.objects.create(
            tenant=self.tenant_b,
            customer=self.customer_b,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('200.00'),
            amount_paid=Decimal('0.00'),
        )
        self.payment_a = Payment.objects.create(
            customer=self.customer_a,
            sale=self.sale_a,
            amount=Decimal('10.00'),
            reference='PAY-TENANT-A',
        )
        PaymentAllocation.objects.create(
            payment=self.payment_a,
            sale=self.sale_a,
            amount=Decimal('10.00'),
        )
        self.payment_b = Payment.objects.create(
            customer=self.customer_b,
            sale=self.sale_b,
            amount=Decimal('20.00'),
            reference='PAY-TENANT-B',
        )
        PaymentAllocation.objects.create(
            payment=self.payment_b,
            sale=self.sale_b,
            amount=Decimal('20.00'),
        )

    def test_payment_notifications_are_bound_to_the_customer_tenant(self):
        response = self.client_a.post(
            '/api/payments/',
            {
                'customer': self.customer_a.id,
                'sale': self.sale_a.id,
                'amount': '20.00',
                'payment_method': 'cash',
                'reference': 'PAY-TENANT-NOTIFICATION',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        notifications = Notification.objects.filter(
            customer=self.customer_a,
            event_type='payment_received',
        )
        self.assertTrue(notifications.exists())
        self.assertEqual(
            set(notifications.values_list('tenant_id', flat=True)),
            {self.tenant_a.pk},
        )

    def test_payment_and_credit_reads_are_scoped_to_the_assigned_tenant(self):
        payment_list = self.client_a.get('/api/payments/')
        self.assertEqual(payment_list.status_code, 200)
        self.assertEqual(
            [item['id'] for item in payment_list.data['results']],
            [self.payment_a.id],
        )
        self.assertEqual(
            self.client_a.get(f'/api/payments/{self.payment_b.id}/').status_code,
            404,
        )
        self.assertEqual(
            self.client_a.get(f'/api/payments/{self.payment_b.id}/receipt/').status_code,
            404,
        )
        self.assertEqual(
            self.client_a.get(
                f'/api/payments/customer/{self.customer_b.id}/',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client_a.get(
                f'/api/payments/customer/{self.customer_b.id}/credits/',
            ).status_code,
            404,
        )
        credit_list = self.client_a.get('/api/payments/credits/')
        self.assertEqual(credit_list.status_code, 200)
        self.assertEqual(
            [item['customer_id'] for item in credit_list.data],
            [self.customer_a.id],
        )

    def test_payment_creation_rejects_foreign_customers_and_sales(self):
        foreign_customer = self.client_a.post(
            '/api/payments/',
            {
                'customer': self.customer_b.id,
                'sale': self.sale_b.id,
                'amount': '10.00',
                'payment_method': 'cash',
            },
            format='json',
        )
        foreign_sale = self.client_a.post(
            '/api/payments/',
            {
                'customer': self.customer_a.id,
                'sale': self.sale_b.id,
                'amount': '10.00',
                'payment_method': 'cash',
            },
            format='json',
        )

        self.assertEqual(foreign_customer.status_code, 400)
        self.assertEqual(foreign_sale.status_code, 400)
        self.assertEqual(Payment.objects.count(), 2)

    def test_foreign_sale_allocations_are_not_returned_with_a_payment(self):
        malformed_payment = Payment.objects.create(
            customer=self.customer_a,
            amount=Decimal('5.00'),
            reference='PAY-CROSS-TENANT-ALLOCATION',
        )
        PaymentAllocation.objects.create(
            payment=malformed_payment,
            sale=self.sale_b,
            amount=Decimal('5.00'),
        )

        response = self.client_a.get('/api/payments/')

        self.assertEqual(response.status_code, 200)
        serialized_payment = next(
            item
            for item in response.data['results']
            if item['id'] == malformed_payment.id
        )
        self.assertEqual(serialized_payment['allocations'], [])

    def test_unassigned_users_cannot_access_payments_when_multiple_tenants_exist(self):
        unassigned_user = User.objects.create_user(
            username='payments_unassigned',
            password='secret123',
            role='admin',
        )
        client = APIClient()
        client.force_authenticate(user=unassigned_user)

        response = client.get('/api/payments/')

        self.assertEqual(response.status_code, 403)
