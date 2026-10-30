from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AppSetting, Company, PlatformTaskRun, Tenant
from customers.models import Customer
from notifications.models import Notification, TenantCreditReminderSettings
from notifications.reminders import generate_weekly_credit_reminders
from notifications.services import dispatch_notification
from sales.models import Sale
from users.models import User


class NotificationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='notif_admin',
            password='secret123',
            pin_code='1234',
            role='admin',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.customer = Customer.objects.create(full_name='Moussa Bah', phone='+224600004000')
        self.sale = Sale.objects.create(
            customer=self.customer,
            status='paid',
            payment_method='cash',
            total_amount='150000.00',
            amount_paid='150000.00',
        )

    def test_create_notification_record(self):
        response = self.client.post(
            '/api/notifications/',
            {
                'sale': self.sale.id,
                'channel': 'whatsapp',
                'event_type': 'sale_confirmed',
                'status': 'pending',
                'message': 'Votre vente a été confirmée',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['event_type'], 'sale_confirmed')

    def test_tenant_notifications_are_isolated_and_foreign_sales_cannot_be_used(self):
        tenant_a = Tenant.objects.create(slug='notification-a', name='Entreprise A', status='active')
        tenant_b = Tenant.objects.create(slug='notification-b', name='Entreprise B', status='active')
        user_a = User.objects.create_user(
            username='notification_admin_a',
            password='secret123',
            role='admin',
            tenant=tenant_a,
        )
        User.objects.create_user(
            username='notification_admin_b',
            password='secret123',
            role='admin',
            tenant=tenant_b,
        )
        customer_a = Customer.objects.create(
            tenant=tenant_a,
            full_name='Client A',
            phone='+224600005101',
        )
        customer_b = Customer.objects.create(
            tenant=tenant_b,
            full_name='Client B',
            phone='+224600005102',
        )
        sale_a = Sale.objects.create(
            tenant=tenant_a,
            customer=customer_a,
            status='paid',
            payment_method='cash',
            total_amount='10000.00',
            amount_paid='10000.00',
        )
        sale_b = Sale.objects.create(
            tenant=tenant_b,
            customer=customer_b,
            status='paid',
            payment_method='cash',
            total_amount='20000.00',
            amount_paid='20000.00',
        )
        notification_a = Notification.objects.create(
            sale=sale_a,
            customer=customer_a,
            event_type='sale_confirmed',
            message='Notification de A',
        )
        notification_b = Notification.objects.create(
            sale=sale_b,
            customer=customer_b,
            event_type='sale_confirmed',
            message='Notification de B',
        )
        self.client.force_authenticate(user=user_a)

        listing = self.client.get('/api/v1/notifications/')
        visible_ids = {
            item['id']
            for item in listing.data.get('results', listing.data)
        }
        self.assertIn(notification_a.id, visible_ids)
        self.assertNotIn(notification_b.id, visible_ids)
        self.assertEqual(
            self.client.get(f'/api/v1/notifications/{notification_b.id}/').status_code,
            404,
        )

        foreign_create = self.client.post(
            '/api/v1/notifications/',
            {'sale': sale_b.id, 'message': 'Cross-tenant'},
            format='json',
        )
        self.assertEqual(foreign_create.status_code, 400, foreign_create.data)

    def test_weekly_credit_reminder_api_only_generates_for_the_calling_tenant(self):
        tenant_a = Tenant.objects.create(slug='reminder-a', name='Entreprise A', status='active')
        tenant_b = Tenant.objects.create(slug='reminder-b', name='Entreprise B', status='active')
        user_a = User.objects.create_user(
            username='reminder_admin_a',
            password='secret123',
            role='admin',
            tenant=tenant_a,
        )
        customer_a = Customer.objects.create(
            tenant=tenant_a,
            full_name='Client A',
            phone='+224600005111',
        )
        customer_b = Customer.objects.create(
            tenant=tenant_b,
            full_name='Client B',
            phone='+224600005112',
        )
        for tenant, customer in ((tenant_a, customer_a), (tenant_b, customer_b)):
            Sale.objects.create(
                tenant=tenant,
                customer=customer,
                status='partial',
                payment_method='credit',
                total_amount=Decimal('100000'),
                amount_paid=Decimal('0'),
            )
        Company.objects.create(tenant=tenant_a, name='Société A', currency='GNF')
        Company.objects.create(tenant=tenant_b, name='Société B', currency='USD')
        self.client.force_authenticate(user=user_a)

        response = self.client.post('/api/v1/notifications/reminders/weekly/', format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['notification_ids']), 1)
        reminder = Notification.objects.get(pk=response.data['notification_ids'][0])
        self.assertEqual(reminder.tenant, tenant_a)
        self.assertEqual(reminder.customer, customer_a)
        self.assertIn('Société A', reminder.message)
        self.assertNotIn('Société B', reminder.message)

    def test_credit_reminder_settings_are_isolated_per_tenant(self):
        tenant_a = Tenant.objects.create(slug='reminder-settings-a', name='Entreprise A', status='active')
        tenant_b = Tenant.objects.create(slug='reminder-settings-b', name='Entreprise B', status='active')
        admin_a = User.objects.create_user(
            username='reminder_settings_admin_a',
            password='secret123',
            role='admin',
            tenant=tenant_a,
        )
        admin_b = User.objects.create_user(
            username='reminder_settings_admin_b',
            password='secret123',
            role='admin',
            tenant=tenant_b,
        )
        client_a = APIClient()
        client_a.force_authenticate(user=admin_a)
        client_b = APIClient()
        client_b.force_authenticate(user=admin_b)
        url = '/api/v1/notifications/reminders/settings/'

        response_a = client_a.patch(
            url,
            {'enabled': False, 'day_of_week': 2, 'time': '09:30'},
            format='json',
        )

        self.assertEqual(response_a.status_code, 200, response_a.data)
        self.assertFalse(response_a.data['enabled'])
        self.assertEqual(response_a.data['day_of_week'], 2)
        self.assertEqual(response_a.data['time'], '09:30')
        response_b = client_b.get(url)
        self.assertEqual(response_b.status_code, 200, response_b.data)
        self.assertTrue(response_b.data['enabled'])
        self.assertEqual(response_b.data['day_of_week'], 4)
        self.assertEqual(response_b.data['time'], '17:00')
        self.assertEqual(
            TenantCreditReminderSettings.objects.get(tenant=tenant_a).enabled,
            False,
        )
        self.assertFalse(TenantCreditReminderSettings.objects.filter(tenant=tenant_b).exists())
        self.assertFalse(AppSetting.objects.filter(key__startswith='credit_reminder_').exists())

    def test_notification_status_can_be_updated(self):
        response = self.client.post(
            '/api/notifications/',
            {
                'sale': self.sale.id,
                'channel': 'whatsapp',
                'event_type': 'payment_received',
                'status': 'sent',
                'message': 'Paiement reçu',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'sent')

    def test_notification_can_be_marked_as_read(self):
        response = self.client.post(
            '/api/notifications/',
            {
                'sale': self.sale.id,
                'channel': 'whatsapp',
                'event_type': 'invoice_sent',
                'status': 'sent',
                'message': 'Votre facture vient d’être envoyée',
                'recipient_phone': '+224600004000',
            },
            format='json',
        )
        notification_id = response.data['id']

        read_response = self.client.post(f'/api/notifications/{notification_id}/read/', format='json')

        self.assertEqual(read_response.status_code, 200)
        self.assertTrue(read_response.data['is_read'])
        self.assertIsNotNone(read_response.data['read_at'])

    def test_unconfigured_whatsapp_is_not_reported_as_sent(self):
        response = self.client.post(
            '/api/notifications/',
            {
                'sale': self.sale.id,
                'channel': 'whatsapp',
                'event_type': 'payment_received',
                'status': 'pending',
                'message': 'Paiement reçu pour votre achat.',
                'recipient_phone': '+224600004000',
            },
            format='json',
        )
        notification_id = response.data['id']

        dispatch_response = self.client.post(f'/api/notifications/{notification_id}/dispatch/', format='json')

        self.assertEqual(dispatch_response.status_code, 502)
        self.assertEqual(dispatch_response.data['status'], 'retry')
        self.assertEqual(dispatch_response.data['attempt_count'], 1)

    @patch('notifications.services.requests.post')
    def test_message_history_is_available_and_dispatch_is_not_repeatable(self, mock_post):
        AppSetting.objects.create(key='whatsapp_api_endpoint', value='https://example.test/whatsapp')
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {'status': 'queued'}
        response = self.client.post(
            '/api/v1/notifications/',
            {
                'sale': self.sale.id,
                'channel': 'whatsapp',
                'event_type': 'payment_received',
                'status': 'pending',
                'message': 'Historique message',
                'recipient_phone': '+224600004000',
            },
            format='json',
        )
        notification_id = response.data['id']
        dispatch_url = f'/api/v1/notifications/{notification_id}/dispatch/'
        self.assertEqual(self.client.post(dispatch_url, format='json').status_code, 200)
        self.assertEqual(self.client.post(dispatch_url, format='json').status_code, 409)

        history = self.client.get('/api/v1/messages/')
        self.assertEqual(history.status_code, 200)
        self.assertTrue(any(item['id'] == notification_id for item in history.data['results']))

    def test_weekly_credit_reminders_are_generated_for_customers_with_open_balance(self):
        customer = Customer.objects.create(full_name='Aminata Koné', phone='+224600005000')
        Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='credit',
            total_amount='120000.00',
            amount_paid='30000.00',
        )

        response = self.client.post('/api/notifications/reminders/weekly/', format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['created'], 1)
        self.assertTrue(
            Notification.objects.filter(
                recipient_phone=customer.phone,
                event_type='credit_reminder',
                channel='whatsapp',
            ).exists()
        )

    @patch('notifications.services.requests.post')
    def test_whatsapp_dispatch_uses_configured_provider(self, mock_post):
        AppSetting.objects.create(key='whatsapp_api_endpoint', value='https://example.test/whatsapp')
        AppSetting.objects.create(key='whatsapp_api_key', value='secret-key')
        AppSetting.objects.create(key='whatsapp_sender_id', value='NEXORA')
        notification = Notification.objects.create(
            sale=self.sale,
            channel='whatsapp',
            event_type='payment_received',
            status='pending',
            message='Paiement reçu pour votre commande.',
            recipient_phone='+224600004000',
        )

        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {'status': 'queued'}

        response = self.client.post(f'/api/notifications/{notification.id}/dispatch/', format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'sent')
        mock_post.assert_called_once()
        self.assertEqual(
            mock_post.call_args.kwargs['json']['message'],
            'DJIBEXA | Paiement reçu pour votre commande.',
        )
        self.assertEqual(
            mock_post.call_args.kwargs['headers']['Authorization'],
            'Bearer secret-key',
        )

    def test_message_history_includes_customer_and_export_metadata(self):
        notification = Notification.objects.create(
            sale=self.sale,
            channel='whatsapp',
            event_type='credit_reminder',
            status='pending',
            message='Rappel de paiement',
            recipient_phone='+224600004000',
        )
        history = self.client.get('/api/notifications/history/')
        self.assertEqual(history.status_code, 200)
        item = next(item for item in history.data['results'] if item['id'] == notification.id)
        self.assertEqual(item['customer_name'], self.customer.full_name)
        self.assertEqual(item['customer_phone'], self.customer.phone)

    def test_credit_reminders_group_sales_per_customer_and_are_weekly_idempotent(self):
        company = Company.objects.create(name='Kourouma Auto Part', currency='GNF')
        customer = Customer.objects.create(full_name='Alpha SARL', phone='+224600005001')
        Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('1000000'),
            amount_paid=Decimal('0'),
        )
        Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('2000000'),
            amount_paid=Decimal('0'),
        )
        settled = Customer.objects.create(full_name='Client soldé', phone='+224600005002')
        Sale.objects.create(
            customer=settled,
            status='paid',
            payment_method='credit',
            total_amount=Decimal('300000'),
            amount_paid=Decimal('300000'),
        )

        created = generate_weekly_credit_reminders()
        repeated = generate_weekly_credit_reminders()

        self.assertEqual(len(created), 1)
        self.assertEqual(repeated, [])
        reminder = Notification.objects.get(pk=created[0])
        self.assertEqual(reminder.customer, customer)
        self.assertIsNone(reminder.sale)
        self.assertIn('3 000 000 GNF', reminder.message)
        self.assertIn(company.name, reminder.message)
        self.assertFalse(Notification.objects.filter(customer=settled, event_type='credit_reminder').exists())

    @patch('notifications.services.requests.post')
    def test_queued_reminder_is_cancelled_if_paid_and_refreshes_balance_before_send(self, mock_post):
        AppSetting.objects.create(key='whatsapp_api_endpoint', value='https://example.test/whatsapp')
        settled_customer = Customer.objects.create(
            full_name='Compte soldé',
            phone='+224600005010',
        )
        still_owing_customer = Customer.objects.create(
            full_name='Compte partiel',
            phone='+224600005011',
        )
        settled_sale = Sale.objects.create(
            customer=settled_customer,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('100000'),
            amount_paid=Decimal('0'),
        )
        still_owing_sale = Sale.objects.create(
            customer=still_owing_customer,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('200000'),
            amount_paid=Decimal('0'),
        )
        reminders = generate_weekly_credit_reminders()
        by_customer = {
            reminder.customer_id: reminder
            for reminder in Notification.objects.filter(id__in=reminders)
        }
        settled_sale.amount_paid = settled_sale.total_amount
        settled_sale.status = 'paid'
        settled_sale.save(update_fields=['amount_paid', 'status'])
        still_owing_sale.amount_paid = Decimal('150000')
        still_owing_sale.save(update_fields=['amount_paid'])
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {'status': 'queued'}

        cancelled = dispatch_notification(by_customer[settled_customer.id].id)
        sent = dispatch_notification(by_customer[still_owing_customer.id].id)
        by_customer[settled_customer.id].refresh_from_db()
        by_customer[still_owing_customer.id].refresh_from_db()

        self.assertTrue(cancelled['cancelled'])
        self.assertEqual(by_customer[settled_customer.id].status, 'cancelled')
        self.assertEqual(by_customer[still_owing_customer.id].status, 'sent')
        self.assertIn('50 000 GNF', by_customer[still_owing_customer.id].message)
        self.assertEqual(mock_post.call_count, 1)

    def test_reminder_settings_are_persisted_and_restricted_to_managers(self):
        url = '/api/v1/notifications/reminders/settings/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['day_of_week'], 4)
        self.assertEqual(response.data['time'], '17:00')

        update = self.client.patch(
            url,
            {'enabled': False, 'day_of_week': 2, 'time': '09:30'},
            format='json',
        )
        self.assertEqual(update.status_code, 200)
        self.assertFalse(update.data['enabled'])
        self.assertEqual(update.data['day_of_week'], 2)
        self.assertEqual(update.data['time'], '09:30')

        self.user.role = 'sales'
        self.user.save(update_fields=['role'])
        denied = self.client.patch(url, {'enabled': True}, format='json')
        self.assertEqual(denied.status_code, 403)

    @patch('notifications.services.requests.post')
    def test_failed_whatsapp_is_retried_and_attempts_are_recorded(self, mock_post):
        AppSetting.objects.create(key='whatsapp_api_endpoint', value='https://example.test/whatsapp')
        notification = Notification.objects.create(
            sale=self.sale,
            channel='whatsapp',
            event_type='payment_received',
            status='pending',
            message='Paiement reçu',
            recipient_phone=self.customer.phone,
        )
        mock_post.side_effect = requests.ConnectionError('service indisponible')
        first = self.client.post(f'/api/v1/notifications/{notification.id}/dispatch/', format='json')
        notification.refresh_from_db()
        self.assertEqual(first.status_code, 502)
        self.assertEqual(notification.status, 'retry')
        self.assertEqual(notification.attempt_count, 1)
        self.assertIn('service indisponible', notification.last_error)
        self.assertIsNotNone(notification.next_attempt_at)

        notification.next_attempt_at = timezone.now() - timedelta(seconds=1)
        notification.save(update_fields=['next_attempt_at'])
        mock_post.side_effect = None
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {'status': 'queued'}
        second = self.client.post(f'/api/v1/notifications/{notification.id}/dispatch/', format='json')
        notification.refresh_from_db()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(notification.status, 'sent')
        self.assertEqual(notification.attempt_count, 2)

    @patch('notifications.services.requests.post')
    def test_scheduler_generates_and_dispatches_due_weekly_reminders(self, mock_post):
        AppSetting.objects.create(key='whatsapp_api_endpoint', value='https://example.test/whatsapp')
        AppSetting.objects.create(key='credit_reminder_day_of_week', value='4')
        AppSetting.objects.create(key='credit_reminder_time', value='17:00')
        customer = Customer.objects.create(full_name='Aminata Koné', phone='+224600005003')
        Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('120000'),
            amount_paid=Decimal('30000'),
        )
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {'status': 'queued'}
        local_time = timezone.make_aware(datetime(2026, 10, 9, 17, 0), timezone.get_current_timezone())
        from notifications.reminders import due_reminder_period

        self.assertIsNone(due_reminder_period(local_time - timedelta(minutes=1)))
        self.assertEqual(due_reminder_period(local_time), '2026-W41')
        with patch('notifications.management.commands.process_credit_notifications.timezone.now', return_value=local_time):
            call_command('process_credit_notifications', verbosity=0)

        reminder = Notification.objects.get(customer=customer, event_type='credit_reminder')
        self.assertEqual(reminder.status, 'sent')
        self.assertEqual(reminder.attempt_count, 1)
        mock_post.assert_called_once()
        task_run = PlatformTaskRun.objects.get(
            task_name='process_credit_notifications',
        )
        self.assertEqual(task_run.status, 'succeeded')
        self.assertIsNotNone(task_run.finished_at)
        self.assertIsNotNone(task_run.duration_ms)
        self.assertEqual(task_run.error_type, '')

    @patch('notifications.services.requests.post')
    def test_scheduler_applies_each_tenant_reminder_schedule(self, mock_post):
        AppSetting.objects.create(key='whatsapp_api_endpoint', value='https://example.test/whatsapp')
        tenant_a = Tenant.objects.create(slug='scheduled-reminder-a', name='Entreprise A', status='active')
        tenant_b = Tenant.objects.create(slug='scheduled-reminder-b', name='Entreprise B', status='active')
        suspended_tenant = Tenant.objects.create(
            slug='scheduled-reminder-suspended',
            name='Entreprise suspendue',
            status='suspended',
        )
        TenantCreditReminderSettings.objects.create(
            tenant=tenant_a,
            enabled=True,
            day_of_week=4,
            time='17:00',
        )
        TenantCreditReminderSettings.objects.create(
            tenant=tenant_b,
            enabled=True,
            day_of_week=5,
            time='17:00',
        )
        customer_a = Customer.objects.create(
            tenant=tenant_a,
            full_name='Client A',
            phone='+224600006001',
        )
        customer_b = Customer.objects.create(
            tenant=tenant_b,
            full_name='Client B',
            phone='+224600006002',
        )
        for tenant, customer in ((tenant_a, customer_a), (tenant_b, customer_b)):
            Sale.objects.create(
                tenant=tenant,
                customer=customer,
                status='partial',
                payment_method='credit',
                total_amount=Decimal('120000'),
                amount_paid=Decimal('30000'),
            )
        suspended_notification = Notification.objects.create(
            tenant=suspended_tenant,
            channel='whatsapp',
            event_type='sale_confirmed',
            status='pending',
            message='Ne pas envoyer',
            recipient_phone='+224600006003',
        )
        orphan_notification = Notification.objects.create(
            channel='whatsapp',
            event_type='sale_confirmed',
            status='pending',
            message='Ne pas envoyer sans rattachement',
            recipient_phone='+224600006004',
        )
        incoherent_notification = Notification.objects.create(
            tenant=tenant_a,
            customer=customer_b,
            channel='whatsapp',
            event_type='sale_confirmed',
            status='pending',
            message='Ne pas envoyer avec une relation incohérente',
            recipient_phone='+224600006005',
        )
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {'status': 'queued'}
        local_time = timezone.make_aware(
            datetime(2026, 10, 9, 17, 0),
            timezone.get_current_timezone(),
        )

        with patch(
            'notifications.management.commands.process_credit_notifications.timezone.now',
            return_value=local_time,
        ):
            call_command('process_credit_notifications', verbosity=0)

        reminder_a = Notification.objects.get(customer=customer_a, event_type='credit_reminder')
        self.assertEqual(reminder_a.tenant, tenant_a)
        self.assertEqual(reminder_a.status, 'sent')
        self.assertFalse(
            Notification.objects.filter(
                customer=customer_b,
                event_type='credit_reminder',
            ).exists(),
        )
        suspended_notification.refresh_from_db()
        self.assertEqual(suspended_notification.status, 'pending')
        self.assertEqual(suspended_notification.attempt_count, 0)
        orphan_notification.refresh_from_db()
        self.assertEqual(orphan_notification.status, 'pending')
        self.assertEqual(orphan_notification.attempt_count, 0)
        incoherent_notification.refresh_from_db()
        self.assertEqual(incoherent_notification.status, 'pending')
        self.assertEqual(incoherent_notification.attempt_count, 0)
        mock_post.assert_called_once()

    def test_scheduler_records_failure_without_storing_exception_message(self):
        with patch(
            'notifications.management.commands.process_credit_notifications.Command.'
            '_process_notifications',
            side_effect=RuntimeError('Contains private payload'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'Contains private payload'):
                call_command('process_credit_notifications', verbosity=0)

        task_run = PlatformTaskRun.objects.get(
            task_name='process_credit_notifications',
        )
        self.assertEqual(task_run.status, 'failed')
        self.assertEqual(task_run.error_type, 'RuntimeError')
        self.assertNotIn('private payload', task_run.error_type)
        self.assertIsNotNone(task_run.finished_at)

    def test_notification_export_csv_is_available(self):
        Notification.objects.create(
            sale=self.sale,
            channel='whatsapp',
            event_type='credit_reminder',
            status='pending',
            message='Rappel facture',
            recipient_phone='+224600004000',
        )

        response = self.client.get('/api/v1/notifications/export/?format=csv')

        self.assertEqual(
            response.status_code,
            200,
            response.data if hasattr(response, 'data') else response.content[:500],
        )
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('event_type', response.content.decode('utf-8'))
