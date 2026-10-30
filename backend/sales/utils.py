from inventory.access import accessible_locations


def sales_locations_for_user(user):
    locations = accessible_locations(user).filter(
        is_active=True,
        location_type='shop',
    )
    if user.has_role('admin') or getattr(user, 'is_superuser', False):
        return locations.order_by('name')
    return locations.order_by('name')
