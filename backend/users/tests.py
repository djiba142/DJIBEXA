import base64
from datetime import timedelta
from io import BytesIO
from importlib import import_module
import tempfile

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image
from rest_framework.test import APIClient

from core.models import AuditLog, Tenant
from customers.models import Customer
from payments.models import Payment
from sales.models import Sale
from .models import User


class AuthLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            slug='users-test-tenant',
            name='Users Test Tenant',
            status='active',
        )
        self.user = User.objects.create_user(
            username='vendeur1',
            email='vendeur1@example.com',
            password='secret123',
            phone='+224600000001',
            pin_code='1234',
            role='sales',
            tenant=self.tenant,
        )

    def test_login_with_username_and_pin(self):
        response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '1234'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['user']['username'], 'vendeur1')
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.pin_code, '1234')

    def test_default_pin_cannot_authenticate_and_is_not_assigned_to_new_users(self):
        user_without_pin = User.objects.create_user(
            username='no_default_pin',
            password='secret123',
            role='sales',
        )
        self.assertEqual(user_without_pin.pin_code, '')

        response = self.client.post(
            '/api/users/login/',
            {'identifier': 'no_default_pin', 'pin': '0000'},
            format='json',
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.data['success'])

    def test_plaintext_pin_is_not_accepted_by_pin_authentication(self):
        self.user.pin_code = '1234'
        self.user.save(update_fields=['pin_code'])
        self.user.refresh_from_db()

        self.assertFalse(self.user.check_pin('1234'))

    def test_user_manager_hashes_pin_codes_when_creating_users(self):
        user = User.objects.create_user(
            username='hashed_pin_user',
            password='secret123',
            pin_code='2468',
        )

        self.assertNotEqual(user.pin_code, '2468')
        self.assertTrue(user.check_pin('2468'))

    def test_login_with_password(self):
        self.user.set_password('SecurePass!2026')
        self.user.save(update_fields=['password'])

        response = self.client.post(
            '/api/users/login/',
            {'identifier': 'vendeur1', 'password': 'SecurePass!2026'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])

    def test_login_rejects_password_shorter_than_eight_characters(self):
        response = self.client.post(
            '/api/users/login/',
            {'identifier': 'vendeur1', 'password': 'short'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)

    def test_login_with_phone_and_pin(self):
        response = self.client.post('/api/users/login/', {'identifier': '+224600000001', 'pin': '1234'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['user']['phone'], '+224600000001')

    def test_login_rejects_wrong_pin(self):
        response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '9999'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.data['success'])

    def test_login_rejects_pin_shorter_than_four_digits(self):
        response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '123'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('pin', response.data)

    def test_login_rejects_pin_with_non_numeric_characters(self):
        response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '12ab'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('pin', response.data)

    def test_successful_login_creates_audit_log(self):
        response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '1234'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(user=self.user, action='login').exists())

    def test_user_list_requires_admin_role(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, 403)

    def test_tenant_admin_creation_emails_and_enforces_temporary_password(self):
        admin = User.objects.create_user(
            username='temporary_password_admin',
            email='temporary.password.admin@example.com',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=admin)

        response = self.client.post(
            '/api/users/',
            {
                'username': 'new_employee',
                'email': 'new.employee@example.com',
                'role': 'sales',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        created_user = User.objects.get(username='new_employee')
        self.assertTrue(created_user.must_change_password)
        self.assertEqual(len(mail.outbox), 1)
        temporary_password_line = next(
            line for line in mail.outbox[0].body.splitlines()
            if line.startswith('Votre mot de passe provisoire est : ')
        )
        temporary_password = temporary_password_line.split(': ', 1)[1]
        self.assertTrue(created_user.check_password(temporary_password))
        self.assertIn('kourouma-logo.svg', mail.outbox[0].alternatives[0][0])

        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            '/api/users/login/',
            {'identifier': created_user.username, 'password': temporary_password},
            format='json',
        )
        self.assertEqual(login_response.status_code, 200, login_response.data)
        self.assertTrue(login_response.data['user']['must_change_password'])
        blocked = self.client.get('/api/users/')
        self.assertEqual(blocked.status_code, 403)

        changed = self.client.post(
            '/api/users/change-password/',
            {
                'current_password': temporary_password,
                'new_password': 'PermanentSecure!2026',
            },
            format='json',
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(changed.data['user']['must_change_password'])
        current_user = self.client.get('/api/users/me/')
        self.assertEqual(current_user.status_code, 200, current_user.content)
        self.assertFalse(current_user.data['must_change_password'])

    def test_user_profile_exposes_preferred_language(self):
        self.user.preferred_language = 'en'
        self.user.save(update_fields=['preferred_language'])
        self.client.force_authenticate(user=self.user)

        response = self.client.get('/api/users/me/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['preferred_language'], 'en')

    def test_user_can_update_password_from_profile(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            '/api/users/me/',
            {'password': 'NewSecurePass!2026'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecurePass!2026'))

    def test_user_can_update_personal_profile_and_upload_photo(self):
        self.client.force_authenticate(user=self.user)
        image = BytesIO()
        Image.new('RGB', (2, 2), color='blue').save(image, format='PNG')
        image.seek(0)

        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.patch(
                '/api/users/me/',
                {
                    'first_name': 'Aïssatou',
                    'last_name': 'Diallo',
                    'email': 'aissatou@example.com',
                    'phone': '+224600000002',
                    'photo': SimpleUploadedFile(
                        'profil.png',
                        image.read(),
                        content_type='image/png',
                    ),
                },
                format='multipart',
            )

            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['first_name'], 'Aïssatou')
            self.assertEqual(response.data['last_name'], 'Diallo')
            self.assertEqual(response.data['email'], 'aissatou@example.com')
            self.assertEqual(response.data['phone'], '+224600000002')
            self.assertTrue(response.data['photo'].startswith('http://testserver/media/profile_photos/'))

        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'sales')
        self.assertTrue(self.user.photo.name.startswith('profile_photos/'))

    def test_password_reset_request_emails_link_without_exposing_token(self):
        response = self.client.post(
            '/api/v1/users/pin-reset/request/',
            {'email': self.user.email},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertNotIn('reset_token', response.data)
        self.assertNotIn('reset_uid', response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            f'/reset-password?uid={urlsafe_base64_encode(force_bytes(self.user.pk))}&token=',
            mail.outbox[0].body,
        )
        self.assertIn('kourouma-logo.svg', mail.outbox[0].alternatives[0][0])

    def test_password_reset_request_does_not_disclose_unknown_email(self):
        response = self.client.post(
            '/api/v1/users/pin-reset/request/',
            {'email': 'unknown@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(
            response.data['message'],
            'Si ce compte existe, les instructions ont été envoyées à cette adresse.',
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_request_uses_same_response_for_known_and_unknown_email(self):
        known_response = self.client.post(
            '/api/v1/users/pin-reset/request/',
            {'email': self.user.email},
            format='json',
        )
        unknown_response = self.client.post(
            '/api/v1/users/pin-reset/request/',
            {'email': 'unknown@example.com'},
            format='json',
        )

        self.assertEqual(known_response.status_code, unknown_response.status_code)
        self.assertEqual(known_response.data, unknown_response.data)

    def test_password_reset_confirm_changes_password_with_valid_token(self):
        response = self.client.post(
            '/api/v1/users/pin-reset/confirm/',
            {
                'uid': urlsafe_base64_encode(force_bytes(self.user.pk)),
                'token': default_token_generator.make_token(self.user),
                'password': 'NewResetPassword!2026',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewResetPassword!2026'))

    def test_password_reset_confirm_rejects_invalid_token(self):
        response = self.client.post(
            '/api/v1/users/pin-reset/confirm/',
            {
                'uid': urlsafe_base64_encode(force_bytes(self.user.pk)),
                'token': 'invalid-token',
                'password': 'NewResetPassword!2026',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('NewResetPassword!2026'))

    def test_password_reset_confirm_rejects_invalid_encoded_uid(self):
        response = self.client.post(
            '/api/v1/users/pin-reset/confirm/',
            {'uid': 'not-a-user-id', 'token': 'invalid-token', 'password': 'NewResetPassword!2026'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['message'],
            'Le lien de réinitialisation est invalide ou expiré.',
        )

    def test_user_cannot_elevate_own_role_from_profile(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            '/api/users/me/',
            {'role': 'admin', 'is_active': False},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'sales')
        self.assertTrue(self.user.is_active)

    def test_user_gets_locked_after_repeated_failed_pin_attempts(self):
        for attempt in range(4):
            response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '9999'}, format='json')
            self.assertEqual(response.status_code, 401)
            self.assertIn('Code PIN incorrect', response.data['message'])

        response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '9999'}, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertIn('bloqué', response.data['message'])

        response = self.client.post('/api/users/login/', {'identifier': 'vendeur1', 'pin': '1234'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertIn('bloqué', response.data['message'])

    def test_user_can_switch_language_and_keyboard_layout_globally(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            '/api/users/me/',
            {'preferred_language': 'en', 'keyboard_layout': 'us'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, 'en')
        self.assertEqual(self.user.keyboard_layout, 'us')
        self.assertEqual(self.client.session.get('django_language'), 'en')

    def test_user_can_save_arabic_and_chinese_language_preferences(self):
        self.client.force_authenticate(user=self.user)

        for language in ('ar', 'zh'):
            with self.subTest(language=language):
                response = self.client.patch(
                    '/api/users/me/',
                    {'preferred_language': language},
                    format='json',
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['preferred_language'], language)
                self.user.refresh_from_db()
                self.assertEqual(self.user.preferred_language, language)
                self.assertEqual(self.client.session.get('django_language'), language)

    def test_admin_can_list_users(self):
        admin_user = User.objects.create_user(
            username='admin1',
            email='admin1@example.com',
            password='secret123',
            phone='+224600000002',
            pin_code='4321',
            role='admin',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=admin_user)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, 200)

    def test_tenant_license_blocks_login_and_existing_sessions(self):
        self.tenant.status = 'suspended'
        self.tenant.save(update_fields=['status'])
        login_response = self.client.post(
            '/api/users/login/',
            {'identifier': self.user.username, 'password': 'secret123'},
            format='json',
        )
        self.assertEqual(login_response.status_code, 403)
        self.assertFalse(login_response.data['success'])

        self.tenant.status = 'active'
        self.tenant.save(update_fields=['status'])
        self.assertTrue(self.client.login(
            username=self.user.username,
            password='secret123',
        ))
        self.tenant.status = 'suspended'
        self.tenant.save(update_fields=['status'])
        protected = self.client.get('/api/users/me/')
        self.assertEqual(protected.status_code, 403)

    def test_expired_tenant_license_blocks_login(self):
        self.tenant.trial_ends_at = timezone.now() - timedelta(days=1)
        self.tenant.save(update_fields=['trial_ends_at'])

        response = self.client.post(
            '/api/users/login/',
            {'identifier': self.user.username, 'password': 'secret123'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('licence', response.data['message'])

    def test_tenant_user_creation_enforces_active_user_limit(self):
        admin_user = User.objects.create_user(
            username='capacity_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        self.tenant.max_users = 3
        self.tenant.save(update_fields=['max_users'])
        self.client.force_authenticate(user=admin_user)
        first = self.client.post(
            '/api/users/',
            {
                'username': 'capacity_first_user',
                'email': 'capacity.first@example.com',
                'password': 'secret123',
                'role': 'sales',
            },
            format='json',
        )
        second = self.client.post(
            '/api/users/',
            {
                'username': 'capacity_second_user',
                'email': 'capacity.second@example.com',
                'password': 'secret123',
                'role': 'sales',
            },
            format='json',
        )

        self.assertEqual(first.status_code, 201, first.data)
        first_user = User.objects.get(username='capacity_first_user')
        self.assertTrue(first_user.must_change_password)
        temporary_password_line = next(
            line for line in mail.outbox[0].body.splitlines()
            if line.startswith('Votre mot de passe provisoire est : ')
        )
        self.assertTrue(
            first_user.check_password(temporary_password_line.split(': ', 1)[1])
        )
        self.assertEqual(second.status_code, 400)
        self.assertFalse(User.objects.filter(username='capacity_second_user').exists())

    def test_admin_user_management_is_scoped_to_tenant(self):
        admin_user = User.objects.create_user(
            username='tenant_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        other_tenant = Tenant.objects.create(
            slug='other-users-test-tenant',
            name='Other Users Test Tenant',
        )
        other_user = User.objects.create_user(
            username='other_tenant_user',
            password='secret123',
            role='sales',
            tenant=other_tenant,
        )
        platform_admin = User.objects.create_user(
            username='tenant_list_platform_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
            is_platform_admin=True,
        )
        self.client.force_authenticate(user=admin_user)

        listed = self.client.get('/api/users/')
        self.assertEqual(listed.status_code, 200)
        listed_ids = {user['id'] for user in listed.data['results']}
        self.assertIn(self.user.id, listed_ids)
        self.assertNotIn(other_user.id, listed_ids)
        self.assertNotIn(platform_admin.id, listed_ids)
        self.assertEqual(
            self.client.get(f'/api/users/{other_user.id}/').status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f'/api/users/{platform_admin.id}/').status_code,
            404,
        )

        created = self.client.post(
            '/api/users/',
            {
                'username': 'created_in_tenant',
                'email': 'created.in.tenant@example.com',
                'password': 'secret123',
                'role': 'sales',
                'tenant': other_tenant.id,
                'is_platform_admin': True,
            },
            format='json',
        )

        self.assertEqual(created.status_code, 201)
        created_user = User.objects.get(username='created_in_tenant')
        self.assertEqual(created_user.tenant, self.tenant)
        self.assertFalse(created_user.is_platform_admin)

    def test_unassigned_and_platform_admins_cannot_manage_tenant_users(self):
        unassigned_admin = User.objects.create_user(
            username='unassigned_admin',
            password='secret123',
            role='admin',
        )
        self.client.force_authenticate(user=unassigned_admin)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, 403)

        platform_admin = User.objects.create_user(
            username='platform_admin',
            password='secret123',
            role='admin',
            tenant=self.tenant,
            is_platform_admin=True,
            is_superuser=True,
            is_staff=True,
            additional_roles=['sales', 'stock'],
            must_change_password=True,
        )
        self.assertEqual(platform_admin.roles, [])
        self.assertFalse(platform_admin.has_any_role('admin', 'sales', 'stock'))
        self.client.force_authenticate(user=None)
        self.assertTrue(self.client.login(
            username='platform_admin',
            password='secret123',
        ))

        csrf_response = self.client.get('/api/v1/users/csrf/')
        self.assertEqual(csrf_response.status_code, 200, csrf_response.content)
        password_response = self.client.post(
            '/api/v1/users/change-password/',
            {
                'current_password': 'secret123',
                'new_password': 'A-new-secure-password-2026',
            },
            format='json',
            HTTP_X_CSRFTOKEN=csrf_response.json()['csrfToken'],
        )
        self.assertEqual(password_response.status_code, 200, password_response.data)

        self.assertEqual(self.client.get('/api/products/').status_code, 403)
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 403)
        self.assertEqual(self.client.get('/media/private-document.pdf').status_code, 403)

    def test_platform_admin_business_apis_are_also_blocked_with_basic_auth(self):
        platform_admin = User.objects.create_user(
            username='platform_basic_admin',
            password='secret123',
            role='admin',
            is_platform_admin=True,
        )
        credentials = base64.b64encode(
            b'platform_basic_admin:secret123',
        ).decode('ascii')
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Basic {credentials}',
        )

        response = self.client.get('/api/core/reports/')

        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=platform_admin.pk).exists())

    def test_admin_can_fetch_and_update_user_detail_from_v1_api(self):
        admin_user = User.objects.create_user(
            username='admin_detail',
            email='admin_detail@example.com',
            password='secret123',
            phone='+224600000007',
            pin_code='4321',
            role='admin',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=admin_user)

        response = self.client.get(f'/api/v1/users/{self.user.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'vendeur1')

        patch_response = self.client.patch(
            f'/api/v1/users/{self.user.id}/',
            {'role': 'stock'},
            format='json',
        )
        self.assertEqual(patch_response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'stock')
        self.assertTrue(AuditLog.objects.filter(model_name='User', action='update', record_id=self.user.id).exists())

        invalid_role_response = self.client.patch(
            f'/api/v1/users/{self.user.id}/',
            {'role': 'manager'},
            format='json',
        )
        self.assertEqual(invalid_role_response.status_code, 400)

    def test_sales_user_cannot_create_products(self):
        sales_user = User.objects.create_user(
            username='sales_user',
            email='sales_user@example.com',
            password='secret123',
            phone='+224600000003',
            pin_code='5678',
            role='sales',
        )
        self.client.force_authenticate(user=sales_user)
        response = self.client.post(
            '/api/products/',
            {
                'sku': 'SKU-SEC-01',
                'name': 'Produit interdit',
                'brand': 'NEXORA',
                'selling_price': '15000.00',
                'quantity': 10,
                'alert_threshold': 2,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_user_api_creates_and_updates_combined_roles(self):
        admin_user = User.objects.create_user(
            username='multi_role_admin',
            email='multi_role_admin@example.com',
            password='secret123',
            role='admin',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=admin_user)

        created = self.client.post(
            '/api/users/',
            {
                'username': 'solo_owner',
                'email': 'solo_owner@example.com',
                'password': 'secret123',
                'role': 'admin',
                'roles': ['admin', 'stock', 'sales'],
                'first_name': 'Solo',
                'last_name': 'Owner',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(set(created.data['roles']), {'admin', 'stock', 'sales'})
        account = User.objects.get(username='solo_owner')
        self.assertEqual(set(account.roles), {'admin', 'stock', 'sales'})
        self.assertTrue(account.has_any_role('admin', 'stock', 'sales'))
        self.assertEqual(account.tenant, self.tenant)

        updated = self.client.patch(
            f'/api/users/{account.id}/',
            {'roles': ['admin', 'stock']},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(set(account.roles), {'admin', 'stock'})
        self.assertNotIn('sales', account.roles)

    def test_combined_sales_and_stock_roles_grant_both_api_surfaces(self):
        combined_user = User.objects.create_user(
            username='combined_sales_stock',
            email='combined_sales_stock@example.com',
            password='secret123',
            role='stock',
            additional_roles=['sales'],
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=combined_user)

        response = self.client.get('/api/sales/catalog/', {'search': 'anything'})
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/api/inventory/stock/')
        self.assertEqual(response.status_code, 200)

    def test_stock_user_cannot_access_payment_creation(self):
        stock_user = User.objects.create_user(
            username='stock_user',
            email='stock_user@example.com',
            password='secret123',
            phone='+224600000004',
            pin_code='9999',
            role='stock',
        )
        customer = self.user
        self.client.force_authenticate(user=stock_user)
        response = self.client.post(
            '/api/payments/',
            {
                'customer': customer.id,
                'amount': '5000.00',
                'payment_method': 'cash',
                'reference': 'PAY-SEC-001',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_sales_user_cannot_update_sensitive_payment(self):
        sales_user = User.objects.create_user(
            username='sales_user_sensitive',
            email='sales_sensitive@example.com',
            password='secret123',
            phone='+224600000005',
            pin_code='1111',
            role='sales',
            tenant=self.tenant,
        )
        customer = Customer.objects.create(full_name='Client sensible', tenant=self.tenant)
        sale = Sale.objects.create(customer=customer, total_amount='1000.00', amount_paid='0.00', tenant=self.tenant)
        payment = Payment.objects.create(customer=customer, sale=sale, amount='500.00', payment_method='cash', reference='PAY-SENSITIVE-001')

        self.client.force_authenticate(user=sales_user)
        response = self.client.patch(
            f'/api/payments/{payment.id}/',
            {'amount': '750.00'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_stock_user_cannot_update_sensitive_payment(self):
        stock_user = User.objects.create_user(
            username='stock_sensitive',
            email='stock_sensitive@example.com',
            password='secret123',
            phone='+224600000006',
            pin_code='2222',
            role='stock',
            tenant=self.tenant,
        )
        customer = Customer.objects.create(full_name='Client gestionnaire', tenant=self.tenant)
        sale = Sale.objects.create(customer=customer, total_amount='1000.00', amount_paid='0.00', tenant=self.tenant)
        payment = Payment.objects.create(customer=customer, sale=sale, amount='500.00', payment_method='cash', reference='PAY-SENSITIVE-002')

        self.client.force_authenticate(user=stock_user)
        response = self.client.patch(
            f'/api/payments/{payment.id}/',
            {'amount': '750.00'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

        admin_user = User.objects.create_user(
            username='admin_sensitive',
            email='admin_sensitive@example.com',
            password='secret123',
            phone='+224600000008',
            pin_code='3333',
            role='admin',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=admin_user)
        response = self.client.patch(
            f'/api/payments/{payment.id}/',
            {'amount': '750.00'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_user_role_choices_only_offer_three_functional_roles(self):
        self.assertEqual(
            {role for role, _label in User.ROLE_CHOICES},
            {'admin', 'stock', 'sales'},
        )

    def test_role_migration_is_idempotent_and_keeps_consultation_accounts_inactive(self):
        manager = User.objects.create_user(username='legacy_manager', role='manager')
        viewer = User.objects.create_user(username='legacy_viewer', role='viewer')
        migration = import_module(
            'users.migrations.0008_merge_manager_and_stock_roles',
        )

        migration.merge_roles(apps, None)
        manager.refresh_from_db()
        viewer.refresh_from_db()
        self.assertEqual(manager.role, 'stock')
        self.assertTrue(manager.is_active)
        self.assertEqual(viewer.role, 'viewer')
        self.assertFalse(viewer.is_active)

        admin = User.objects.create_user(username='role_migration_admin', role='admin')
        admin.tenant = self.tenant
        admin.save(update_fields=['tenant'])
        viewer.tenant = self.tenant
        viewer.save(update_fields=['tenant'])
        self.client.force_authenticate(user=admin)
        reactivate_without_role = self.client.patch(
            f'/api/users/{viewer.id}/',
            {'is_active': True},
            format='json',
        )
        self.assertEqual(reactivate_without_role.status_code, 400)
        reactivate_with_role = self.client.patch(
            f'/api/users/{viewer.id}/',
            {'role': 'sales', 'is_active': True},
            format='json',
        )
        self.assertEqual(reactivate_with_role.status_code, 200)
        viewer.refresh_from_db()
        self.assertEqual(viewer.role, 'sales')
        self.assertTrue(viewer.is_active)

        migration.merge_roles(apps, None)
        manager.refresh_from_db()
        self.assertEqual(manager.role, 'stock')
