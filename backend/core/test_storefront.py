from io import BytesIO
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from core.models import AuditLog, Tenant, TenantStorefront
from products.models import Product
from users.models import User


def storefront_image(name='storefront.png', color=(25, 80, 130)):
    output = BytesIO()
    Image.new('RGB', (12, 12), color).save(output, format='PNG')
    return SimpleUploadedFile(name, output.getvalue(), content_type='image/png')


class TenantStorefrontApiTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            slug='storefront-a',
            name='Entreprise A',
            status='active',
        )
        self.tenant_b = Tenant.objects.create(
            slug='storefront-b',
            name='Entreprise B',
            status='active',
        )
        self.admin_a = User.objects.create_user(
            username='storefront_admin_a',
            password='secret123',
            role='admin',
            tenant=self.tenant_a,
        )
        self.admin_b = User.objects.create_user(
            username='storefront_admin_b',
            password='secret123',
            role='admin',
            tenant=self.tenant_b,
        )
        self.sales_a = User.objects.create_user(
            username='storefront_sales_a',
            password='secret123',
            role='sales',
            tenant=self.tenant_a,
        )
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.admin_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.admin_b)
        self.sales_client = APIClient()
        self.sales_client.force_authenticate(user=self.sales_a)

    def test_draft_is_tenant_scoped_and_not_public_before_publish(self):
        response_a = self.client_a.get('/api/v1/core/storefront/')
        response_b = self.client_b.get('/api/v1/core/storefront/')

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_a.data['tenant_slug'], self.tenant_a.slug)
        self.assertEqual(response_a.data['draft']['title'], self.tenant_a.name)
        self.assertFalse(response_a.data['is_published'])
        self.assertEqual(response_b.status_code, 200)
        self.assertEqual(response_b.data['tenant_slug'], self.tenant_b.slug)
        self.assertEqual(response_b.data['draft']['title'], self.tenant_b.name)
        self.assertNotEqual(response_a.data['draft']['title'], response_b.data['draft']['title'])

        public_response = APIClient().get(
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/',
        )
        self.assertEqual(public_response.status_code, 404)

    def test_admin_can_save_preview_and_publish_only_own_storefront(self):
        content = self.client_a.get('/api/v1/core/storefront/').data['draft']
        content.update({
            'title': 'Kourouma Auto Parts',
            'industry': 'Pièces automobiles',
            'tagline': 'La qualité qui fait la différence',
            'description': 'Présentation de Kourouma.',
            'services': ['Vente de pièces'],
            'categories': ['Freinage'],
        })

        update = self.client_a.patch(
            '/api/v1/core/storefront/',
            {'draft': content},
            format='json',
        )
        self.assertEqual(update.status_code, 200, update.data)
        self.assertEqual(update.data['draft']['title'], 'Kourouma Auto Parts')
        self.assertFalse(update.data['is_published'])
        self.assertEqual(
            APIClient().get(
                f'/api/v1/core/public/storefront/{self.tenant_a.slug}/',
            ).status_code,
            404,
        )

        publish = self.client_a.post('/api/v1/core/storefront/publish/', {}, format='json')
        self.assertEqual(publish.status_code, 200, publish.data)
        self.assertTrue(publish.data['is_published'])
        self.assertIsNotNone(publish.data['published_at'])

        public = APIClient().get(
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/',
        )
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data['content']['title'], 'Kourouma Auto Parts')
        self.assertEqual(public.data['content']['services'], ['Vente de pièces'])

        foreign_public = APIClient().get(
            f'/api/v1/core/public/storefront/{self.tenant_b.slug}/',
        )
        self.assertEqual(foreign_public.status_code, 404)
        self.assertFalse(TenantStorefront.objects.filter(tenant=self.tenant_b).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.admin_a,
                model_name='TenantStorefront',
                details__contains='publiée',
            ).exists(),
        )

    def test_public_storefront_lists_only_active_products_with_photos_from_its_tenant(self):
        TenantStorefront.objects.create(
            tenant=self.tenant_a,
            published_content={'title': self.tenant_a.name},
        )
        products = [
            Product.objects.create(
                tenant=self.tenant_a,
                sku='PUBLIC-ACTIVE',
                name='Filtre à huile',
                brand='NEXORA Parts',
                image='https://cdn.example.test/huile.jpg',
                selling_price=25000,
                quantity=12,
            ),
            Product.objects.create(
                tenant=self.tenant_a,
                sku='PUBLIC-NO-IMAGE',
                name='Produit sans photo',
            ),
            Product.objects.create(
                tenant=self.tenant_a,
                sku='PUBLIC-INACTIVE',
                name='Produit archivé',
                image='https://cdn.example.test/archive.jpg',
                is_active=False,
            ),
            Product.objects.create(
                tenant=self.tenant_b,
                sku='PUBLIC-FOREIGN',
                name='Produit autre entreprise',
                image='https://cdn.example.test/foreign.jpg',
            ),
        ]

        response = APIClient().get(
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/products/',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [{
            'name': products[0].name,
            'brand': products[0].brand,
            'image': products[0].image,
        }])
        self.assertNotIn('selling_price', response.data[0])
        self.assertNotIn('quantity', response.data[0])
        self.assertEqual(
            APIClient().get(
                f'/api/v1/core/public/storefront/{self.tenant_b.slug}/products/',
            ).status_code,
            404,
        )

    def test_non_admin_cannot_read_or_change_storefront(self):
        self.assertEqual(self.sales_client.get('/api/v1/core/storefront/').status_code, 403)
        self.assertEqual(
            self.sales_client.patch(
                '/api/v1/core/storefront/',
                {'draft': {'title': 'Unauthorized'}},
                format='json',
            ).status_code,
            403,
        )
        self.assertEqual(
            self.sales_client.post('/api/v1/core/storefront/publish/', {}, format='json').status_code,
            403,
        )

    def test_invalid_storefront_content_is_rejected_without_saving(self):
        original = self.client_a.get('/api/v1/core/storefront/').data['draft']
        invalid = {**original, 'unapproved_html': '<script>alert(1)</script>'}

        response = self.client_a.patch(
            '/api/v1/core/storefront/',
            {'draft': invalid},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(TenantStorefront.objects.get(tenant=self.tenant_a).updated_by_id)

        invalid_colors = {**original, 'primary_color': 'red'}
        response = self.client_a.patch(
            '/api/v1/core/storefront/',
            {'draft': invalid_colors},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_suspended_and_expired_tenants_have_no_public_storefront(self):
        storefront = TenantStorefront.objects.create(
            tenant=self.tenant_a,
            draft_content={'title': self.tenant_a.name},
            published_content={'title': self.tenant_a.name},
        )
        self.assertTrue(storefront.published_content)

        public_client = APIClient()
        unknown = public_client.get('/api/v1/core/public/storefront/unknown/')
        self.assertEqual(unknown.status_code, 404)

        self.tenant_a.status = 'suspended'
        self.tenant_a.save(update_fields=['status'])
        suspended = public_client.get(
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/',
        )
        self.assertEqual(suspended.status_code, 404)

        self.tenant_a.status = 'active'
        self.tenant_a.trial_ends_at = timezone.now() - timedelta(days=1)
        self.tenant_a.save(update_fields=['status', 'trial_ends_at'])
        expired = public_client.get(
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/',
        )
        self.assertEqual(expired.status_code, 404)

    def test_kourouma_legacy_fallback_is_only_available_while_tenant_is_active(self):
        legacy_tenant, _ = Tenant.objects.get_or_create(
            slug='kourouma-auto-parts',
            defaults={
                'name': 'Kourouma Auto Parts',
                'status': 'active',
            },
        )
        legacy_tenant.status = 'active'
        legacy_tenant.trial_ends_at = None
        legacy_tenant.save(update_fields=['status', 'trial_ends_at'])
        public_client = APIClient()

        fallback = public_client.get(
            f'/api/v1/core/public/storefront/{legacy_tenant.slug}/',
        )
        self.assertEqual(fallback.status_code, 200)
        self.assertTrue(fallback.data['legacy_fallback'])
        self.assertIsNone(fallback.data['content'])

        legacy_tenant.status = 'suspended'
        legacy_tenant.save(update_fields=['status'])
        self.assertEqual(
            public_client.get(
                f'/api/v1/core/public/storefront/{legacy_tenant.slug}/',
            ).status_code,
            404,
        )

    def test_storefront_assets_are_private_until_published_and_tenant_scoped(self):
        logo_upload = self.client_a.post(
            '/api/v1/core/storefront/assets/logo/',
            {'image': storefront_image()},
            format='multipart',
        )
        self.assertEqual(logo_upload.status_code, 200, logo_upload.data)
        self.assertTrue(logo_upload.data['draft_assets']['logo'])
        storefront = TenantStorefront.objects.get(tenant=self.tenant_a)
        self.assertTrue(
            storefront.draft_logo.name.startswith(f'{self.tenant_a.slug}/logo/'),
            storefront.draft_logo.name,
        )
        self.assertFalse(storefront.published_logo)
        self.assertEqual(
            self.client_a.get('/api/v1/core/storefront/assets/logo/').status_code,
            200,
        )
        self.assertEqual(
            APIClient().get(
                f'/api/v1/core/public/storefront/{self.tenant_a.slug}/assets/logo/',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.sales_client.post(
                '/api/v1/core/storefront/assets/logo/',
                {'image': storefront_image()},
                format='multipart',
            ).status_code,
            403,
        )

        published = self.client_a.post(
            '/api/v1/core/storefront/publish/',
            {},
            format='json',
        )
        self.assertEqual(published.status_code, 200, published.data)
        self.assertTrue(published.data['published_assets']['logo'])
        public = APIClient().get(
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/',
        )
        self.assertEqual(public.status_code, 200)
        self.assertTrue(public.data['assets']['logo'].endswith(
            f'/public/storefront/{self.tenant_a.slug}/assets/logo/',
        ))

        public_image = APIClient().get(
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/assets/logo/',
        )
        self.assertEqual(public_image.status_code, 200)
        self.assertEqual(public_image['Content-Type'], 'image/png')
        self.assertEqual(public_image['X-Content-Type-Options'], 'nosniff')

        foreign_asset = APIClient().get(
            f'/api/v1/core/public/storefront/{self.tenant_b.slug}/assets/logo/',
        )
        self.assertEqual(foreign_asset.status_code, 404)

    def test_replacing_or_removing_draft_asset_does_not_change_published_image_until_publish(self):
        self.client_a.post(
            '/api/v1/core/storefront/assets/logo/',
            {'image': storefront_image(color=(20, 40, 60))},
            format='multipart',
        )
        self.client_a.post('/api/v1/core/storefront/publish/', {}, format='json')
        public_asset_path = (
            f'/api/v1/core/public/storefront/{self.tenant_a.slug}/assets/logo/'
        )
        first_published_response = APIClient().get(public_asset_path)
        first_published_image = b''.join(first_published_response.streaming_content)

        self.client_a.post(
            '/api/v1/core/storefront/assets/logo/',
            {'image': storefront_image(color=(170, 110, 40))},
            format='multipart',
        )
        replacement_response = APIClient().get(public_asset_path)
        self.assertEqual(b''.join(replacement_response.streaming_content), first_published_image)

        removed = self.client_a.delete('/api/v1/core/storefront/assets/logo/')
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(removed.data['draft_assets']['logo'])
        self.assertTrue(removed.data['published_assets']['logo'])
        retained_response = APIClient().get(public_asset_path)
        self.assertEqual(b''.join(retained_response.streaming_content), first_published_image)

        publish = self.client_a.post('/api/v1/core/storefront/publish/', {}, format='json')
        self.assertFalse(publish.data['published_assets']['logo'])
        self.assertEqual(APIClient().get(public_asset_path).status_code, 404)

    def test_storefront_image_upload_rejects_invalid_image_data(self):
        response = self.client_a.post(
            '/api/v1/core/storefront/assets/cover/',
            {
                'image': SimpleUploadedFile(
                    'cover.png',
                    b'not an image',
                    content_type='image/png',
                ),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TenantStorefront.objects.filter(tenant=self.tenant_a).exists())
