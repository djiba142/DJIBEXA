from typing import TypeVar

from django.db.models import Model, Q, QuerySet

from .models import Tenant

ModelT = TypeVar('ModelT', bound=Model)


def tenant_for_user(user):
    """Resolve the assigned tenant, with fallback only for a single-tenant install."""
    if (
        not user
        or not user.is_authenticated
        or getattr(user, 'is_platform_admin', False)
    ):
        return None
    if user.tenant_id is not None:
        return Tenant.objects.filter(pk=user.tenant_id).first()

    tenants = list(Tenant.objects.order_by('pk')[:2])
    return tenants[0] if len(tenants) == 1 else None


def tenant_scoped_queryset(
    queryset: QuerySet[ModelT],
    user,
    tenant_field='tenant',
) -> QuerySet[ModelT]:
    tenant = tenant_for_user(user)
    if tenant is None:
        return queryset.none()

    if user.tenant_id is None:
        # Keep pre-tenant records visible only while the database has one tenant.
        return queryset.filter(
            Q(**{f'{tenant_field}_id': tenant.pk})
            | Q(**{f'{tenant_field}__isnull': True})
        )
    return queryset.filter(**{f'{tenant_field}_id': tenant.pk})
