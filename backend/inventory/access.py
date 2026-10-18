from .models import InventoryLocation
from core.tenancy import tenant_scoped_queryset


def accessible_locations(user):
    locations = tenant_scoped_queryset(InventoryLocation.objects.all(), user)
    if user.has_role('admin') or getattr(user, 'is_superuser', False):
        return locations
    if not locations.filter(authorized_users__isnull=False).exists():
        return locations
    return locations.filter(authorized_users=user)


def qr_accessible_locations(user):
    locations = accessible_locations(user)
    if user.has_role('admin') or getattr(user, 'is_superuser', False):
        return locations
    if user.has_role('stock'):
        return locations
    if user.has_role('sales'):
        locations = locations.filter(is_active=True, location_type='shop')
        if locations.filter(authorized_users__isnull=False).exists():
            locations = locations.filter(authorized_users=user)
        return locations
    return locations.none()
