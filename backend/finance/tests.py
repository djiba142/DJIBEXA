from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User
from core.models import AuditLog, Tenant
from expenses.models import Expense, ExpenseCategory
from .models import FinancialAccount, FinancialTransaction, Fund
from sales.models import Sale
from customers.models import Customer
from payments.models import Payment


class FinanceJournalApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='finance_admin', password='secret123', role='admin')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_account_and_transaction_balance(self):
        account_response = self.client.post('/api/v1/finance/accounts/', {
            'name': 'Caisse principale',
            'account_type': 'cash',
            'opening_balance': '1000000.00',
        }, format='json')
        self.assertEqual(account_response.status_code, 201)
        account_id = account_response.data['id']

        transaction_response = self.client.post('/api/v1/finance/transactions/', {
            'transaction_type': 'income',
            'direction': 'in',
            'amount': '250000.00',
            'account': account_id,
            'description': 'Recette test',
        }, format='json')
        self.assertEqual(transaction_response.status_code, 201)
        self.assertEqual(transaction_response.data['status'], 'pending')

        account = FinancialAccount.objects.get(pk=account_id)
        self.assertEqual(account.current_balance, Decimal('1000000.00'))

        validate_response = self.client.post(
            f"/api/v1/finance/transactions/{transaction_response.data['id']}/validate/",
            format='json',
        )
        self.assertEqual(validate_response.status_code, 200)
        self.assertEqual(validate_response.data['status'], 'validated')
        account.refresh_from_db()
        self.assertEqual(account.current_balance, Decimal('1250000.00'))

    def test_validated_transaction_cannot_be_modified(self):
        account = FinancialAccount.objects.create(name='Compte bancaire', account_type='bank')
        transaction = FinancialTransaction.objects.create(
            transaction_type='expense',
            direction='out',
            amount='1000.00',
            account=account,
            created_by=self.user,
            status='validated',
            validated_by=self.user,
        )
        response = self.client.patch(
            f'/api/v1/finance/transactions/{transaction.id}/',
            {'amount': '2000.00'},
            format='json',
        )
        self.assertEqual(response.status_code, 409)

    def test_fund_return_and_closure_require_full_regularization(self):
        account = FinancialAccount.objects.create(name='Caisse missions', account_type='cash')
        fund_response = self.client.post('/api/v1/finance/funds/', {
            'purpose': 'Frais d’importation',
            'responsible': self.user.id,
            'amount': '500000.00',
        }, format='json')
        self.assertEqual(fund_response.status_code, 201)
        fund_id = fund_response.data['id']

        close_response = self.client.post(f'/api/v1/finance/funds/{fund_id}/close/', format='json')
        self.assertEqual(close_response.status_code, 400)

        return_response = self.client.post(f'/api/v1/finance/funds/{fund_id}/return/', {
            'amount': '500000.00',
            'account': account.id,
        }, format='json')
        self.assertEqual(return_response.status_code, 200)
        self.assertEqual(return_response.data['remaining_to_regularize'], '0.00')

        close_response = self.client.post(f'/api/v1/finance/funds/{fund_id}/close/', format='json')
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response.data['status'], 'closed')
        self.assertEqual(Fund.objects.get(pk=fund_id).status, 'closed')

    def test_financial_report_and_audit_endpoints(self):
        account = FinancialAccount.objects.create(name='Compte rapport', account_type='cash', opening_balance='100000.00')
        transaction = FinancialTransaction.objects.create(
            transaction_type='income', direction='in', amount='25000.00', account=account,
            status='validated', created_by=self.user, validated_by=self.user,
        )
        AuditLog.objects.create(
            user=self.user,
            action='update',
            model_name='FinancialTransaction',
            record_id=transaction.id,
            details='Validation test',
        )

        report = self.client.get('/api/v1/finance/reports/?start=2026-01-01&end=2026-12-31')
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['total_income'], Decimal('25000.00'))
        self.assertIn('expenses_by_category', report.data)

        audit = self.client.get('/api/v1/finance/audit/')
        self.assertEqual(audit.status_code, 200)
        self.assertTrue(any(entry['model_name'] == 'FinancialTransaction' for entry in audit.data))

    def test_unassigned_account_and_expense_category_names_remain_unique(self):
        FinancialAccount.objects.create(name='Compte historique sans tenant')
        ExpenseCategory.objects.create(name='Catégorie historique sans tenant')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinancialAccount.objects.create(name='Compte historique sans tenant')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExpenseCategory.objects.create(name='Catégorie historique sans tenant')

    def test_transfer_creates_balanced_pair_of_movements(self):
        source = FinancialAccount.objects.create(name='Caisse transfert', account_type='cash', opening_balance='100000.00')
        destination = FinancialAccount.objects.create(name='Banque transfert', account_type='bank')
        response = self.client.post('/api/v1/finance/transfers/', {
            'source_account': source.id,
            'destination_account': destination.id,
            'amount': '35000.00',
            'description': 'Dépôt bancaire',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.current_balance, Decimal('65000.00'))
        self.assertEqual(destination.current_balance, Decimal('35000.00'))
        self.assertEqual(FinancialTransaction.objects.filter(origin=f"transfer:{response.data['transfer_id']}").count(), 2)

    def test_transfer_replays_idempotently_and_rejects_changed_payload(self):
        source = FinancialAccount.objects.create(
            name='Caisse transfert idempotent',
            account_type='cash',
            opening_balance='100000.00',
        )
        destination = FinancialAccount.objects.create(
            name='Banque transfert idempotent',
            account_type='bank',
        )
        payload = {
            'source_account': source.id,
            'destination_account': destination.id,
            'amount': '35000.00',
            'description': 'Dépôt bancaire',
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': 'FINANCE-TRANSFER-ONCE-001'}

        first = self.client.post(
            '/api/v1/finance/transfers/',
            payload,
            format='json',
            **headers,
        )
        repeated = self.client.post(
            '/api/v1/finance/transfers/',
            payload,
            format='json',
            **headers,
        )
        changed = self.client.post(
            '/api/v1/finance/transfers/',
            {**payload, 'amount': '36000.00'},
            format='json',
            **headers,
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeated.status_code, 201)
        self.assertEqual(repeated.data['transfer_id'], first.data['transfer_id'])
        self.assertEqual(Decimal(str(repeated.data['amount'])), Decimal('35000.00'))
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(
            FinancialTransaction.objects.filter(
                origin=f"transfer:{first.data['transfer_id']}",
            ).count(),
            2,
        )
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.current_balance, Decimal('65000.00'))
        self.assertEqual(destination.current_balance, Decimal('35000.00'))

    def test_transfer_rejects_accounts_with_different_currencies(self):
        source = FinancialAccount.objects.create(
            name='Caisse GNF',
            account_type='cash',
            currency='GNF',
            opening_balance='100000.00',
        )
        destination = FinancialAccount.objects.create(
            name='Banque USD',
            account_type='bank',
            currency='USD',
        )

        response = self.client.post(
            '/api/v1/finance/transfers/',
            {
                'source_account': source.id,
                'destination_account': destination.id,
                'amount': '35000.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(FinancialTransaction.objects.filter(transaction_type='transfer').exists())


class FinanceTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(slug='finance-tenant-a', name='Finance A')
        self.tenant_b = Tenant.objects.create(slug='finance-tenant-b', name='Finance B')
        self.user_a = User.objects.create_user(
            username='finance_tenant_a',
            password='secret123',
            role='admin',
            tenant=self.tenant_a,
        )
        self.user_b = User.objects.create_user(
            username='finance_tenant_b',
            password='secret123',
            role='admin',
            tenant=self.tenant_b,
        )
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.account_a = FinancialAccount.objects.create(
            tenant=self.tenant_a,
            name='Caisse A',
            opening_balance=Decimal('100.00'),
        )
        self.account_b = FinancialAccount.objects.create(
            tenant=self.tenant_b,
            name='Caisse B',
            opening_balance=Decimal('900.00'),
        )
        self.transaction_a = FinancialTransaction.objects.create(
            tenant=self.tenant_a,
            account=self.account_a,
            transaction_type='income',
            direction='in',
            amount=Decimal('20.00'),
            status='validated',
            created_by=self.user_a,
        )
        self.transaction_b = FinancialTransaction.objects.create(
            tenant=self.tenant_b,
            account=self.account_b,
            transaction_type='income',
            direction='in',
            amount=Decimal('800.00'),
            status='validated',
            created_by=self.user_b,
        )
        self.customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            full_name='Client Finance A',
        )
        self.customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            full_name='Client Finance B',
        )
        self.sale_a = Sale.objects.create(
            tenant=self.tenant_a,
            customer=self.customer_a,
            seller=self.user_a,
            payment_method='credit',
            status='partial',
            total_amount=Decimal('20.00'),
            amount_paid=Decimal('5.00'),
        )
        self.sale_b = Sale.objects.create(
            tenant=self.tenant_b,
            customer=self.customer_b,
            seller=self.user_b,
            payment_method='credit',
            status='partial',
            total_amount=Decimal('200.00'),
            amount_paid=Decimal('50.00'),
        )
        self.payment_a = Payment.objects.create(
            customer=self.customer_a,
            sale=self.sale_a,
            amount=Decimal('5.00'),
            reference='FINANCE-TENANT-A-PAYMENT',
            created_by=self.user_a,
        )
        self.payment_b = Payment.objects.create(
            customer=self.customer_b,
            sale=self.sale_b,
            amount=Decimal('50.00'),
            reference='FINANCE-TENANT-B-PAYMENT',
            created_by=self.user_b,
        )

    def test_accounts_transactions_and_reports_are_scoped(self):
        accounts = self.client_a.get('/api/v1/finance/accounts/')
        transactions = self.client_a.get('/api/v1/finance/transactions/')
        report = self.client_a.get(
            '/api/v1/finance/reports/?start=2026-01-01&end=2026-12-31',
        )

        self.assertEqual(accounts.status_code, 200)
        self.assertEqual([item['id'] for item in accounts.data['results']], [self.account_a.id])
        self.assertEqual(transactions.status_code, 200)
        self.assertEqual(
            [item['id'] for item in transactions.data['results']],
            [self.transaction_a.id],
        )
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['opening_balance'], Decimal('100.00'))
        self.assertEqual(report.data['total_income'], Decimal('20.00'))

    def test_legacy_cash_and_finance_reports_are_tenant_scoped(self):
        category_a = ExpenseCategory.objects.create(
            tenant=self.tenant_a,
            name='Transport finance A',
        )
        category_b = ExpenseCategory.objects.create(
            tenant=self.tenant_b,
            name='Transport finance B',
        )
        expense_a = Expense.objects.create(
            tenant=self.tenant_a,
            category=category_a,
            account=self.account_a,
            title='Dépense caisse A',
            amount=Decimal('2.00'),
            created_by=self.user_a,
        )
        Expense.objects.create(
            tenant=self.tenant_b,
            category=category_b,
            account=self.account_b,
            title='Dépense caisse B',
            amount=Decimal('20.00'),
            created_by=self.user_b,
        )
        fund_a = Fund.objects.create(
            tenant=self.tenant_a,
            purpose='Fonds A',
            responsible=self.user_a,
            amount=Decimal('40.00'),
            created_by=self.user_a,
        )
        fund_b = Fund.objects.create(
            tenant=self.tenant_b,
            purpose='Fonds B',
            responsible=self.user_b,
            amount=Decimal('400.00'),
            created_by=self.user_b,
        )
        cashflow = self.client_a.get('/api/v1/cashflow/')
        transactions = self.client_a.get('/api/v1/cash/transactions/')
        summary = self.client_a.get('/api/v1/financial-summary/')
        report = self.client_a.get('/api/v1/reports/finance/')
        funds = self.client_a.get('/api/v1/finance/funds/')

        self.assertEqual(cashflow.status_code, 200)
        self.assertEqual(cashflow.data['cash_in'], 5.0)
        self.assertEqual(cashflow.data['cash_out'], 2.0)
        self.assertEqual(transactions.status_code, 200)
        self.assertEqual(
            [item['id'] for item in transactions.data if item['type'] == 'in'],
            [self.payment_a.id],
        )
        self.assertEqual(
            [item['id'] for item in transactions.data if item['type'] == 'out'],
            [expense_a.id],
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data['outstanding_balance'], 15.0)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['outstanding_balance'], 15.0)
        self.assertEqual(funds.status_code, 200)
        self.assertEqual([item['id'] for item in funds.data['results']], [fund_a.id])
        self.assertNotIn(fund_b.id, [item['id'] for item in funds.data['results']])

    def test_core_dashboards_reports_and_search_are_tenant_scoped(self):
        dashboard = self.client_a.get('/api/v1/dashboard/')
        overview = self.client_a.get('/api/v1/dashboard/overview/')
        report = self.client_a.get('/api/v1/reports/sales/')
        search = self.client_a.get(
            '/api/v1/search/',
            {'q': 'FINANCE-TENANT-B-PAYMENT'},
        )

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data['total_sales'], 20.0)
        self.assertEqual(dashboard.data['total_received'], 5.0)
        self.assertEqual(dashboard.data['total_customers'], 1)
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.data['sales_count'], 1)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['summary']['total_sales'], 20.0)
        self.assertEqual(report.data['summary']['total_received'], 5.0)
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.data['payments'], [])
        self.assertEqual(search.data['total'], 0)

    def test_foreign_account_and_transaction_routes_are_not_accessible(self):
        account_detail = self.client_a.get(
            f'/api/v1/finance/accounts/{self.account_b.id}/',
        )
        transaction_detail = self.client_a.get(
            f'/api/v1/finance/transactions/{self.transaction_b.id}/',
        )
        validate = self.client_a.post(
            f'/api/v1/finance/transactions/{self.transaction_b.id}/validate/',
            format='json',
        )

        self.assertEqual(account_detail.status_code, 404)
        self.assertEqual(transaction_detail.status_code, 404)
        self.assertEqual(validate.status_code, 404)

    def test_transaction_creation_and_transfer_reject_foreign_accounts(self):
        transaction = self.client_a.post(
            '/api/v1/finance/transactions/',
            {
                'transaction_type': 'income',
                'direction': 'in',
                'amount': '1.00',
                'account': self.account_b.id,
            },
            format='json',
        )
        transfer = self.client_a.post(
            '/api/v1/finance/transfers/',
            {
                'source_account': self.account_a.id,
                'destination_account': self.account_b.id,
                'amount': '1.00',
            },
            format='json',
        )

        self.assertEqual(transaction.status_code, 400)
        self.assertEqual(transfer.status_code, 400)
        self.assertEqual(
            FinancialTransaction.objects.filter(transaction_type='transfer').count(),
            0,
        )

    def test_expense_reads_and_creation_are_tenant_scoped(self):
        category_a = ExpenseCategory.objects.create(
            tenant=self.tenant_a,
            name='Transport',
        )
        category_b = ExpenseCategory.objects.create(
            tenant=self.tenant_b,
            name='Transport',
        )
        expense_a = Expense.objects.create(
            tenant=self.tenant_a,
            category=category_a,
            account=self.account_a,
            title='Dépense A',
            amount=Decimal('5.00'),
            created_by=self.user_a,
        )
        expense_b = Expense.objects.create(
            tenant=self.tenant_b,
            category=category_b,
            account=self.account_b,
            title='Dépense B',
            amount=Decimal('50.00'),
            created_by=self.user_b,
        )

        listed = self.client_a.get('/api/expenses/')
        foreign = self.client_a.get(f'/api/v1/expenses/{expense_b.id}/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item['id'] for item in listed.data], [expense_a.id])
        self.assertEqual(foreign.status_code, 404)

        created = self.client_a.post(
            '/api/expenses/',
            {
                'category': category_b.id,
                'account': self.account_a.id,
                'title': 'Dépense inter-tenant',
                'amount': '10.00',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 400)