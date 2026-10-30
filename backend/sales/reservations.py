from django.db.models import Sum

from .models import CustomerOrderItem


def reserved_quantity(*, product_id: int, location_id: int, exclude_order_id: int | None = None) -> int:
    reservations = CustomerOrderItem.objects.filter(
        product_id=product_id,
        order__location_id=location_id,
        order__status='confirmed',
    )
    if exclude_order_id is not None:
        reservations = reservations.exclude(order_id=exclude_order_id)
    return reservations.aggregate(total=Sum('quantity'))['total'] or 0
