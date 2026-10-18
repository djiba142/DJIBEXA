from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from users.models import User
from finance.models import FinancialAccount, FinancialTransaction
from .models import Expense, ExpenseCategory


class ExpenseApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='expense_admin',
            password='secret123',
            pin_code='1234',
            role='admin',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.category = ExpenseCategory.objects.create(name='Transport', description='Frais logistique')

    def test_create_expense(self):
        response = self.client.post(
            '/api/expenses/',
            {
                'category': self.category.id,
                'title': 'Transport fournisseur',
                'amount': '540000.00',
                'beneficiary': 'Logistics SARL',
                'reference': 'DEP-001',
                'justification': 'Livraison produit importé',
                'notes': 'Frais de transport international',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Expense.objects.count(), 1)
        self.assertEqual(response.data['title'], 'Transport fournisseur')

    def test_list_expenses(self):
        Expense.objects.create(
            category=self.category,
            title='Entretien véhicule',
            amount='150000.00',
            beneficiary='Garage NEXORA',
            reference='DEP-002',
            created_by=self.user,
        )

        response = self.client.get('/api/expenses/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['title'] == 'Entretien véhicule' for item in response.data))

    def test_expense_justification_attachment_upload(self):
        expense = Expense.objects.create(
            category=self.category,
            title='Dépense avec justificatif',
            amount='25000.00',
            created_by=self.user,
        )
        attachment = SimpleUploadedFile('facture.pdf', b'justificatif', content_type='application/pdf')

        response = self.client.post(
            f'/api/v1/expenses/{expense.id}/attachments/',
            {'file': attachment},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['original_name'], 'facture.pdf')

    def test_expense_attachment_rejects_unsupported_format(self):
        expense = Expense.objects.create(
            category=self.category,
            title='Justificatif interdit',
            amount='25000.00',
            created_by=self.user,
        )
        attachment = SimpleUploadedFile('preuve.exe', b'not allowed', content_type='application/octet-stream')
        response = self.client.post(
            f'/api/v1/expenses/{expense.id}/attachments/',
            {'file': attachment},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    def test_expense_workflow_creates_validated_finance_transaction(self):
        account = FinancialAccount.objects.create(name='Caisse dépenses', account_type='cash')
        response = self.client.post('/api/v1/expenses/', {
            'category': self.category.id,
            'title': 'Carburant mission',
            'amount': '125000.00',
            'account': account.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        expense_id = response.data['id']
        self.assertEqual(response.data['status'], 'draft')

        submit = self.client.post(f'/api/v1/expenses/{expense_id}/submit/', format='json')
        self.assertEqual(submit.status_code, 200)
        validate = self.client.post(f'/api/v1/expenses/{expense_id}/validate/', format='json')
        self.assertEqual(validate.status_code, 200)
        self.assertEqual(validate.data['status'], 'validated')
        self.assertTrue(FinancialTransaction.objects.filter(origin=f'expense:{expense_id}', status='validated').exists())

    def test_validated_expense_cannot_be_deleted(self):
        expense = Expense.objects.create(category=self.category, title='Dépense protégée', amount='1000.00', created_by=self.user)
        response = self.client.delete(f'/api/v1/expenses/{expense.id}/')
        self.assertEqual(response.status_code, 405)

    def test_rejected_expense_requires_reason(self):
        expense = Expense.objects.create(category=self.category, title='Dépense à rejeter', amount='1000.00', created_by=self.user, status='pending')
        response = self.client.post(f'/api/v1/expenses/{expense.id}/reject/', {}, format='json')
        self.assertEqual(response.status_code, 400)
