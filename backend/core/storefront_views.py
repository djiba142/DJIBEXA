import logging

from PIL import Image, UnidentifiedImageError
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from core.models import AuditLog, Tenant, TenantStorefront, default_storefront_content
from core.storefront_serializers import StorefrontAssetSerializer
from core.storefront_storage import private_storefront_storage
from core.tenancy import tenant_for_user
from core.storefront_serializers import StorefrontContentSerializer
from products.models import Product
from users.permissions import IsTenantAdminUser, IsTenantAssignedUser

logger = logging.getLogger(__name__)
STOREFRONT_ASSETS = {
    'logo': ('draft_logo', 'published_logo'),
    'cover': ('draft_cover', 'published_cover'),
}
IMAGE_CONTENT_TYPES = {
    'JPEG': ('image/jpeg', 'jpg'),
    'PNG': ('image/png', 'png'),
    'WEBP': ('image/webp', 'webp'),
}


def _content_for_tenant(tenant):
    content = default_storefront_content()
    content['title'] = tenant.name
    return content


def _get_or_create_storefront(tenant):
    storefront, _ = TenantStorefront.objects.get_or_create(
        tenant=tenant,
        defaults={'draft_content': _content_for_tenant(tenant)},
    )
    return storefront


def _management_response(storefront):
    draft = _content_for_tenant(storefront.tenant)
    draft.update(storefront.draft_content or {})
    return {
        'tenant_slug': storefront.tenant.slug,
        'draft': draft,
        'published': storefront.published_content,
        'published_at': storefront.published_at,
        'is_published': bool(storefront.published_content),
        'draft_assets': {
            asset: bool(getattr(storefront, draft_field))
            for asset, (draft_field, _) in STOREFRONT_ASSETS.items()
        },
        'published_assets': {
            asset: bool(getattr(storefront, published_field))
            for asset, (_, published_field) in STOREFRONT_ASSETS.items()
        },
        'updated_at': storefront.updated_at,
    }


def _cleanup_unreferenced_asset(storefront_id, name):
    if not name:
        return
    references = TenantStorefront.objects.filter(pk=storefront_id).values(
        'draft_logo',
        'published_logo',
        'draft_cover',
        'published_cover',
    ).first()
    if references and name in references.values():
        return
    try:
        private_storefront_storage.delete(name)
    except OSError:
        logger.exception('Could not clean up an unreferenced storefront image.')


def _queue_asset_cleanup(storefront_id, names):
    for name in set(filter(None, names)):
        transaction.on_commit(
            lambda name=name: _cleanup_unreferenced_asset(storefront_id, name),
        )


def _image_response(image, asset, *, public):
    try:
        image.open('rb')
        with Image.open(image) as decoded:
            image_format = decoded.format
        content_type, extension = IMAGE_CONTENT_TYPES[image_format]
        image.seek(0)
    except (OSError, ValueError, UnidentifiedImageError, KeyError):
        return Response({'detail': 'Image configurée indisponible.'}, status=404)

    response = FileResponse(
        image,
        content_type=content_type,
        as_attachment=False,
        filename=f'{asset}.{extension}',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'public, max-age=300' if public else 'private, no-store'
    return response


class TenantStorefrontView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsTenantAdminUser,
    ]

    def get(self, request, *args, **kwargs):
        tenant = tenant_for_user(request.user)
        if tenant is None:
            raise PermissionDenied('Votre compte doit être rattaché à un espace d’entreprise.')
        storefront = _get_or_create_storefront(tenant)
        return Response(_management_response(storefront))

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        tenant = tenant_for_user(request.user)
        if tenant is None:
            raise PermissionDenied('Votre compte doit être rattaché à un espace d’entreprise.')
        if set(request.data) != {'draft'} or not isinstance(request.data.get('draft'), dict):
            return Response(
                {'detail': 'Envoyez uniquement la configuration dans le champ « draft ». '},
                status=status.HTTP_400_BAD_REQUEST,
            )

        storefront = _get_or_create_storefront(tenant)
        draft = _content_for_tenant(tenant)
        draft.update(storefront.draft_content or {})
        serializer = StorefrontContentSerializer(
            data={**draft, **request.data['draft']},
        )
        serializer.is_valid(raise_exception=True)
        storefront.draft_content = serializer.validated_data
        storefront.updated_by = request.user
        storefront.save(update_fields=['draft_content', 'updated_by', 'updated_at'])
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='TenantStorefront',
            record_id=storefront.pk,
            details=f'Brouillon de vitrine mis à jour pour {tenant.name}.',
        )
        return Response(_management_response(storefront))


class TenantStorefrontPublishView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsTenantAdminUser,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        tenant = tenant_for_user(request.user)
        if tenant is None:
            raise PermissionDenied('Votre compte doit être rattaché à un espace d’entreprise.')
        storefront = _get_or_create_storefront(tenant)
        draft = _content_for_tenant(tenant)
        draft.update(storefront.draft_content or {})
        serializer = StorefrontContentSerializer(data=draft)
        serializer.is_valid(raise_exception=True)

        old_published_assets = [
            getattr(storefront, published_field).name
            for _, published_field in STOREFRONT_ASSETS.values()
        ]
        storefront.draft_content = serializer.validated_data
        storefront.published_content = serializer.validated_data
        storefront.published_at = timezone.now()
        storefront.updated_by = request.user
        for draft_field, published_field in STOREFRONT_ASSETS.values():
            setattr(
                storefront,
                published_field,
                getattr(storefront, draft_field).name,
            )
        storefront.save(update_fields=[
            'draft_content',
            'published_content',
            *[field for pair in STOREFRONT_ASSETS.values() for field in pair[1:]],
            'published_at',
            'updated_by',
            'updated_at',
        ])
        _queue_asset_cleanup(storefront.pk, old_published_assets)
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='TenantStorefront',
            record_id=storefront.pk,
            details=f'Vitrine publiée pour {tenant.name}.',
        )
        return Response(_management_response(storefront))


class TenantStorefrontAssetView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsTenantAdminUser,
    ]
    parser_classes = [MultiPartParser, FormParser]

    def _storefront(self, request):
        tenant = tenant_for_user(request.user)
        if tenant is None:
            raise PermissionDenied('Votre compte doit être rattaché à un espace d’entreprise.')
        return _get_or_create_storefront(tenant)

    def get(self, request, asset, *args, **kwargs):
        fields = STOREFRONT_ASSETS.get(asset)
        if fields is None:
            raise NotFound('Image de vitrine inconnue.')
        storefront = self._storefront(request)
        image = getattr(storefront, fields[0])
        if not image:
            raise NotFound('Image non configurée.')
        return _image_response(image, asset, public=False)

    @transaction.atomic
    def post(self, request, asset, *args, **kwargs):
        fields = STOREFRONT_ASSETS.get(asset)
        if fields is None:
            raise NotFound('Image de vitrine inconnue.')
        if set(request.data) != {'image'}:
            return Response(
                {'detail': 'Envoyez une seule image dans le champ « image ». '},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = StorefrontAssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        storefront = self._storefront(request)
        field_name = fields[0]
        old_name = getattr(storefront, field_name).name
        getattr(storefront, field_name).save(
            serializer.validated_data['image'].name,
            serializer.validated_data['image'],
            save=False,
        )
        storefront.updated_by = request.user
        storefront.save(update_fields=[field_name, 'updated_by', 'updated_at'])
        _queue_asset_cleanup(storefront.pk, [old_name])
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='TenantStorefront',
            record_id=storefront.pk,
            details=f'Image {asset} de la vitrine remplacée pour {storefront.tenant.name}.',
        )
        return Response(_management_response(storefront))

    @transaction.atomic
    def delete(self, request, asset, *args, **kwargs):
        fields = STOREFRONT_ASSETS.get(asset)
        if fields is None:
            raise NotFound('Image de vitrine inconnue.')
        storefront = self._storefront(request)
        field_name = fields[0]
        old_name = getattr(storefront, field_name).name
        if not old_name:
            return Response(status=status.HTTP_204_NO_CONTENT)
        setattr(storefront, field_name, '')
        storefront.updated_by = request.user
        storefront.save(update_fields=[field_name, 'updated_by', 'updated_at'])
        _queue_asset_cleanup(storefront.pk, [old_name])
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='TenantStorefront',
            record_id=storefront.pk,
            details=f'Image {asset} retirée du brouillon de vitrine pour {storefront.tenant.name}.',
        )
        return Response(_management_response(storefront))


class PublicTenantStorefrontView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, slug, *args, **kwargs):
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None or tenant.status_at() != 'active':
            raise NotFound('Vitrine indisponible.')
        storefront = TenantStorefront.objects.filter(tenant=tenant).first()
        if storefront is None or not storefront.published_content:
            if tenant.slug == 'kourouma-auto-parts':
                return Response({
                    'tenant_slug': tenant.slug,
                    'content': None,
                    'published_at': None,
                    'legacy_fallback': True,
                })
            raise NotFound('Vitrine indisponible.')
        return Response({
            'tenant_slug': tenant.slug,
            'content': storefront.published_content,
            'published_at': storefront.published_at,
            'assets': {
                asset: (
                    request.build_absolute_uri(
                        f'/api/v1/core/public/storefront/{tenant.slug}/assets/{asset}/',
                    )
                    if getattr(storefront, published_field)
                    else None
                )
                for asset, (_, published_field) in STOREFRONT_ASSETS.items()
            },
        })


class PublicTenantStorefrontProductsView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, slug, *args, **kwargs):
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None or tenant.status_at() != 'active':
            raise NotFound('Vitrine indisponible.')
        storefront = TenantStorefront.objects.filter(tenant=tenant).first()
        if storefront is None or not storefront.published_content:
            raise NotFound('Vitrine indisponible.')

        products = Product.objects.filter(
            tenant=tenant,
            is_active=True,
        ).exclude(image='').order_by('-updated_at', 'pk')[:8]
        return Response([
            {
                'name': product.name,
                'brand': product.brand,
                'image': product.image,
            }
            for product in products
        ])


class PublicTenantStorefrontAssetView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, slug, asset, *args, **kwargs):
        fields = STOREFRONT_ASSETS.get(asset)
        if fields is None:
            raise NotFound('Image de vitrine inconnue.')
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None or tenant.status_at() != 'active':
            raise NotFound('Image de vitrine indisponible.')
        storefront = TenantStorefront.objects.filter(tenant=tenant).first()
        if storefront is None or not storefront.published_content:
            raise NotFound('Image de vitrine indisponible.')
        image = getattr(storefront, fields[1])
        if not image:
            raise NotFound('Image de vitrine indisponible.')
        return _image_response(image, asset, public=True)
