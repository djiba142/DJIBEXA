import os
import subprocess
import sys
from importlib import import_module
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.apps import apps
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command, CommandError
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from customers.models import Customer
from inventory.models import InventoryCount, InventoryLocation, StockItem, StockMovement
from payments.models import Payment, PaymentAllocation
from purchases.models import PurchaseOrder, PurchaseOrderItem, PurchaseReceipt, PurchaseReceiptItem
from products.models import Category, Product
from sales.models import (
    CustomerOrder,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
    SaleReturnQuarantine,
)
from suppliers.models import Supplier
from users.models import User
from .mailer import create_branded_email
from .models import (
    AppSetting,
    AuditLog,
    BillingInvoice,
    Company,
    EmailOutbox,
    PlatformAuditLog,
    PlatformDemoRequest,
    PlatformModule,
    PlatformPayment,
    PlatformPlan,
    PlatformSettings,
    PlatformTaskRun,
    PaymentRecord,
    Tenant,
    TenantDomain,
    TenantMembership,
    TenantModuleOverride,
    TenantSubscription,
)
from .platform_entitlements import (
    module_for_request_path,
    tenant_module_is_enabled,
    user_has_required_module,
)
from .tenancy import tenant_for_user


class ProductionSettingsTests(SimpleTestCase):
    def run_production_settings_check(self, **overrides):
        backend_dir = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.pop('FRONTEND_BASE_URL', None)
        env.update({
            'DJANGO_ENV': 'production',
            'DJANGO_SECRET_KEY': (
                'test-only-production-key-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            ),
            'DJANGO_ALLOWED_HOSTS': 'localhost',
            'DJANGO_DEBUG': 'false',
            'DB_ENGINE': 'postgresql',
            'DB_NAME': 'test_only',
            'DB_USER': 'test_only',
            'DB_PASSWORD': 'not-a-real-password',
            'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'CORS_ALLOWED_ORIGINS': 'https://app.example.test',
            'CSRF_TRUSTED_ORIGINS': 'https://app.example.test',
        })
        env.update(overrides)
        return subprocess.run(
            [sys.executable, str(backend_dir / 'manage.py'), 'check'],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_production_rejects_sqlite_database_fallback(self):
        result = self.run_production_settings_check(DB_ENGINE='sqlite', DB_NAME=':memory:')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DB_ENGINE doit être configuré sur postgresql', result.stderr)

    def test_production_rejects_low_diversity_secret_key(self):
        result = self.run_production_settings_check(DJANGO_SECRET_KEY='a' * 64)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', result.stderr)

    def test_production_rejects_debug_mode(self):
        result = self.run_production_settings_check(DJANGO_DEBUG='true')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_DEBUG doit être désactivé', result.stderr)

    def test_production_rejects_wildcard_allowed_hosts(self):
        result = self.run_production_settings_check(DJANGO_ALLOWED_HOSTS='*')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_ALLOWED_HOSTS doit définir explicitement', result.stderr)

    def test_production_requires_https_frontend_url(self):
        for frontend_url in (
            '',
            'http://app.example.test',
            'https://user:secret@app.example.test',
            'https://app.example.test:invalid',
        ):
            with self.subTest(frontend_url=frontend_url):
                result = self.run_production_settings_check(
                    FRONTEND_BASE_URL=frontend_url,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FRONTEND_BASE_URL', result.stderr)

    def test_production_accepts_configured_https_frontend_url(self):
        result = self.run_production_settings_check(
            FRONTEND_BASE_URL='https://app.example.test',
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_rejects_non_delivering_email_backend(self):
        result = self.run_production_settings_check(
            FRONTEND_BASE_URL='https://app.example.test',
            EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('EMAIL_BACKEND doit permettre un véritable envoi', result.stderr)

    def test_production_requires_gmail_smtp_credentials_and_sender(self):
        result = self.run_production_settings_check(
            FRONTEND_BASE_URL='https://app.example.test',
            EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            EMAIL_HOST='smtp.gmail.com',
            EMAIL_HOST_USER='',
            EMAIL_HOST_PASSWORD='',
            DEFAULT_FROM_EMAIL='noreply@example.invalid',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('mot de passe d’application', result.stderr)

    def test_production_accepts_configured_gmail_smtp_credentials_and_sender(self):
        result = self.run_production_settings_check(
            FRONTEND_BASE_URL='https://app.example.test',
            EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            EMAIL_HOST='smtp.gmail.com',
            EMAIL_HOST_USER='sender@gmail.com',
            EMAIL_HOST_PASSWORD='test-app-password',
            DEFAULT_FROM_EMAIL='sender@gmail.com',
            EMAIL_PORT='587',
            EMAIL_USE_TLS='true',
            EMAIL_USE_SSL='false',
        )

        self.assertEqual(result.returncode, 0, result.stderr)


class BrandedEmailTests(SimpleTestCase):
    @override_settings(FRONTEND_BASE_URL='https://erp.example.test')
    def test_email_alternative_contains_djibexa_logo_and_escapes_message(self):
        email = create_branded_email(
            subject='Notification DJIBEXA',
            message='<script>alert("x")</script>',
            recipient_list=['user@example.test'],
        )

        self.assertIn('<script>alert("x")</script>', email.body)
        html_message, content_type = email.alternatives[0]
        self.assertEqual(content_type, 'text/html')
        self.assertIn('https://erp.example.test/brand/kourouma-logo.svg', html_message)
        self.assertIn('&lt;script&gt;', html_message)

    def test_email_action_is_a_safe_html_link_and_remains_in_plain_text(self):
        action_url = 'https://erp.example.test/reset-password?uid=1&token=token'
        email = create_branded_email(
            subject='Invitation DJIBEXA',
            message=f'Utilisez ce lien :\n{action_url}',
            recipient_list=['user@example.test'],
            action_url=action_url,
            action_label='Choisir mon mot de passe',
        )

        html_message, _ = email.alternatives[0]
        self.assertIn('href="https://erp.example.test/reset-password?uid=1&amp;token=token"', html_message)
        self.assertIn('Choisir mon mot de passe', html_message)
        self.assertIn(action_url, email.body)


class DevelopmentCorsSettingsTests(SimpleTestCase):
    def test_default_settings_allow_tanstack_local_origins(self):
        backend_dir = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.update({
            'DJANGO_SETTINGS_MODULE': 'nexora_backend.settings',
            'DJANGO_ENV': 'development',
            'DJANGO_DEBUG': 'true',
            'DB_ENGINE': 'sqlite',
            'DB_NAME': ':memory:',
            'CORS_ALLOWED_ORIGINS': '',
            'CSRF_TRUSTED_ORIGINS': '',
        })
        script = (
            'from django.conf import settings; '
            'origins=("http://localhost:3000", "http://127.0.0.1:3000", '
            '"http://localhost:3001", "http://127.0.0.1:3001", '
            '"http://localhost:3002", "http://127.0.0.1:3002"); '
            'assert all(origin in settings.CORS_ALLOWED_ORIGINS for origin in origins); '
            'assert all(origin in settings.CSRF_TRUSTED_ORIGINS for origin in origins)'
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


class DjangoAdminBrandingTests(TestCase):
    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    })
    def test_admin_login_displays_djibexa_branding_and_logo(self):
        response = self.client.get('/admin/login/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DJIBEXA')
        self.assertContains(response, 'core/djibexa-admin-logo.svg')
        self.assertContains(response, 'core/admin.css')


class CoreApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='admin_core',
            password='secret123',
            pin_code='1234',
            role='admin',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_inactive_tenant_membership_blocks_legacy_tenant_assignment(self):
        tenant = Tenant.objects.create(
            slug='membership-authorization',
            name='Membership authorization',
        )
        member = User.objects.create_user(
            username='membership_authorization_user',
            password='secret123',
            tenant=tenant,
            role='sales',
        )
        membership = TenantMembership.objects.create(
            tenant=tenant,
            user=member,
            role='sales',
            is_active=False,
        )

        self.assertIsNone(tenant_for_user(member))

        membership.is_active = True
        membership.save(update_fields=['is_active', 'updated_at'])
        self.assertEqual(tenant_for_user(member), tenant)

    def test_platform_admin_can_verify_dns_domain_and_choose_primary(self):
        platform_admin = User.objects.create_user(
            username='platform_domain_admin',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='domain-verification',
            name='Domain verification',
        )
        self.client.force_authenticate(user=platform_admin)

        created = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/domains/',
            {
                'hostname': 'ERP.Example.Test',
                'domain_type': 'application',
                'reason': 'Domaine autorisé pour le tenant.',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        domain = TenantDomain.objects.get(pk=created.data['domain']['id'])
        challenge_value = created.data['challenge']['recordValue']
        self.assertEqual(domain.hostname, 'erp.example.test')
        self.assertNotIn(challenge_value, domain.verification_token_hash)

        answer = SimpleNamespace(strings=[challenge_value.encode('utf-8')])
        with patch(
            'core.platform_views.dns.resolver.Resolver.resolve',
            return_value=[answer],
        ):
            verified = self.client.post(
                f'/api/v1/platform/domains/{domain.pk}/verify/',
                {'reason': 'TXT DNS contrôlé.'},
                format='json',
            )
        self.assertEqual(verified.status_code, 200, verified.data)
        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, 'verified')
        self.assertIsNotNone(domain.verified_at)
        self.assertEqual(domain.verification_token_hash, '')

        primary = self.client.post(
            f'/api/v1/platform/domains/{domain.pk}/set-primary/',
            {'reason': 'Domaine confirmé pour l’application.'},
            format='json',
        )
        self.assertEqual(primary.status_code, 200, primary.data)
        domain.refresh_from_db()
        self.assertTrue(domain.is_primary)
        audit = PlatformAuditLog.objects.filter(
            tenant=tenant,
            entity_type='tenant_domain',
        ).latest('created_at')
        self.assertEqual(audit.entity_id, str(domain.pk))
        self.assertEqual(audit.reason, 'Domaine confirmé pour l’application.')

    def test_platform_tenant_archive_restore_and_deletion_request_preserve_data(self):
        platform_admin = User.objects.create_user(
            username='platform_tenant_lifecycle',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='tenant-lifecycle',
            name='Tenant lifecycle',
            status='active',
        )
        self.client.force_authenticate(user=platform_admin)

        archived = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/archive/',
            {'reason': 'Archivage demandé.'},
            format='json',
        )
        self.assertEqual(archived.status_code, 200, archived.data)
        self.assertEqual(archived.data['status'], 'archived')
        tenant.refresh_from_db()
        self.assertIsNotNone(tenant.archived_at)

        restored = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/restore/',
            {'reason': 'Réactivation administrative demandée.'},
            format='json',
        )
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(restored.data['status'], 'suspended')
        self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())

        requested = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/request-deletion/',
            {'reason': 'Demande de suppression reçue.'},
            format='json',
        )
        self.assertEqual(requested.status_code, 200, requested.data)
        self.assertEqual(requested.data['status'], 'deletion_pending')
        self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())

    @override_settings(FRONTEND_BASE_URL='https://app.example.test')
    def test_root_redirects_to_configured_frontend(self):
        response = self.client.get('/')

        self.assertRedirects(
            response,
            'https://app.example.test',
            fetch_redirect_response=False,
        )

    def test_platform_overview_requires_platform_admin(self):
        response = self.client.get('/api/v1/platform/overview/')

        self.assertEqual(response.status_code, 403)

    def test_platform_monitoring_requires_platform_admin(self):
        response = self.client.get('/api/v1/platform/monitoring/')

        self.assertEqual(response.status_code, 403)

    def test_platform_monitoring_reports_measured_checks_and_unconfigured_sources(self):
        platform_admin = User.objects.create_user(
            username='platform_monitoring_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)

        response = self.client.get('/api/v1/platform/monitoring/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('checkedAt', response.data)
        self.assertEqual(
            response.data['system']['application']['status'],
            'operational',
        )
        self.assertEqual(
            response.data['system']['database']['status'],
            'operational',
        )
        storage = response.data['system']['storage']
        self.assertIn(storage['status'], {'operational', 'unavailable'})
        self.assertEqual(
            set(response.data['unconfigured']),
            {
                'serverErrors',
                'applicationErrors',
                'backgroundTasks',
                'backups',
                'securityAlerts',
            },
        )
        self.assertEqual(
            response.data['tasks']['creditNotifications'],
            {
                'status': 'unconfigured',
                'startedAt': None,
                'finishedAt': None,
                'durationMs': None,
                'errorType': None,
                'history': [],
            },
        )

    def test_platform_monitoring_exposes_recent_task_run_history_safely(self):
        platform_admin = User.objects.create_user(
            username='platform_task_monitoring_admin',
            password='secret123',
            is_platform_admin=True,
        )
        PlatformTaskRun.objects.create(
            task_name='process_credit_notifications',
            status='succeeded',
            started_at=timezone.now() - timedelta(minutes=5),
            finished_at=timezone.now() - timedelta(minutes=4),
            duration_ms=800,
        )
        PlatformTaskRun.objects.create(
            task_name='process_credit_notifications',
            status='failed',
            started_at=timezone.now() - timedelta(minutes=3),
            finished_at=timezone.now() - timedelta(minutes=2),
            duration_ms=1234,
            error_type='CommandError',
        )
        for index in range(11):
            started_at = timezone.now() - timedelta(minutes=10 + index)
            PlatformTaskRun.objects.create(
                task_name='process_credit_notifications',
                status='succeeded',
                started_at=started_at,
                finished_at=started_at + timedelta(seconds=1),
                duration_ms=1000,
            )
        PlatformTaskRun.objects.create(
            task_name='unrelated_task',
            status='failed',
            error_type='DoNotExpose',
        )
        self.client.force_authenticate(user=platform_admin)

        response = self.client.get('/api/v1/platform/monitoring/')

        self.assertEqual(response.status_code, 200)
        task = response.data['tasks']['creditNotifications']
        self.assertEqual(task['status'], 'failed')
        self.assertEqual(task['durationMs'], 1234)
        self.assertEqual(task['errorType'], 'CommandError')
        self.assertNotIn('details', task)
        self.assertNotIn('message', task)
        self.assertEqual(len(task['history']), 10)
        self.assertEqual(task['history'][0]['status'], 'failed')
        self.assertEqual(task['history'][0]['durationMs'], 1234)
        self.assertTrue(
            all(run['status'] == 'succeeded' for run in task['history'][1:]),
        )
        self.assertNotIn('DoNotExpose', str(response.data))

    def test_platform_monitoring_surfaces_database_failure_without_followup_query(self):
        platform_admin = User.objects.create_user(
            username='platform_database_monitoring_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)

        with patch(
            'core.platform_views.connection.cursor',
            side_effect=DatabaseError,
        ):
            response = self.client.get('/api/v1/platform/monitoring/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['system']['database']['status'], 'unavailable')
        self.assertEqual(
            response.data['tasks']['creditNotifications']['status'],
            'unavailable',
        )

    def test_platform_monitoring_surfaces_task_history_database_failure(self):
        platform_admin = User.objects.create_user(
            username='platform_task_history_database_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)

        with (
            patch(
                'core.platform_views.PlatformTaskRun.objects.filter',
                side_effect=DatabaseError,
            ),
            self.assertLogs('core.platform_views', level='ERROR'),
        ):
            response = self.client.get('/api/v1/platform/monitoring/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['system']['database']['status'],
            'operational',
        )
        self.assertEqual(
            response.data['tasks']['creditNotifications'],
            {
                'status': 'unavailable',
                'startedAt': None,
                'finishedAt': None,
                'durationMs': None,
                'errorType': None,
                'history': [],
            },
        )

    def test_platform_overview_exposes_only_tenant_management_metadata(self):
        tenant = Tenant.objects.create(
            slug='platform-overview-tenant',
            name='Tenant aperçu plateforme',
            status='active',
            max_users=6,
        )
        User.objects.create_user(
            username='platform_overview_member',
            password='secret123',
            email='private@example.com',
            role='sales',
            tenant=tenant,
        )
        platform_admin = User.objects.create_user(
            username='platform_overview_admin',
            password='secret123',
            role='admin',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)

        response = self.client.get('/api/v1/platform/overview/')

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['limits']['maxTenants'])
        self.assertEqual(response.data['counts']['activeUsers'], 1)
        summary = next(
            item for item in response.data['tenants']
            if item['id'] == tenant.id
        )
        self.assertEqual(summary['activeUsers'], 1)
        self.assertEqual(summary['maxUsers'], 6)
        self.assertNotIn('email', summary)
        self.assertNotIn('customers', summary)
        self.assertNotIn('sales', summary)
        self.assertNotIn('private@example.com', str(response.data))

    def test_platform_overview_is_available_to_session_authenticated_platform_admin(self):
        platform_admin = User.objects.create_user(
            username='platform_session_admin',
            password='secret123',
            role='sales',
            is_platform_admin=True,
        )
        client = APIClient()
        self.assertTrue(client.login(
            username='platform_session_admin',
            password='secret123',
        ))

        response = client.get('/api/v1/platform/overview/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts']['tenants'], Tenant.objects.count())

    def test_platform_admin_can_create_activate_suspend_and_resume_tenant(self):
        platform_admin = User.objects.create_user(
            username='platform_tenant_manager',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)
        created = self.client.post(
            '/api/v1/platform/tenants/',
            {
                'name': 'Entreprise pilote',
                'slug': 'entreprise-pilote',
                'max_users': 8,
            },
            format='json',
        )

        self.assertEqual(created.status_code, 201, created.data)
        tenant_id = created.data['id']
        self.assertEqual(created.data['status'], 'pending')
        self.assertEqual(created.data['maxUsers'], 8)
        self.assertIsNone(created.data['trialActivatedAt'])
        self.assertEqual(
            PlatformAuditLog.objects.filter(
                tenant_id=tenant_id,
                action='create',
            ).count(),
            1,
        )

        activated = self.client.post(
            f'/api/v1/platform/tenants/{tenant_id}/activate/',
            format='json',
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        self.assertEqual(activated.data['status'], 'active')
        self.assertNotIn('invitationEmailQueued', activated.data)
        initial_expiration = activated.data['trialEndsAt']

        suspended = self.client.post(
            f'/api/v1/platform/tenants/{tenant_id}/suspend/',
            format='json',
        )
        self.assertEqual(suspended.status_code, 200, suspended.data)
        self.assertEqual(suspended.data['status'], 'suspended')

        resumed = self.client.post(
            f'/api/v1/platform/tenants/{tenant_id}/resume/',
            format='json',
        )
        self.assertEqual(resumed.status_code, 200, resumed.data)
        self.assertEqual(resumed.data['status'], 'active')
        self.assertEqual(resumed.data['trialEndsAt'], initial_expiration)
        self.assertEqual(
            PlatformAuditLog.objects.filter(tenant_id=tenant_id).count(),
            4,
        )

    def test_platform_admin_can_invite_first_tenant_admin_securely(self):
        platform_admin = User.objects.create_user(
            username='platform_initial_admin_inviter',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='first-admin-invitation',
            name='Entreprise invitée',
        )
        self.client.force_authenticate(user=platform_admin)

        response = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/admin-invitation/',
            {
                'username': 'initial_admin',
                'email': 'initial.admin@example.com',
                'first_name': 'Initial',
                'last_name': 'Admin',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data, {'invited': True, 'emailQueued': False})
        invited_user = User.objects.get(username='initial_admin')
        self.assertEqual(invited_user.tenant, tenant)
        self.assertEqual(invited_user.role, 'admin')
        self.assertFalse(invited_user.is_active)
        self.assertTrue(invited_user.invitation_pending)
        self.assertTrue(invited_user.must_change_password)
        self.assertFalse(invited_user.has_usable_password())
        overview = self.client.get('/api/v1/platform/overview/')
        self.assertTrue(overview.data['tenants'][0]['hasUsers'])
        self.assertEqual(overview.data['tenants'][0]['activeUsers'], 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotIn('initial.admin@example.com', str(response.data))
        self.assertEqual(
            PlatformAuditLog.objects.get(
                tenant=tenant,
                action='invite_admin',
            ).details,
            {'role': 'admin'},
        )
        audit_response = self.client.get('/api/v1/platform/audit/')
        self.assertEqual(audit_response.status_code, 200)
        self.assertEqual(
            audit_response.data['results'][0]['details'],
            {'role': 'admin'},
        )
        self.assertNotIn('initial.admin@example.com', str(audit_response.data))

        self.client.force_authenticate(user=None)
        blocked_login = self.client.post(
            '/api/v1/users/login/',
            {
                'identifier': invited_user.username,
                'password': 'TemporaryPassword!2026',
            },
            format='json',
        )
        self.assertEqual(blocked_login.status_code, 401)
        self.client.force_authenticate(user=platform_admin)
        activated = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/activate/',
            format='json',
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        self.assertTrue(activated.data['invitationEmailQueued'])
        call_command('process_email_outbox')
        self.assertEqual(len(mail.outbox), 1)
        invitation_email = mail.outbox[0]
        self.assertIn(tenant.name, invitation_email.body)
        self.assertIn(invited_user.username, invitation_email.body)
        self.assertIn('purpose=invitation', invitation_email.body)
        self.assertNotIn('mot de passe provisoire', invitation_email.body.lower())
        self.assertIn('Choisir mon mot de passe', invitation_email.alternatives[0][0])
        self.assertIn('kourouma-logo.svg', invitation_email.alternatives[0][0])
        setup_url = next(
            line for line in invitation_email.body.splitlines()
            if '/reset-password?uid=' in line
        )
        token = parse_qs(urlsplit(setup_url).query)['token'][0]
        invited_user.refresh_from_db()
        self.assertTrue(invited_user.is_active)
        self.assertTrue(invited_user.invitation_pending)
        self.client.force_authenticate(user=None)
        password_setup = self.client.post(
            '/api/v1/users/pin-reset/confirm/',
            {
                'uid': urlsafe_base64_encode(force_bytes(invited_user.pk)),
                'token': token,
                'password': 'ChosenPassword!2026',
            },
            format='json',
        )
        self.assertEqual(password_setup.status_code, 200, password_setup.data)
        invited_user.refresh_from_db()
        self.assertTrue(invited_user.check_password('ChosenPassword!2026'))
        self.assertFalse(invited_user.must_change_password)
        successful_login = self.client.post(
            '/api/v1/users/login/',
            {
                'identifier': invited_user.username,
                'password': 'ChosenPassword!2026',
            },
            format='json',
        )
        self.assertEqual(successful_login.status_code, 200, successful_login.data)
        self.assertFalse(successful_login.data['user']['must_change_password'])

    def test_tenant_admin_invitation_checks_existing_identity(self):
        platform_admin = User.objects.create_user(
            username='platform_invitation_guard',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='invitation-guard-tenant',
            name='Entreprise invitation contrôlée',
        )
        second_tenant = Tenant.objects.create(
            slug='invitation-identity-guard',
            name='Autre entreprise invitation contrôlée',
        )
        self.client.force_authenticate(user=platform_admin)
        endpoint = f'/api/v1/platform/tenants/{tenant.pk}/admin-invitation/'
        payload = {
            'username': 'reused_initial_admin',
            'email': 'reused.initial.admin@example.com',
        }

        first = self.client.post(endpoint, payload, format='json')
        duplicate = self.client.post(
            endpoint,
            {
                'username': 'another_initial_admin',
                'email': 'another.initial.admin@example.com',
            },
            format='json',
        )
        duplicate_identity = self.client.post(
            f'/api/v1/platform/tenants/{second_tenant.pk}/admin-invitation/',
            payload,
            format='json',
        )

        self.assertEqual(first.status_code, 201, first.data)
        self.assertFalse(first.data['emailQueued'])
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate_identity.status_code, 400)
        self.assertEqual(User.objects.filter(tenant=tenant).count(), 1)
        self.assertFalse(User.objects.filter(tenant=second_tenant).exists())
        invited_admin = User.objects.get(tenant=tenant)
        self.assertFalse(invited_admin.is_active)
        self.assertTrue(invited_admin.invitation_pending)
        self.assertEqual(len(mail.outbox), 0)

    def test_platform_admin_can_invite_first_admin_after_tenant_activation(self):
        platform_admin = User.objects.create_user(
            username='platform_active_tenant_inviter',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='already-active-invitation',
            name='Entreprise déjà activée',
        )
        tenant.activate_trial()
        self.client.force_authenticate(user=platform_admin)

        invited = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/admin-invitation/',
            {
                'username': 'active_tenant_admin',
                'email': 'active.tenant.admin@example.com',
            },
            format='json',
        )

        self.assertEqual(invited.status_code, 201, invited.data)
        self.assertTrue(invited.data['emailQueued'])
        call_command('process_email_outbox')
        invited_user = User.objects.get(username='active_tenant_admin')
        self.assertTrue(invited_user.is_active)
        self.assertTrue(invited_user.invitation_pending)
        self.assertTrue(invited_user.must_change_password)
        self.assertFalse(invited_user.has_usable_password())
        self.assertIn('purpose=invitation', mail.outbox[0].body)
        self.assertNotIn('mot de passe provisoire', mail.outbox[0].body.lower())
        self.assertIn('Choisir mon mot de passe', mail.outbox[0].alternatives[0][0])
        setup_url = next(
            line for line in mail.outbox[0].body.splitlines()
            if '/reset-password?uid=' in line
        )
        token = parse_qs(urlsplit(setup_url).query)['token'][0]
        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            '/api/v1/users/login/',
            {
                'identifier': invited_user.username,
                'password': 'TemporaryPassword!2026',
            },
            format='json',
        )
        self.assertEqual(login_response.status_code, 403, login_response.data)
        password_setup = self.client.post(
            '/api/v1/users/pin-reset/confirm/',
            {
                'uid': urlsafe_base64_encode(force_bytes(invited_user.pk)),
                'token': token,
                'password': 'ChosenPassword!2026',
            },
            format='json',
        )
        self.assertEqual(password_setup.status_code, 200, password_setup.data)
        invited_user.refresh_from_db()
        self.assertTrue(invited_user.check_password('ChosenPassword!2026'))
        self.assertFalse(invited_user.must_change_password)

    def test_platform_admin_invitation_rolls_back_when_outbox_cannot_be_queued(self):
        platform_admin = User.objects.create_user(
            username='platform_invitation_mail_failure',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='invitation-mail-failure',
            name='Entreprise e-mail indisponible',
        )
        tenant.activate_trial()
        self.client.force_authenticate(user=platform_admin)

        with patch(
            'core.platform_views.send_password_setup_email',
            side_effect=RuntimeError('SMTP unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    f'/api/v1/platform/tenants/{tenant.pk}/admin-invitation/',
                    {
                        'username': 'failed_invitation_admin',
                        'email': 'failed.invitation@example.com',
                    },
                    format='json',
                )

        self.assertFalse(User.objects.filter(tenant=tenant).exists())
        self.assertFalse(
            PlatformAuditLog.objects.filter(
                tenant=tenant,
                action='invite_admin',
            ).exists(),
        )

    def test_tenant_activation_queues_invitation_for_reliable_delivery(self):
        platform_admin = User.objects.create_user(
            username='platform_activation_mail_failure',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='activation-mail-failure',
            name='Entreprise e-mail indisponible',
        )
        invited_admin = User.objects.create_user(
            username='activation_mail_failure_admin',
            email='activation.mail.failure@example.com',
            password=None,
            tenant=tenant,
            is_active=False,
            invitation_pending=True,
            must_change_password=True,
        )
        self.client.force_authenticate(user=platform_admin)

        response = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/activate/',
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'active')
        self.assertTrue(response.data['invitationEmailQueued'])
        self.assertEqual(EmailOutbox.objects.filter(status='queued').count(), 1)
        tenant.refresh_from_db()
        invited_admin.refresh_from_db()
        self.assertEqual(tenant.status, 'active')
        self.assertTrue(invited_admin.is_active)
        self.assertTrue(invited_admin.invitation_pending)
        self.assertTrue(
            PlatformAuditLog.objects.filter(
                tenant=tenant,
                action='activate',
            ).exists(),
        )

    def test_pending_admin_invitation_cannot_exceed_global_user_capacity(self):
        platform_admin = User.objects.create_user(
            username='platform_invitation_capacity',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='invitation-capacity',
            name='Entreprise capacité invitation',
        )
        other_tenant = Tenant.objects.create(
            slug='invitation-capacity-other',
            name='Autre entreprise capacité invitation',
        )
        self.client.force_authenticate(user=platform_admin)
        invited = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/admin-invitation/',
            {
                'username': 'capacity_initial_admin',
                'email': 'capacity.initial.admin@example.com',
            },
            format='json',
        )
        self.assertEqual(invited.status_code, 201, invited.data)

        PlatformSettings.objects.filter(pk=1).update(max_active_users=1)
        User.objects.create_user(
            username='capacity_other_tenant_user',
            email='capacity.other@example.com',
            password='secret123',
            tenant=other_tenant,
        )
        response = self.client.post(
            f'/api/v1/platform/tenants/{tenant.pk}/activate/',
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        invited_user = User.objects.get(username='capacity_initial_admin')
        self.assertFalse(invited_user.is_active)
        self.assertTrue(invited_user.invitation_pending)
        self.assertTrue(invited_user.must_change_password)
        tenant.refresh_from_db()
        self.assertEqual(tenant.status, 'pending')

    def test_password_reset_does_not_reactivate_non_invited_inactive_user(self):
        inactive_user = User.objects.create_user(
            username='inactive_not_invited',
            email='inactive.not.invited@example.com',
            password='secret123',
            is_active=False,
        )
        response = self.client.post(
            '/api/v1/users/pin-reset/confirm/',
            {
                'uid': urlsafe_base64_encode(force_bytes(inactive_user.pk)),
                'token': default_token_generator.make_token(inactive_user),
                'password': 'NewResetPassword!2026',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        inactive_user.refresh_from_db()
        self.assertFalse(inactive_user.is_active)
        self.assertFalse(inactive_user.check_password('NewResetPassword!2026'))

    def test_platform_tenant_creation_enforces_platform_limit(self):
        platform_admin = User.objects.create_user(
            username='platform_tenant_limit',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)
        PlatformSettings.objects.filter(pk=1).update(max_tenants=Tenant.objects.count())

        response = self.client.post(
            '/api/v1/platform/tenants/',
            {
                'name': 'Entreprise au-delà du quota',
                'slug': 'entreprise-hors-quota',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Tenant.objects.filter(slug='entreprise-hors-quota').exists())

    def test_platform_tenant_creation_has_no_default_ten_tenant_limit(self):
        platform_admin = User.objects.create_user(
            username='platform_tenant_unlimited',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)
        Tenant.objects.bulk_create([
            Tenant(
                code=f'company-{index}',
                slug=f'company-{index}',
                name=f'Entreprise {index}',
            )
            for index in range(9)
        ])

        response = self.client.post(
            '/api/v1/platform/tenants/',
            {
                'name': 'Entreprise numéro onze',
                'slug': 'entreprise-numero-onze',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Tenant.objects.count(), 11)
        self.assertIsNone(PlatformSettings.objects.get(pk=1).max_tenants)

    def test_platform_tenant_capacity_cannot_be_lower_than_active_users(self):
        tenant = Tenant.objects.create(
            slug='tenant-capacity-admin',
            name='Tenant capacité',
        )
        User.objects.create_user(
            username='tenant_capacity_member',
            password='secret123',
            role='sales',
            tenant=tenant,
        )
        second_tenant_user = User.objects.create_user(
            username='tenant_capacity_member_two',
            password='secret123',
            role='sales',
            tenant=tenant,
        )
        platform_admin = User.objects.create_user(
            username='platform_capacity_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)

        response = self.client.patch(
            f'/api/v1/platform/tenants/{tenant.id}/',
            {'max_users': 1},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        second_tenant_user.is_active = False
        second_tenant_user.save(update_fields=['is_active'])
        response = self.client.patch(
            f'/api/v1/platform/tenants/{tenant.id}/',
            {'max_users': 1},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['maxUsers'], 1)

    def test_tenant_admin_cannot_use_platform_management_or_audit_api(self):
        platform_admin = User.objects.create_user(
            username='platform_access_guard',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='tenant-platform-access-guard',
            name='Tenant contrôle accès',
        )
        tenant_user = User.objects.create_user(
            username='tenant_platform_guard',
            password='secret123',
            role='admin',
            tenant=tenant,
        )
        PlatformAuditLog.objects.create(
            actor=platform_admin,
            tenant=tenant,
            action='create',
            details={'name': tenant.name},
        )
        self.client.force_authenticate(user=tenant_user)

        create = self.client.post(
            '/api/v1/platform/tenants/',
            {
                'name': 'Interdit',
                'slug': 'interdit-tenant',
            },
            format='json',
        )
        audit = self.client.get('/api/v1/platform/audit/')

        self.assertEqual(create.status_code, 403)
        self.assertEqual(audit.status_code, 403)
        self.assertFalse(Tenant.objects.filter(slug='interdit-tenant').exists())

        self.client.force_authenticate(user=platform_admin)
        audit = self.client.get('/api/v1/platform/audit/')
        self.assertEqual(audit.status_code, 200)
        self.assertEqual(audit.data['results'][0]['tenant'], tenant.name)
        self.assertNotIn('sales', str(audit.data))

    def test_platform_audit_supports_search_action_filter_and_pagination(self):
        platform_admin = User.objects.create_user(
            username='platform_audit_filters',
            password='secret123',
            is_platform_admin=True,
        )
        tenant = Tenant.objects.create(
            slug='audit-search-tenant',
            name='Audit Search Company',
        )
        self.client.force_authenticate(user=platform_admin)

        for index in range(3):
            PlatformAuditLog.objects.create(
                actor=platform_admin,
                tenant=tenant,
                action='update',
                details={
                    'field': 'max_users',
                    'old_value': 10,
                    'new_value': index,
                    'access_token': 'must-not-be-exposed',
                    'internal_payload': {'email': 'private@example.test'},
                },
            )
        for index in range(2):
            PlatformAuditLog.objects.create(
                actor=platform_admin,
                tenant=tenant,
                action='suspend',
                details={'status': 'suspended', 'index': index},
            )

        paginated = self.client.get(
            '/api/v1/platform/audit/',
            {'action': 'update', 'page': 1, 'page_size': 2},
        )
        searched = self.client.get(
            '/api/v1/platform/audit/',
            {'search': 'Search Company', 'action': 'suspend', 'page_size': 10},
        )
        invalid_filter = self.client.get(
            '/api/v1/platform/audit/',
            {'action': 'delete'},
        )

        self.assertEqual(paginated.status_code, 200)
        self.assertEqual(paginated.data['count'], 3)
        self.assertEqual(len(paginated.data['results']), 2)
        self.assertIsNotNone(paginated.data['next'])
        self.assertIsNone(paginated.data['previous'])
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(searched.data['count'], 2)
        self.assertTrue(
            all(entry['action'] == 'suspend' for entry in searched.data['results']),
        )
        update_details = paginated.data['results'][0]['details']
        self.assertEqual(
            set(update_details),
            {'field', 'old_value', 'new_value'},
        )
        self.assertNotIn('must-not-be-exposed', str(paginated.data))
        self.assertNotIn('private@example.test', str(paginated.data))
        self.assertEqual(invalid_filter.status_code, 400)

    def test_platform_admin_login_payload_identifies_account_without_business_roles(self):
        User.objects.create_user(
            username='platform_login_admin',
            password='secret123',
            role='admin',
            is_platform_admin=True,
            additional_roles=['sales', 'stock'],
        )

        response = self.client.post(
            '/api/v1/users/login/',
            {
                'identifier': 'platform_login_admin',
                'password': 'secret123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['user']['is_platform_admin'])
        self.assertEqual(response.data['user']['roles'], [])

    def test_platform_settings_and_legacy_test_tenant_are_available(self):
        tenant = Tenant.objects.get(slug='kourouma-auto-parts')
        platform_settings = PlatformSettings.objects.get(pk=1)

        self.assertEqual(tenant.name, 'Kourouma Auto Parts')
        self.assertEqual(tenant.status, 'active')
        self.assertEqual(tenant.max_users, 10)
        self.assertIsNone(platform_settings.max_tenants)
        self.assertIsNone(platform_settings.max_active_users)

    def test_platform_migration_does_not_seed_a_tenant_without_a_legacy_company(self):
        Tenant.objects.all().delete()
        Company.objects.all().delete()
        migration = import_module(
            'core.migrations.0006_platformsettings_tenant_company_tenant',
        )

        migration.initialize_platform_settings(
            apps,
            SimpleNamespace(connection=connection),
        )

        self.assertFalse(Tenant.objects.exists())
        self.assertTrue(PlatformSettings.objects.filter(pk=1).exists())

    def test_platform_migration_preserves_existing_company_tenant_assignment(self):
        Tenant.objects.all().delete()
        Company.objects.all().delete()
        company = Company.objects.create(pk=1, name='Entreprise historique')
        migration = import_module(
            'core.migrations.0006_platformsettings_tenant_company_tenant',
        )

        migration.initialize_platform_settings(
            apps,
            SimpleNamespace(connection=connection),
        )

        tenant = Tenant.objects.get(slug='kourouma-auto-parts')
        company.refresh_from_db()
        self.assertEqual(company.tenant_id, tenant.pk)
        self.assertEqual(tenant.name, 'Entreprise historique')

    def test_tenant_trial_uses_three_calendar_months_from_activation(self):
        tenant = Tenant.objects.create(
            slug='trial-calendar-test',
            name='Entreprise de test',
        )
        activated_at = timezone.make_aware(datetime(2026, 1, 31, 10, 30))

        tenant.activate_trial(activated_at=activated_at)

        self.assertEqual(tenant.status, 'active')
        self.assertEqual(tenant.trial_activated_at, activated_at)
        self.assertEqual(
            tenant.trial_ends_at,
            timezone.make_aware(datetime(2026, 4, 30, 10, 30)),
        )
        self.assertEqual(tenant.status_at(now=activated_at), 'active')
        self.assertEqual(tenant.status_at(now=tenant.trial_ends_at), 'expired')
        with self.assertRaises(ValidationError):
            tenant.activate_trial(activated_at=activated_at)

    def test_tenant_trial_uses_configured_calendar_month_duration(self):
        tenant = Tenant.objects.create(
            slug='trial-duration-test',
            name='Entreprise de test',
            trial_duration_months=1,
        )
        activated_at = timezone.make_aware(datetime(2026, 1, 31, 10, 30))

        tenant.activate_trial(activated_at=activated_at)

        self.assertEqual(
            tenant.trial_ends_at,
            timezone.make_aware(datetime(2026, 2, 28, 10, 30)),
        )

    def test_list_and_create_app_settings(self):
        response = self.client.post(
            '/api/core/settings/',
            {'key': 'company_name', 'value': 'NEXORA', 'description': 'Nom de la société'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AppSetting.objects.count(), 1)
        self.assertTrue(AuditLog.objects.filter(model_name='AppSetting', action='create').exists())

        list_response = self.client.get('/api/core/settings/')
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(
            any(item['key'] == 'company_name' for item in list_response.data['results'])
        )

    def test_company_endpoint_reads_and_updates_company_profile(self):
        tenant = Tenant.objects.get(slug='kourouma-auto-parts')
        response = self.client.get('/api/v1/company/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], tenant.name)

        update = self.client.patch(
            '/api/v1/company/',
            {'name': 'NEXORA Guinée', 'currency': 'GNF'},
            format='json',
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data['name'], 'NEXORA Guinée')
        self.assertTrue(AuditLog.objects.filter(model_name='Company', action='update').exists())

    def test_company_endpoint_is_scoped_to_tenant_and_blocks_platform_admin(self):
        first_tenant = Tenant.objects.create(
            slug='company-profile-first',
            name='Entreprise Première',
        )
        second_tenant = Tenant.objects.create(
            slug='company-profile-second',
            name='Entreprise Seconde',
        )
        first_company = Company.objects.create(
            tenant=first_tenant,
            name='Profil Première',
        )
        second_company = Company.objects.create(
            tenant=second_tenant,
            name='Profil Seconde',
        )
        self.user.tenant = first_tenant
        self.user.save(update_fields=['tenant'])

        response = self.client.get('/api/v1/company/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], first_company.id)
        self.assertEqual(response.data['name'], 'Profil Première')

        update = self.client.patch(
            '/api/v1/company/',
            {'name': 'Profil Première modifié'},
            format='json',
        )

        self.assertEqual(update.status_code, 200)
        first_company.refresh_from_db()
        second_company.refresh_from_db()
        self.assertEqual(first_company.name, 'Profil Première modifié')
        self.assertEqual(second_company.name, 'Profil Seconde')

        platform_admin = User.objects.create_user(
            username='company_profile_platform_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=platform_admin)
        platform_response = self.client.get('/api/v1/company/')
        self.assertEqual(platform_response.status_code, 403)

    def test_list_audit_logs(self):
        AuditLog.objects.create(
            user=self.user,
            action='login',
            model_name='User',
            record_id=self.user.id,
            details='Connexion de l’administrateur',
        )

        response = self.client.get('/api/core/audit/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['action'] == 'login' for item in response.data['results']))

    def test_audit_logs_are_scoped_to_the_requesting_users_tenant(self):
        tenant_a = Tenant.objects.create(
            slug='audit-isolation-tenant-a',
            name='Entreprise journal A',
        )
        tenant_b = Tenant.objects.create(
            slug='audit-isolation-tenant-b',
            name='Entreprise journal B',
        )
        self.user.tenant = tenant_a
        self.user.save(update_fields=['tenant'])
        user_b = User.objects.create_user(
            username='audit_isolation_user_b',
            password='secret123',
            role='admin',
            tenant=tenant_b,
        )
        own_entry = AuditLog.objects.create(
            user=self.user,
            action='login',
            model_name='User',
            record_id=self.user.id,
            details='Action propre à l’entreprise A',
        )
        foreign_entry = AuditLog.objects.create(
            user=user_b,
            action='login',
            model_name='User',
            record_id=user_b.id,
            details='Action privée de l’entreprise B',
        )

        response = self.client.get('/api/core/audit/')

        self.assertEqual(response.status_code, 200)
        returned_ids = {entry['id'] for entry in response.data['results']}
        self.assertIn(own_entry.id, returned_ids)
        self.assertNotIn(foreign_entry.id, returned_ids)
        self.assertNotIn('Action privée de l’entreprise B', str(response.data))

    def test_dashboard_summary_exposes_business_kpis(self):
        customer = Customer.objects.create(full_name='Aminata Diallo', phone='+224600000001')
        product = Product.objects.create(
            sku='SKU-001',
            name='Produit dashboard',
            brand='NEXORA',
            selling_price=Decimal('5000.00'),
            quantity=4,
            alert_threshold=5,
        )
        sale = Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='cash',
            total_amount=Decimal('150000.00'),
            amount_paid=Decimal('100000.00'),
        )
        Payment.objects.create(
            customer=customer,
            sale=sale,
            amount=Decimal('100000.00'),
            payment_method='cash',
            reference='PAY-DASH-001',
        )

        response = self.client.get('/api/core/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_products'], 1)
        self.assertEqual(response.data['total_customers'], 1)
        self.assertEqual(response.data['total_sales'], 150000.0)
        self.assertEqual(response.data['total_received'], 100000.0)
        self.assertEqual(response.data['outstanding_balance'], 50000.0)
        self.assertEqual(response.data['low_stock_products'], 1)
        self.assertEqual(response.data['total_stock_items'], product.quantity)

    def test_dashboard_overview_uses_business_timezone_and_net_daily_sales(self):
        customer = Customer.objects.create(full_name='Dashboard Client', phone='+224600000099')
        first_product = Product.objects.create(
            sku='DASH-DAILY-1',
            name='Pièce tableau 1',
            quantity=4,
            alert_threshold=1,
        )
        second_product = Product.objects.create(
            sku='DASH-DAILY-2',
            name='Pièce tableau 2',
            quantity=1,
            alert_threshold=2,
        )
        location = InventoryLocation.objects.create(
            name='Boutique dashboard',
            code='DASH-STORE',
            location_type='shop',
        )
        CustomerOrder.objects.create(
            customer=customer,
            location=location,
            created_by=self.user,
            status='quote',
        )
        CustomerOrder.objects.create(
            customer=customer,
            location=location,
            created_by=self.user,
            status='confirmed',
        )
        StockItem.objects.create(product=first_product, location=location, quantity=4)
        StockItem.objects.create(product=second_product, location=location, quantity=1)
        supplier = Supplier.objects.create(name='Fournisseur dashboard')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            reference='DASH-PO-001',
            status='approved',
        )
        PurchaseReceipt.objects.create(
            purchase_order=purchase_order,
            location=location,
            reference='DASH-RECEIPT-PENDING',
            status='submitted',
        )
        PurchaseReceipt.objects.create(
            purchase_order=purchase_order,
            location=location,
            reference='DASH-RECEIPT-DRAFT',
            status='draft',
        )
        InventoryCount.objects.create(
            number='DASH-COUNT-001',
            location=location,
            status='submitted',
        )
        paid_sale = Sale.objects.create(
            customer=customer,
            seller=self.user,
            status='paid',
            total_amount=Decimal('100000.00'),
        )
        SaleItem.objects.create(
            sale=paid_sale,
            product=first_product,
            quantity=1,
            unit_price=Decimal('100000.00'),
        )
        partial_sale = Sale.objects.create(
            customer=customer,
            seller=self.user,
            status='partial',
            total_amount=Decimal('50000.00'),
        )
        SaleItem.objects.create(
            sale=partial_sale,
            product=second_product,
            quantity=1,
            unit_price=Decimal('50000.00'),
        )
        old_sale = Sale.objects.create(
            customer=customer,
            seller=self.user,
            status='paid',
            total_amount=Decimal('900000.00'),
        )
        Sale.objects.filter(pk=old_sale.pk).update(
            sale_date=timezone.now() - timedelta(days=1),
        )
        Sale.objects.create(
            customer=customer,
            seller=self.user,
            status='cancelled',
            total_amount=Decimal('800000.00'),
        )
        sale_return = SaleReturn.objects.create(
            sale=paid_sale,
            created_by=self.user,
            reason='Retour partiel',
        )
        return_item = SaleReturnItem.objects.create(
            sale_return=sale_return,
            sale_item=paid_sale.items.get(),
            quantity=1,
            gross_revenue_total=Decimal('20000.00'),
            revenue_total=Decimal('20000.00'),
            cost_total=Decimal('10000.00'),
        )
        SaleReturnQuarantine.objects.create(
            return_item=return_item,
            location=location,
            quantity=1,
            quantity_remaining=1,
            reason='Vérification qualité nécessaire',
        )
        Payment.objects.create(
            customer=customer,
            sale=paid_sale,
            amount=Decimal('60000.00'),
            reference='DASH-TODAY-PAID',
        )
        old_payment = Payment.objects.create(
            customer=customer,
            sale=old_sale,
            amount=Decimal('40000.00'),
            reference='DASH-YESTERDAY',
        )
        Payment.objects.filter(pk=old_payment.pk).update(
            payment_date=timezone.now() - timedelta(days=1),
        )

        response = self.client.get('/api/v1/dashboard/overview/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['date'], timezone.localdate().isoformat())
        self.assertEqual(response.data['timezone'], 'Africa/Conakry')
        self.assertEqual(response.data['sales_amount'], 130000.0)
        self.assertEqual(response.data['sales_count'], 2)
        self.assertEqual(response.data['returned_amount'], 20000.0)
        self.assertEqual(response.data['collected_amount'], 60000.0)
        self.assertEqual(response.data['sold_references'], 2)
        self.assertEqual(len(response.data['sales_trend']), 7)
        trend_by_date = {entry['date']: entry for entry in response.data['sales_trend']}
        self.assertEqual(
            trend_by_date[timezone.localdate().isoformat()]['sales'],
            130000.0,
        )
        self.assertEqual(
            trend_by_date[(timezone.localdate() - timedelta(days=1)).isoformat()]['sales'],
            900000.0,
        )
        self.assertEqual(len(response.data['recent_sales']), 2)
        recent_sale_statuses = {
            sale['status'] for sale in response.data['recent_sales']
        }
        self.assertEqual(recent_sale_statuses, {'paid', 'partial'})
        self.assertEqual(response.data['stock_alert_count'], 1)
        self.assertEqual(response.data['out_of_stock_count'], 0)
        self.assertEqual(response.data['pending_customer_quotes'], 1)
        self.assertEqual(response.data['confirmed_customer_orders'], 1)
        self.assertEqual(response.data['low_stock'][0]['id'], second_product.id)
        self.assertEqual(response.data['pending_receipts'], 1)
        self.assertEqual(response.data['draft_receipts'], 1)
        self.assertEqual(response.data['pending_inventory_counts'], 1)
        self.assertEqual(response.data['pending_return_quarantines'], 1)
        self.assertEqual(response.data['pending_return_items'][0]['sale_id'], paid_sale.id)
        self.assertEqual(response.data['pending_return_items'][0]['product_name'], first_product.name)

    def test_dashboard_overview_scopes_sales_and_hides_financials_from_stock_role(self):
        customer = Customer.objects.create(full_name='Dashboard Scope', phone='+224600000098')
        own_sale = Sale.objects.create(
            customer=customer,
            seller=self.user,
            status='paid',
            total_amount=Decimal('1000.00'),
        )
        other_seller = User.objects.create_user(
            username='dashboard_other_seller',
            role='sales',
        )
        Sale.objects.create(
            customer=customer,
            seller=other_seller,
            status='paid',
            total_amount=Decimal('9000.00'),
        )
        Payment.objects.create(
            customer=customer,
            sale=own_sale,
            amount=Decimal('1000.00'),
            reference='DASH-OWN-PAYMENT',
        )
        sales_user = User.objects.create_user(
            username='dashboard_sales_user',
            role='sales',
        )
        Sale.objects.filter(pk=own_sale.pk).update(seller=sales_user)
        self.client.force_authenticate(user=sales_user)

        sales_response = self.client.get('/api/v1/dashboard/overview/')

        self.assertEqual(sales_response.status_code, 200, sales_response.data)
        self.assertEqual(sales_response.data['sales_amount'], 1000.0)
        self.assertEqual(sales_response.data['sales_count'], 1)
        self.assertEqual(sales_response.data['collected_amount'], 1000.0)

        stock_user = User.objects.create_user(
            username='dashboard_stock_user',
            role='stock',
        )
        self.client.force_authenticate(user=stock_user)
        stock_response = self.client.get('/api/v1/dashboard/overview/')

        self.assertEqual(stock_response.status_code, 200, stock_response.data)
        self.assertIsNone(stock_response.data['sales_amount'])
        self.assertIsNone(stock_response.data['collected_amount'])
        self.assertIsNone(stock_response.data['sold_references'])
        self.assertIsNone(stock_response.data['sales_trend'])
        self.assertIsNone(stock_response.data['pending_customer_quotes'])
        self.assertIsNone(stock_response.data['confirmed_customer_orders'])

    def test_dashboard_overview_scopes_seller_stock_alerts_to_authorized_shop(self):
        seller = User.objects.create_user(
            username='dashboard_scoped_stock_seller',
            role='sales',
        )
        other_user = User.objects.create_user(
            username='dashboard_other_location_user',
            role='stock',
        )
        shop = InventoryLocation.objects.create(
            name='Boutique autorisée tableau',
            code='DASH-AUTH-SHOP',
            location_type='shop',
        )
        shop.authorized_users.add(seller)
        warehouse = InventoryLocation.objects.create(
            name='Entrepôt non autorisé tableau',
            code='DASH-OTHER-WAREHOUSE',
            location_type='warehouse',
        )
        warehouse.authorized_users.add(other_user)
        product = Product.objects.create(
            sku='DASH-SCOPED-STOCK',
            name='Stock limité par boutique',
            quantity=14,
            alert_threshold=5,
        )
        StockItem.objects.create(product=product, location=shop, quantity=4)
        StockItem.objects.create(product=product, location=warehouse, quantity=10)
        self.client.force_authenticate(user=seller)

        response = self.client.get('/api/v1/dashboard/overview/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['stock_alert_count'], 1)
        self.assertEqual(response.data['low_stock'][0]['id'], product.id)
        self.assertEqual(response.data['low_stock'][0]['stock'], 4)

    def test_advanced_reporting_api_is_available(self):
        customer = Customer.objects.create(full_name='Aissatou Barry', phone='+224600000002')
        Product.objects.create(
            sku='SKU-REPORT-1',
            name='Produit report',
            brand='NEXORA',
            selling_price=Decimal('20000.00'),
            quantity=10,
            alert_threshold=2,
        )
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('20000.00'),
            amount_paid=Decimal('20000.00'),
        )
        Payment.objects.create(
            customer=customer,
            sale=sale,
            amount=Decimal('20000.00'),
            payment_method='cash',
            reference='PAY-REPORT-001',
        )

        response = self.client.get('/api/core/reports/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('summary', response.data)
        self.assertIn('top_products', response.data)
        self.assertIn('sales_by_period', response.data)
        self.assertIn('customer_breakdown', response.data)
        self.assertIn('inventory_status', response.data)
        self.assertIn('inventory_value', response.data['inventory_status'])
        self.assertIn('average_margin_percent', response.data['inventory_status'])
        self.assertIn('financial_data_quality', response.data['inventory_status'])

    def test_cashflow_summary_exposes_financial_snapshot(self):
        customer = Customer.objects.create(full_name='Saliou Camara', phone='+224600000010')
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('300000.00'),
            amount_paid=Decimal('300000.00'),
        )
        Payment.objects.create(
            customer=customer,
            sale=sale,
            amount=Decimal('300000.00'),
            payment_method='cash',
            reference='PAY-CASHFLOW-001',
        )

        response = self.client.get('/api/core/cashflow/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['cash_in'], 300000.0)
        self.assertEqual(response.data['cash_out'], 0.0)
        self.assertEqual(response.data['net_cash'], 300000.0)

    def test_versioned_cash_endpoints_expose_summary_and_transactions(self):
        customer = Customer.objects.create(full_name='Client caisse')
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('300000.00'),
            amount_paid=Decimal('300000.00'),
        )
        Payment.objects.create(
            customer=customer,
            sale=sale,
            amount=Decimal('300000.00'),
            payment_method='cash',
            reference='PAY-CASH-001',
        )

        cash_response = self.client.get('/api/v1/cash/')
        cashflow_response = self.client.get('/api/v1/cashflow/')
        transactions_response = self.client.get('/api/v1/cash/transactions/')
        financial_response = self.client.get('/api/v1/financial-summary/')

        self.assertEqual(cash_response.status_code, 200)
        self.assertEqual(cash_response.data['cash_in'], 300000.0)
        self.assertEqual(cashflow_response.status_code, 200)
        self.assertEqual(cashflow_response.data['cash_in'], 300000.0)
        self.assertEqual(transactions_response.status_code, 200)
        self.assertTrue(any(item['reference'] == 'PAY-CASH-001' for item in transactions_response.data))
        self.assertEqual(financial_response.status_code, 200)
        self.assertEqual(financial_response.data['outstanding_balance'], 0.0)

    def test_versioned_core_endpoints_are_available_in_v1_root(self):
        response = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_products', response.data)

        audit_response = self.client.get('/api/v1/audit/')
        self.assertEqual(audit_response.status_code, 200)

        settings_response = self.client.get('/api/v1/settings/')
        self.assertEqual(settings_response.status_code, 200)

    def test_advanced_reporting_filters_by_date_and_customer(self):
        customer_recent = Customer.objects.create(full_name='Recent Client', phone='+224600000011')
        customer_old = Customer.objects.create(full_name='Old Client', phone='+224600000012')
        product = Product.objects.create(
            sku='SKU-FILT-001',
            name='Produit filtré',
            brand='NEXORA',
            selling_price=Decimal('60000.00'),
            quantity=10,
            alert_threshold=2,
        )

        recent_sale = Sale.objects.create(
            customer=customer_recent,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('60000.00'),
            amount_paid=Decimal('60000.00'),
        )
        recent_sale.items.create(product=product, quantity=1, unit_price=Decimal('60000.00'))
        recent_sale.sale_date = timezone.now()
        recent_sale.save(update_fields=['sale_date'])

        old_sale = Sale.objects.create(
            customer=customer_old,
            status='paid',
            payment_method='bank_transfer',
            total_amount=Decimal('100000.00'),
            amount_paid=Decimal('100000.00'),
        )
        old_sale.items.create(product=product, quantity=1, unit_price=Decimal('100000.00'))
        old_sale.sale_date = timezone.now() - timedelta(days=30)
        old_sale.save(update_fields=['sale_date'])

        response = self.client.get(
            '/api/core/reports/',
            {'start_date': (timezone.now() - timedelta(days=1)).date().isoformat(), 'end_date': timezone.now().date().isoformat(), 'customer': customer_recent.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['total_sales'], 60000.0)
        self.assertEqual(response.data['summary']['total_customers'], 1)

    def test_report_routes_accept_product_and_category_filters(self):
        category = Category.objects.create(name='Catégorie rapport')
        customer = Customer.objects.create(full_name='Client rapport produit')
        product = Product.objects.create(
            sku='REPORT-PRODUCT-001',
            name='Produit rapport filtre',
            category=category,
            selling_price=Decimal('12000.00'),
            quantity=2,
        )
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('12000.00'),
            amount_paid=Decimal('12000.00'),
        )
        sale.items.create(product=product, quantity=1, unit_price=Decimal('12000.00'))

        response = self.client.get(
            '/api/v1/reports/sales/',
            {'product': product.id, 'category': category.id, 'date_from': '2026-01-01'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['total_sales'], 12000.0)

    def test_report_routes_accept_seller_filter(self):
        seller = User.objects.create_user(
            username='seller_report',
            password='secret123',
            pin_code='4321',
            role='sales',
        )
        customer = Customer.objects.create(full_name='Client vendeur')
        product = Product.objects.create(
            sku='REPORT-SELLER-001',
            name='Produit vendeur',
            selling_price=Decimal('30000.00'),
            quantity=5,
        )

        sale = Sale.objects.create(
            customer=customer,
            seller=seller,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('30000.00'),
            amount_paid=Decimal('30000.00'),
        )
        sale.items.create(product=product, quantity=1, unit_price=Decimal('30000.00'))

        response = self.client.get('/api/v1/reports/sales/', {'seller': seller.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['total_sales'], 30000.0)

    def test_sales_report_filters_by_business_dimensions_and_groups_locations(self):
        category = Category.objects.create(name='Catégorie BI')
        location = InventoryLocation.objects.create(
            name='Boutique BI',
            code='REPORT-BI-SHOP',
            location_type='shop',
        )
        seller = User.objects.create_user(
            username='seller_dimensions',
            first_name='Vendeur',
            last_name='BI',
            password='secret123',
            role='sales',
        )
        customer = Customer.objects.create(
            full_name='Client Dimensions BI',
            phone='+224600001234',
        )
        product = Product.objects.create(
            sku='REPORT-DIMENSIONS-001',
            name='Filtre dimensions',
            category=category,
            selling_price=Decimal('42000.00'),
            quantity=5,
        )
        sale = Sale.objects.create(
            customer=customer,
            seller=seller,
            location=location,
            status='paid',
            payment_method='mobile_money',
            total_amount=Decimal('84000.00'),
            amount_paid=Decimal('84000.00'),
        )
        sale.items.create(
            product=product,
            quantity=2,
            unit_price=Decimal('42000.00'),
        )

        response = self.client.get(
            '/api/v1/reports/sales/',
            {
                'product_search': 'dimensions',
                'category_search': 'BI',
                'customer_search': 'Client Dimensions',
                'seller_search': 'seller_dimensions',
                'location_search': 'Boutique BI',
                'payment_method': 'mobile_money',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['total_sales'], 84000.0)
        self.assertEqual(response.data['summary']['total_quantity_sold'], 2)
        self.assertEqual(len(response.data['sales_by_location']), 1)
        self.assertEqual(
            response.data['sales_by_location'][0]['location_name'],
            'Boutique BI',
        )
        self.assertEqual(
            response.data['sales_by_location'][0]['total_sales'],
            84000.0,
        )

        invalid_payment = self.client.get(
            '/api/v1/reports/sales/',
            {'payment_method': 'cryptocurrency'},
        )
        self.assertEqual(invalid_payment.status_code, 400)

    def test_sales_report_limits_sales_role_to_own_sales_and_hides_cost_data(self):
        seller = User.objects.create_user(
            username='own_sales_report',
            password='secret123',
            pin_code='4321',
            role='sales',
        )
        other_seller = User.objects.create_user(
            username='other_sales_report',
            password='secret123',
            pin_code='5678',
            role='sales',
        )
        customer = Customer.objects.create(full_name='Client rapport vendeur')
        product = Product.objects.create(
            sku='REPORT-OWN-001',
            name='Produit rapport vendeur',
            cost_price=Decimal('12000.00'),
            selling_price=Decimal('30000.00'),
            quantity=9,
            alert_threshold=2,
        )
        own_shop = InventoryLocation.objects.create(
            name='Boutique rapport vendeur',
            code='REPORT-OWN-SHOP',
            location_type='shop',
        )
        own_shop.authorized_users.add(seller)
        other_shop = InventoryLocation.objects.create(
            name='Boutique autre vendeur',
            code='REPORT-OTHER-SHOP',
            location_type='shop',
        )
        other_shop.authorized_users.add(other_seller)
        StockItem.objects.create(product=product, location=own_shop, quantity=3)
        StockItem.objects.create(product=product, location=other_shop, quantity=11)
        other_product = Product.objects.create(
            sku='REPORT-OTHER-STOCK-001',
            name='Produit stock autre boutique',
            quantity=15,
            alert_threshold=1,
        )
        StockItem.objects.create(product=other_product, location=other_shop, quantity=15)
        own_sale = Sale.objects.create(
            customer=customer,
            seller=seller,
            status='paid',
            total_amount=Decimal('30000.00'),
            amount_paid=Decimal('10000.00'),
        )
        own_sale.items.create(product=product, quantity=1, unit_price=Decimal('30000.00'))
        foreign_sale = Sale.objects.create(
            customer=customer,
            seller=other_seller,
            status='paid',
            total_amount=Decimal('70000.00'),
            amount_paid=Decimal('70000.00'),
        )
        foreign_sale.items.create(product=product, quantity=1, unit_price=Decimal('70000.00'))

        self.client.force_authenticate(user=seller)
        response = self.client.get(
            '/api/v1/reports/sales/',
            {'seller': other_seller.id, 'period': 'day'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['total_sales'], 30000.0)
        self.assertEqual(response.data['summary']['outstanding_balance'], 20000.0)
        self.assertEqual(response.data['summary']['sales_count'], 1)
        self.assertEqual(response.data['summary']['average_basket'], 30000.0)
        self.assertNotIn('profitability', response.data['summary'])
        self.assertNotIn('inventory_value', response.data['inventory_status'])
        self.assertNotIn('average_margin_percent', response.data['inventory_status'])
        self.assertNotIn('financial_data_quality', response.data['inventory_status'])
        self.assertEqual(response.data['inventory_status']['total_stock_items'], 3)
        self.assertEqual(response.data['inventory_status']['low_stock_products'], 1)
        self.assertEqual(response.data['inventory_status']['healthy_products'], 1)
        self.assertEqual(response.data['top_products'][0]['quantity_sold'], 1)
        self.assertEqual(float(response.data['top_products'][0]['revenue']), 30000.0)
        self.assertEqual(response.data['trend_period'], 'day')
        self.assertEqual(len(response.data['sales_trend']), 1)
        self.assertEqual(response.data['sales_trend'][0]['sales'], 30000.0)
        self.assertEqual(len(response.data['sales_by_seller']), 1)
        self.assertEqual(response.data['sales_by_seller'][0]['sale_count'], 1)
        self.assertEqual(response.data['sales_by_seller'][0]['total_sales'], 30000.0)
        self.assertEqual(response.data['sales_by_payment_method'][0]['total_sales'], 30000.0)

    def test_sales_report_marks_historical_profitability_unavailable(self):
        response = self.client.get('/api/core/reports/sales/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['summary']['profitability']['available'])
        self.assertIn('coût FIFO', response.data['summary']['profitability']['reason'])

    def test_sales_report_calculates_profitability_from_sale_cost_snapshots(self):
        customer = Customer.objects.create(full_name='Client marge historique')
        product = Product.objects.create(
            sku='REPORT-FIFO-001',
            name='Produit coût FIFO',
            selling_price=Decimal('150.00'),
        )
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
        )
        sale.items.create(
            product=product,
            quantity=2,
            unit_price=Decimal('150.00'),
            cost_total=Decimal('180.00'),
        )

        response = self.client.get('/api/core/reports/sales/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['summary']['profitability']['available'])
        self.assertEqual(response.data['summary']['total_cost'], 180.0)
        self.assertEqual(response.data['summary']['gross_margin'], 120.0)
        self.assertEqual(response.data['summary']['gross_margin_percent'], 40.0)

    def test_sales_report_counts_only_payment_allocations_in_report_scope(self):
        first_seller = User.objects.create_user(
            username='report_payment_first',
            password='secret123',
            role='sales',
        )
        second_seller = User.objects.create_user(
            username='report_payment_second',
            password='secret123',
            role='sales',
        )
        customer = Customer.objects.create(
            full_name='Client paiements répartis',
            phone='+224600009876',
        )
        first_sale = Sale.objects.create(
            customer=customer,
            seller=first_seller,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('100.00'),
            amount_paid=Decimal('0.00'),
        )
        second_sale = Sale.objects.create(
            customer=customer,
            seller=second_seller,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('200.00'),
            amount_paid=Decimal('0.00'),
        )
        product = Product.objects.create(
            sku='REPORT-PAYMENT-001',
            name='Produit paiement rapport',
        )
        first_sale.items.create(
            product=product,
            quantity=1,
            unit_price=Decimal('100.00'),
            cost_total=Decimal('50.00'),
        )
        second_sale.items.create(
            product=product,
            quantity=1,
            unit_price=Decimal('200.00'),
            cost_total=Decimal('80.00'),
        )
        payment = self.client.post(
            '/api/payments/',
            {
                'customer': customer.id,
                'amount': '150.00',
                'payment_method': 'cash',
            },
            format='json',
        )

        self.assertEqual(payment.status_code, 201, payment.data)
        self.assertEqual(
            list(
                PaymentAllocation.objects.filter(payment_id=payment.data['id'])
                .order_by('sale_id')
                .values_list('amount', flat=True)
            ),
            [Decimal('100.00'), Decimal('50.00')],
        )
        manager_report = self.client.get('/api/v1/reports/sales/')
        self.assertEqual(manager_report.data['summary']['total_received'], 150.0)

        self.client.force_authenticate(user=first_seller)
        first_seller_report = self.client.get('/api/v1/reports/sales/')
        self.assertEqual(first_seller_report.data['summary']['total_received'], 100.0)
        self.assertNotIn('gross_margin', first_seller_report.data['summary'])

    def test_inventory_report_filters_products_and_categories(self):
        category = Category.objects.create(name='Accessoires BI')
        location = InventoryLocation.objects.create(
            name='Dépôt filtrage BI',
            code='INVENTORY-FILTER-BI',
        )
        matching_product = Product.objects.create(
            sku='INVENTORY-FILTER-001',
            name='Batterie filtrable',
            category=category,
            quantity=4,
        )
        other_product = Product.objects.create(
            sku='INVENTORY-FILTER-002',
            name='Autre accessoire',
            quantity=8,
        )
        StockItem.objects.create(product=matching_product, location=location, quantity=4)
        StockItem.objects.create(product=other_product, location=location, quantity=8)

        response = self.client.get(
            '/api/v1/reports/inventory/',
            {
                'product_search': 'Batterie',
                'category_search': 'Accessoires',
                'location': location.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['total_stock_units'], 4)
        self.assertEqual(response.data['summary']['tracked_products'], 1)
        self.assertEqual(
            [item['product_id'] for item in response.data['inventory']],
            [matching_product.id],
        )
        self.assertEqual(
            response.data['rotation']['products'][0]['product_id'],
            matching_product.id,
        )

    def test_sales_report_rejects_unknown_trend_period(self):
        response = self.client.get('/api/core/reports/sales/', {'period': 'decade'})

        self.assertEqual(response.status_code, 400)

    def test_purchase_report_uses_received_receipts_and_excludes_drafts(self):
        supplier = Supplier.objects.create(name='Fournisseur rapport BI')
        location = InventoryLocation.objects.create(
            name='Entrepôt achat rapport',
            code='PURCHASE-REPORT-LOC',
        )
        product = Product.objects.create(
            sku='REPORT-PURCHASE-001',
            name='Produit achat BI',
        )
        order = PurchaseOrder.objects.create(
            supplier=supplier,
            reference='REPORT-PO-001',
            status='approved',
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            product=product,
            quantity=4,
            unit_cost=Decimal('25.00'),
        )
        received_receipt = PurchaseReceipt.objects.create(
            purchase_order=order,
            location=location,
            reference='REPORT-RECEIPT-001',
            status='received',
            transport_cost=Decimal('10.00'),
        )
        PurchaseReceiptItem.objects.create(
            purchase_receipt=received_receipt,
            product=product,
            quantity_received=2,
            unit_cost=Decimal('25.00'),
        )
        partial_receipt = PurchaseReceipt.objects.create(
            purchase_order=order,
            location=location,
            reference='REPORT-RECEIPT-002',
            status='received',
        )
        PurchaseReceiptItem.objects.create(
            purchase_receipt=partial_receipt,
            product=product,
            quantity_received=1,
            unit_cost=Decimal('20.00'),
        )
        draft_receipt = PurchaseReceipt.objects.create(
            purchase_order=order,
            location=location,
            reference='REPORT-RECEIPT-DRAFT',
            status='draft',
        )
        PurchaseReceiptItem.objects.create(
            purchase_receipt=draft_receipt,
            product=product,
            quantity_received=9,
            unit_cost=Decimal('25.00'),
        )

        response = self.client.get(
            '/api/v1/reports/purchases/',
            {'location': location.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['ordered_amount'], 100.0)
        self.assertEqual(response.data['suppliers'][0]['ordered_quantity'], 4)
        self.assertEqual(response.data['summary']['received_quantity'], 3)
        self.assertEqual(response.data['summary']['receipt_count'], 2)
        self.assertEqual(response.data['summary']['received_amount'], 80.0)
        self.assertEqual(
            response.data['data_quality']['ordered_amount_scope'],
            'whole_orders_with_matching_validated_receipts',
        )
        self.assertEqual(
            response.data['data_quality']['received_values_source'],
            'validated_received_receipts_only',
        )
        self.assertTrue(response.data['summary']['ordered_amount_is_not_stock'])
        self.assertFalse(response.data['data_quality']['currency_comparison_available'])
        filtered = self.client.get(
            '/api/v1/reports/purchases/',
            {
                'supplier_search': 'Fournisseur rapport',
                'location_search': 'Entrepôt achat',
            },
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data['summary']['receipt_count'], 2)
        no_match = self.client.get(
            '/api/v1/reports/purchases/',
            {'location_search': 'Emplacement absent'},
        )
        self.assertEqual(no_match.data['summary']['receipt_count'], 0)

    def test_report_routes_enforce_domain_permissions(self):
        sales_user = User.objects.create_user(
            username='report_sales_scope',
            password='secret123',
            pin_code='4321',
            role='sales',
        )
        stock_user = User.objects.create_user(
            username='report_stock_scope',
            password='secret123',
            pin_code='5678',
            role='stock',
        )
        location = InventoryLocation.objects.create(
            name='Emplacement rapport BI',
            code='REPORT-BI-LOC',
        )
        location.authorized_users.add(stock_user)
        stock_product = Product.objects.create(
            sku='REPORT-STOCK-001',
            name='Produit stock BI',
            cost_price=Decimal('500.00'),
            quantity=12,
            alert_threshold=3,
        )
        StockItem.objects.create(
            product=stock_product,
            location=location,
            quantity=5,
        )
        client = APIClient()

        client.force_authenticate(user=sales_user)
        self.assertEqual(client.get('/api/v1/reports/purchases/').status_code, 403)
        self.assertEqual(client.get('/api/core/reports/').status_code, 403)

        client.force_authenticate(user=stock_user)
        inventory_response = client.get('/api/v1/reports/inventory/')
        self.assertEqual(inventory_response.status_code, 200)
        self.assertEqual(inventory_response.data['summary']['total_stock_units'], 5)
        self.assertNotIn('inventory_value', inventory_response.data)
        self.assertNotIn('cost_price', inventory_response.data['inventory'][0])
        unauthorized_location = InventoryLocation.objects.create(
            name='Emplacement non autorisé',
            code='REPORT-BI-OTHER',
        )
        restricted_response = client.get(
            '/api/v1/reports/inventory/',
            {'location': unauthorized_location.id},
        )
        self.assertEqual(restricted_response.status_code, 200)
        self.assertEqual(restricted_response.data['summary']['total_stock_units'], 0)
        self.assertEqual(client.get('/api/v1/reports/sales/').status_code, 403)
        self.assertEqual(client.get('/api/v1/reports/finance/').status_code, 403)

    def test_finance_report_keeps_current_credit_balance_separate_from_period_cashflow(self):
        customer = Customer.objects.create(full_name='Client encours actuel')
        open_credit = Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='credit',
            total_amount=Decimal('200000.00'),
            amount_paid=Decimal('125000.00'),
        )
        open_credit.sale_date = timezone.now() - timedelta(days=120)
        open_credit.save(update_fields=['sale_date'])
        Sale.objects.create(
            customer=customer,
            status='draft',
            payment_method='credit',
            total_amount=Decimal('90000.00'),
            amount_paid=Decimal('0.00'),
        )
        Sale.objects.create(
            customer=customer,
            status='partial',
            payment_method='cash',
            total_amount=Decimal('50000.00'),
            amount_paid=Decimal('10000.00'),
        )

        response = self.client.get(
            '/api/v1/reports/finance/',
            {'start_date': '2000-01-01', 'end_date': '2000-01-31'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['cash_in'], 0.0)
        self.assertEqual(response.data['cash_out'], 0.0)
        self.assertEqual(response.data['outstanding_balance'], 75000.0)
        self.assertEqual(
            response.data['outstanding_balance_scope'],
            'current_open_credit_sales',
        )
        self.assertEqual(response.data['as_of'], timezone.localdate().isoformat())

    def test_inventory_report_exposes_location_scoped_rotation_and_movements(self):
        stock_user = User.objects.create_user(
            username='rotation_stock_user',
            password='secret123',
            pin_code='2468',
            role='stock',
        )
        location = InventoryLocation.objects.create(
            name='Entrepôt rotation',
            code='ROTATION-LOC',
        )
        location.authorized_users.add(stock_user)
        product = Product.objects.create(
            sku='ROTATION-PRODUCT',
            name='Produit rotation',
            quantity=15,
            alert_threshold=3,
        )
        StockItem.objects.create(product=product, location=location, quantity=6)
        customer = Customer.objects.create(full_name='Client rotation stock')
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            location=location,
            total_amount=Decimal('12000.00'),
            amount_paid=Decimal('12000.00'),
        )
        sale.items.create(product=product, quantity=30, unit_price=Decimal('400.00'))
        StockMovement.objects.create(
            product=product,
            location=location,
            movement_type='out',
            quantity=30,
            reference='ROTATION-SALE',
        )

        client = APIClient()
        client.force_authenticate(user=stock_user)
        response = client.get(
            '/api/v1/reports/inventory/',
            {'period_days': 30},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rotation']['period_days'], 30)
        self.assertEqual(response.data['rotation']['products'][0]['quantity_sold'], 30)
        self.assertEqual(response.data['rotation']['products'][0]['days_of_stock'], 6.0)
        self.assertEqual(response.data['rotation']['products'][0]['rotation_status'], 'fast')
        self.assertTrue(response.data['rotation']['products'][0]['reorder_signal'])
        self.assertEqual(response.data['movement_summary']['out']['quantity'], 30)
        self.assertTrue(response.data['inventory_scope']['products_without_stock_item_excluded'])

        invalid_period = client.get(
            '/api/v1/reports/inventory/',
            {'period_days': 0},
        )
        self.assertEqual(invalid_period.status_code, 400)
        invalid_date = client.get(
            '/api/v1/reports/inventory/',
            {'start_date': 'not-a-date'},
        )
        self.assertEqual(invalid_date.status_code, 400)

    def test_global_search_returns_cross_module_results(self):
        customer = Customer.objects.create(full_name='Aminata Diop', phone='+224600000020')
        product = Product.objects.create(
            sku='PRD-SEARCH-001',
            name='Produit global',
            brand='NEXORA',
            selling_price=Decimal('25000.00'),
            quantity=7,
            alert_threshold=2,
        )
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('25000.00'),
            amount_paid=Decimal('25000.00'),
        )
        sale.items.create(product=product, quantity=1, unit_price=Decimal('25000.00'))
        Payment.objects.create(
            customer=customer,
            sale=sale,
            amount=Decimal('25000.00'),
            payment_method='cash',
            reference='PAY-SEARCH-001',
        )

        response = self.client.get('/api/core/search/', {'q': 'PRD-SEARCH-001'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('products', response.data)
        self.assertIn('customers', response.data)
        self.assertIn('payments', response.data)
        self.assertTrue(any(item['sku'] == 'PRD-SEARCH-001' for item in response.data['products']))

    def test_global_search_includes_sales_and_cartons(self):
        from inventory.models import Carton, InventoryLocation

        customer = Customer.objects.create(full_name='Client recherche vente')
        product = Product.objects.create(
            sku='SEARCH-CARTON-001',
            name='Produit carton recherche',
            selling_price=Decimal('15000.00'),
            quantity=4,
        )
        sale = Sale.objects.create(
            customer=customer,
            status='paid',
            payment_method='cash',
            total_amount=Decimal('15000.00'),
            amount_paid=Decimal('15000.00'),
            external_reference='SALE-SEARCH-001',
        )
        location = InventoryLocation.objects.create(name='Emplacement recherche', code='SEARCH-LOC')
        carton = Carton.objects.create(
            product=product,
            location=location,
            reference='CARTON-SEARCH-001',
            quantity=2,
            items_per_carton=1,
        )

        response = self.client.get('/api/v1/search/', {'q': 'SEARCH'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['id'] == sale.id for item in response.data['sales']))
        self.assertTrue(any(item['id'] == carton.id for item in response.data['cartons']))

    def test_offline_sale_sync_is_idempotent(self):
        customer = Customer.objects.create(full_name='Client synchronisation')
        product = Product.objects.create(
            sku='SYNC-PRODUCT-001',
            name='Produit synchronisation',
            selling_price=Decimal('9000.00'),
            quantity=3,
        )
        location = InventoryLocation.objects.create(
            name='Boutique synchronisation',
            code='SYNC-SHOP-001',
            location_type='shop',
        )
        StockItem.objects.create(product=product, location=location, quantity=3)
        operation = {
            'local_id': 'LOCAL-SALE-001',
            'operation_type': 'sale',
            'payload': {
                'customer': customer.id,
                'location': location.id,
                'status': 'paid',
                'payment_method': 'cash',
                'items': [{'product': product.id, 'quantity': 1, 'unit_price': '9000.00'}],
            },
        }

        first = self.client.post('/api/v1/sync/', operation, format='json')
        second = self.client.post('/api/v1/sync/', operation, format='json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['results'][0]['status'], 'accepted')
        self.assertEqual(second.data['results'][0]['result']['id'], first.data['results'][0]['result']['id'])
        self.assertEqual(Sale.objects.filter(customer=customer).count(), 1)

    def test_app_settings_require_admin_role(self):
        manager = User.objects.create_user(
            username='stock_app',
            password='secret123',
            pin_code='4321',
            role='stock',
        )
        client = APIClient()
        client.force_authenticate(user=manager)

        response = client.post(
            '/api/core/settings/',
            {'key': 'finance_mode', 'value': 'strict'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)


class PlatformBillingTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_user(
            username='billing_platform_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.tenant = Tenant.objects.create(
            slug='billing-tenant',
            name='Entreprise facturation',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.platform_admin)

    def test_only_platform_admin_can_manage_platform_plans(self):
        tenant_admin = User.objects.create_user(
            username='billing_tenant_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=tenant_admin)

        response = self.client.get('/api/v1/platform/plans/')

        self.assertEqual(response.status_code, 403)

    def test_paid_subscription_payment_confirmation_activates_tenant_and_audits(self):
        module = PlatformModule.objects.create(
            code='billing-dashboard',
            name='Tableau de bord',
        )
        plan = PlatformPlan.objects.create(
            code='billing-standard',
            name='Standard',
            price=Decimal('50000.00'),
            currency='GNF',
            duration_months=3,
            max_users=10,
        )
        plan.modules.add(module)

        assigned = self.client.post(
            '/api/v1/platform/subscriptions/',
            {'tenant_id': self.tenant.pk, 'plan_id': plan.pk},
            format='json',
        )

        self.assertEqual(assigned.status_code, 201, assigned.data)
        subscription_id = assigned.data['id']
        self.assertEqual(assigned.data['status'], 'pending')
        invoice = BillingInvoice.objects.get(subscription_id=subscription_id)
        self.assertEqual(invoice.status, 'open')
        self.assertEqual(invoice.amount, Decimal('50000.00'))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'pending')

        invalid_payment = self.client.post(
            '/api/v1/platform/payments/',
            {
                'subscription_id': subscription_id,
                'amount': '49999.00',
                'method': 'bank_transfer',
                'paid_at': timezone.localdate().isoformat(),
            },
            format='json',
        )
        self.assertEqual(invalid_payment.status_code, 400)

        payment = self.client.post(
            '/api/v1/platform/payments/',
            {
                'subscription_id': subscription_id,
                'amount': '50000.00',
                'method': 'bank_transfer',
                'reference': 'BANK-2026-001',
                'paid_at': timezone.localdate().isoformat(),
            },
            format='json',
        )
        self.assertEqual(payment.status_code, 201, payment.data)
        self.assertEqual(payment.data['status'], 'pending')
        payment_record = PaymentRecord.objects.get(
            platform_payment__subscription_id=subscription_id
        )
        self.assertEqual(payment_record.status, 'pending')
        self.assertEqual(payment_record.invoice_id, invoice.pk)
        self.assertEqual(payment.data['invoiceNumber'], invoice.invoice_number)

        confirmed = self.client.post(
            f"/api/v1/platform/payments/{payment.data['id']}/confirm/",
            {},
            format='json',
        )

        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data['status'], 'confirmed')
        payment_record.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(payment_record.status, 'confirmed')
        self.assertEqual(payment_record.verified_by, self.platform_admin)
        self.assertEqual(invoice.status, 'paid')
        subscription = TenantSubscription.objects.get(pk=subscription_id)
        self.assertEqual(subscription.status, 'active')
        self.assertIsNotNone(subscription.ends_at)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'active')
        self.assertTrue(tenant_module_is_enabled(self.tenant, module.code))
        self.assertTrue(
            PlatformAuditLog.objects.filter(action='subscription_assign').exists()
        )
        self.assertTrue(
            PlatformAuditLog.objects.filter(action='payment_record').exists()
        )
        self.assertTrue(
            PlatformAuditLog.objects.filter(action='payment_confirm').exists()
        )

    def test_paid_plan_change_suspends_active_tenant_until_payment(self):
        module = PlatformModule.objects.create(
            code='billing-reports',
            name='Rapports',
        )
        plan = PlatformPlan.objects.create(
            code='billing-paid',
            name='Payant',
            price=Decimal('100.00'),
            currency='GNF',
            duration_months=1,
            max_users=10,
        )
        plan.modules.add(module)
        self.tenant.status = 'active'
        self.tenant.trial_activated_at = timezone.now()
        self.tenant.trial_ends_at = timezone.now() + timedelta(days=30)
        self.tenant.save()

        response = self.client.post(
            '/api/v1/platform/subscriptions/',
            {'tenant_id': self.tenant.pk, 'plan_id': plan.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'suspended')

    def test_rejected_payment_does_not_activate_a_pending_subscription(self):
        plan = PlatformPlan.objects.create(
            code='billing-rejected',
            name='À rejeter',
            price=Decimal('250.00'),
            currency='GNF',
            duration_months=1,
            max_users=10,
        )
        assigned = self.client.post(
            '/api/v1/platform/subscriptions/',
            {'tenant_id': self.tenant.pk, 'plan_id': plan.pk},
            format='json',
        )
        payment = self.client.post(
            '/api/v1/platform/payments/',
            {
                'subscription_id': assigned.data['id'],
                'amount': '250.00',
                'method': 'cash',
                'paid_at': timezone.localdate().isoformat(),
            },
            format='json',
        )

        rejected = self.client.post(
            f"/api/v1/platform/payments/{payment.data['id']}/reject/",
            {},
            format='json',
        )

        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(rejected.data['status'], 'rejected')
        self.assertEqual(
            TenantSubscription.objects.get(pk=assigned.data['id']).status,
            'pending',
        )
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, 'pending')
        self.assertTrue(
            PlatformAuditLog.objects.filter(action='payment_reject').exists()
        )

    def test_module_override_requires_dependencies_from_active_entitlement(self):
        base = PlatformModule.objects.create(
            code='billing-base',
            name='Base',
        )
        dependent = PlatformModule.objects.create(
            code='billing-advanced',
            name='Avancé',
            dependencies=[base.code],
        )
        plan = PlatformPlan.objects.create(
            code='billing-empty',
            name='Sans modules',
            price=Decimal('10.00'),
            currency='GNF',
            duration_months=1,
            max_users=10,
        )
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=plan,
            status='active',
            amount=plan.price,
            currency=plan.currency,
            duration_months=1,
            max_users=10,
            included_modules=[],
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=30),
            created_by=self.platform_admin,
        )
        self.tenant.status = 'active'
        self.tenant.trial_activated_at = timezone.now()
        self.tenant.trial_ends_at = subscription.ends_at
        self.tenant.save()

        denied = self.client.patch(
            f'/api/v1/platform/tenants/{self.tenant.pk}/modules/',
            {'module_code': dependent.code, 'status': 'enabled'},
            format='json',
        )

        self.assertEqual(denied.status_code, 400)
        subscription.included_modules = [base.code]
        subscription.save(update_fields=['included_modules', 'updated_at'])

        enabled = self.client.patch(
            f'/api/v1/platform/tenants/{self.tenant.pk}/modules/',
            {'module_code': dependent.code, 'status': 'enabled'},
            format='json',
        )

        self.assertEqual(enabled.status_code, 200, enabled.data)
        self.assertTrue(
            TenantModuleOverride.objects.filter(
                tenant=self.tenant,
                module=dependent,
                status='enabled',
            ).exists()
        )

    def test_active_subscription_restricts_unincluded_business_modules(self):
        tenant_user = User.objects.create_user(
            username='billing_module_user',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        plan = PlatformPlan.objects.create(
            code='billing-dashboard-only',
            name='Tableau de bord uniquement',
            price=Decimal('100.00'),
            currency='GNF',
            duration_months=1,
            max_users=10,
        )
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=plan,
            status='active',
            amount=plan.price,
            currency=plan.currency,
            duration_months=1,
            max_users=10,
            included_modules=['dashboard'],
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=30),
            created_by=self.platform_admin,
        )
        self.tenant.status = 'active'
        self.tenant.trial_activated_at = timezone.now()
        self.tenant.trial_ends_at = subscription.ends_at
        self.tenant.save()

        self.assertEqual(module_for_request_path('/api/v1/products/'), 'products')
        self.assertTrue(tenant_module_is_enabled(self.tenant, 'dashboard'))
        self.assertFalse(tenant_module_is_enabled(self.tenant, 'products'))
        self.assertFalse(
            user_has_required_module(tenant_user, '/api/v1/products/')
        )

        session_client = APIClient()
        self.assertTrue(
            session_client.login(
                username=tenant_user.username,
                password='secret123',
            )
        )
        denied = session_client.get('/api/v1/products/')
        self.assertEqual(denied.status_code, 403)

        platform_client = APIClient()
        self.assertTrue(
            platform_client.login(
                username=self.platform_admin.username,
                password='secret123',
            )
        )
        isolated = platform_client.get('/api/v1/products/')
        self.assertEqual(isolated.status_code, 403)


class PlatformOperationsTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_user(
            username='operations_platform_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.tenant = Tenant.objects.create(
            slug='operations-tenant',
            name='Entreprise opérations',
            status='active',
            trial_activated_at=timezone.now(),
            trial_ends_at=timezone.now() + timedelta(days=30),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.platform_admin)

    def test_platform_user_access_is_filtered_and_audited(self):
        first_admin = User.objects.create_user(
            username='operations_admin_one',
            password='secret123',
            email='admin-one@example.test',
            role='admin',
            tenant=self.tenant,
        )
        User.objects.create_user(
            username='operations_admin_two',
            password='secret123',
            email='admin-two@example.test',
            role='admin',
            tenant=self.tenant,
        )

        listing = self.client.get(
            '/api/v1/platform/users/',
            {'search': 'Entreprise opérations', 'status': 'active'},
        )

        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data['count'], 2)
        user_data = next(
            item for item in listing.data['results']
            if item['id'] == first_admin.pk
        )
        self.assertEqual(user_data['tenantName'], self.tenant.name)
        self.assertEqual(user_data['email'], 'admin-one@example.test')

        deactivated = self.client.post(
            f'/api/v1/platform/users/{first_admin.pk}/deactivate/',
            {},
            format='json',
        )

        self.assertEqual(deactivated.status_code, 200, deactivated.data)
        self.assertFalse(deactivated.data['isActive'])
        self.assertTrue(
            PlatformAuditLog.objects.filter(
                action='user_access',
                tenant=self.tenant,
                details__action='deactivate',
            ).exists()
        )

    def test_last_company_admin_cannot_be_deactivated(self):
        admin = User.objects.create_user(
            username='operations_last_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )

        response = self.client.post(
            f'/api/v1/platform/users/{admin.pk}/deactivate/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        FRONTEND_BASE_URL='https://app.example.test',
    )
    def test_password_setup_link_is_sent_and_password_is_invalidated(self):
        admin = User.objects.create_user(
            username='operations_reset_admin',
            password='old-secret123',
            email='reset-admin@example.test',
            role='admin',
            tenant=self.tenant,
        )

        response = self.client.post(
            f'/api/v1/platform/users/{admin.pk}/send-setup-link/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        call_command('process_email_outbox')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('purpose=invitation', mail.outbox[0].body)
        admin.refresh_from_db()
        self.assertFalse(admin.has_usable_password())
        self.assertTrue(admin.must_change_password)

    @override_settings(FRONTEND_BASE_URL='https://app.example.test')
    @patch(
        'core.outbox.create_branded_email',
        side_effect=OSError('SMTP unavailable'),
    )
    def test_failed_password_setup_email_is_retained_for_retry(self, _create_email):
        admin = User.objects.create_user(
            username='operations_failed_reset_admin',
            password='old-secret123',
            email='failed-reset@example.test',
            role='admin',
            tenant=self.tenant,
        )

        response = self.client.post(
            f'/api/v1/platform/users/{admin.pk}/send-setup-link/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        admin.refresh_from_db()
        self.assertFalse(admin.has_usable_password())
        self.assertTrue(admin.invitation_pending)
        with self.assertRaises(CommandError):
            call_command('process_email_outbox')
        outbox_entry = EmailOutbox.objects.get(
            idempotency_key__startswith='invitation:',
        )
        self.assertEqual(outbox_entry.status, 'failed')
        self.assertEqual(outbox_entry.attempts, 1)
        self.assertTrue(outbox_entry.next_attempt_at > timezone.now())

    def test_platform_settings_reject_limits_below_current_usage_and_log_changes(self):
        PlatformSettings.objects.filter(pk=1).update(
            max_tenants=None,
            max_active_users=None,
        )
        User.objects.create_user(
            username='operations_active_user',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )

        rejected = self.client.patch(
            '/api/v1/platform/settings/',
            {'max_tenants': 0, 'max_active_users': 0},
            format='json',
        )
        self.assertEqual(rejected.status_code, 400)

        updated = self.client.patch(
            '/api/v1/platform/settings/',
            {'max_tenants': 5, 'max_active_users': 8},
            format='json',
        )

        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['maxTenants'], 5)
        self.assertEqual(updated.data['maxActiveUsers'], 8)
        self.assertTrue(
            PlatformAuditLog.objects.filter(action='settings_update').exists()
        )

    def test_platform_reports_aggregate_live_licence_and_module_usage(self):
        Tenant.objects.exclude(pk=self.tenant.pk).update(status='suspended')
        dashboard = PlatformModule.objects.create(
            code='operations-dashboard',
            name='Operations dashboard',
        )
        sales = PlatformModule.objects.create(
            code='operations-sales',
            name='Operations sales',
            dependencies=[dashboard.code],
        )
        plan = PlatformPlan.objects.create(
            code='operations-plan',
            name='Operations plan',
            price=Decimal('500.00'),
            currency='GNF',
            duration_months=1,
            max_users=10,
        )
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=plan,
            status='active',
            amount=plan.price,
            currency=plan.currency,
            duration_months=1,
            max_users=10,
            included_modules=[dashboard.code, sales.code],
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=30),
            created_by=self.platform_admin,
        )
        PlatformPayment.objects.create(
            tenant=self.tenant,
            subscription=subscription,
            amount=plan.price,
            currency='GNF',
            method='cash',
            status='confirmed',
            recorded_by=self.platform_admin,
        )

        response = self.client.get('/api/v1/platform/reports/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['tenants']['active'], 1)
        self.assertEqual(response.data['subscriptions']['byStatus']['active'], 1)
        self.assertEqual(
            response.data['confirmedPayments'][0],
            {'currency': 'GNF', 'total': '500.00', 'count': 1},
        )
        adoption = {
            module['code']: module['tenantCount']
            for module in response.data['moduleAdoption']
        }
        self.assertEqual(adoption[dashboard.code], 1)
        self.assertEqual(adoption[sales.code], 1)


class PlatformDemoRequestTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_user(
            username='demo_platform_admin',
            password='secret123',
            is_platform_admin=True,
        )
        self.tenant = Tenant.objects.create(
            slug='demo-request-tenant',
            name='Entreprise cliente',
            status='active',
        )
        self.tenant_admin = User.objects.create_user(
            username='demo_tenant_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        self.client = APIClient()

    def demo_payload(self, **overrides):
        return {
            'company_name': '  Société Exemple  ',
            'contact_name': '  Aïssatou Diallo  ',
            'email': '  DEMO@EXAMPLE.TEST ',
            'phone': ' +224 600 00 00 00 ',
            'message': ' Nous souhaitons découvrir les fonctions de gestion. ',
            'consent': True,
            **overrides,
        }

    def test_public_demo_request_is_validated_and_saved_for_central_review(self):
        response = self.client.post(
            '/api/v1/public/demo-requests/',
            self.demo_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(PlatformDemoRequest.objects.count(), 1)
        saved = PlatformDemoRequest.objects.get()
        self.assertEqual(saved.company_name, 'Société Exemple')
        self.assertEqual(saved.contact_name, 'Aïssatou Diallo')
        self.assertEqual(saved.email, 'demo@example.test')
        self.assertEqual(saved.phone, '+224 600 00 00 00')
        self.assertEqual(saved.status, 'new')
        self.assertIsNotNone(saved.consent_at)
        self.assertNotIn('email', response.data)

    def test_public_demo_request_requires_consent_and_valid_contact_data(self):
        response = self.client.post(
            '/api/v1/public/demo-requests/',
            self.demo_payload(consent=False, email='invalid-email'),
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlatformDemoRequest.objects.count(), 0)

    def test_only_platform_admin_can_review_and_update_demo_requests(self):
        demo_request = PlatformDemoRequest.objects.create(
            company_name='Entreprise confidentielle',
            contact_name='Contact privé',
            email='private@example.test',
            phone='+224600000001',
            message='Demande de présentation.',
            consent_at=timezone.now(),
        )

        anonymous_list = self.client.get('/api/v1/platform/demo-requests/')
        anonymous_update = self.client.patch(
            f'/api/v1/platform/demo-requests/{demo_request.id}/',
            {'status': 'contacted'},
            format='json',
        )
        self.assertEqual(anonymous_list.status_code, 403)
        self.assertEqual(anonymous_update.status_code, 403)

        self.client.force_authenticate(user=self.tenant_admin)
        denied_list = self.client.get('/api/v1/platform/demo-requests/')
        denied_update = self.client.patch(
            f'/api/v1/platform/demo-requests/{demo_request.id}/',
            {'status': 'contacted'},
            format='json',
        )
        self.assertEqual(denied_list.status_code, 403)
        self.assertEqual(denied_update.status_code, 403)

        self.client.force_authenticate(user=self.platform_admin)
        listed = self.client.get(
            '/api/v1/platform/demo-requests/',
            {'search': 'private@example.test', 'status': 'new'},
        )
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data['count'], 1)
        item = listed.data['results'][0]
        self.assertEqual(item['email'], 'private@example.test')
        self.assertEqual(item['companyName'], 'Entreprise confidentielle')

        updated = self.client.patch(
            f'/api/v1/platform/demo-requests/{demo_request.id}/',
            {'status': 'contacted'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        demo_request.refresh_from_db()
        self.assertEqual(demo_request.status, 'contacted')
