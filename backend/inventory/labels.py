from django.db import transaction

from .models import Carton, StockUnit


@transaction.atomic
def ensure_carton_units(carton: Carton) -> list[StockUnit]:
    carton = Carton.objects.select_for_update().get(pk=carton.pk)
    existing_numbers = set(
        carton.units.values_list('unit_number', flat=True)
    )
    untracked_before_labeling = max(carton.initial_quantity - carton.quantity, 0)
    missing_units = []
    for unit_number in range(1, carton.initial_quantity + 1):
        if unit_number in existing_numbers:
            continue
        if carton.purchase_receipt_id:
            prefix = f'REC{carton.purchase_receipt_id:06d}-{carton.pk:06d}'
        else:
            prefix = f'CTN{carton.pk:06d}'
        status = (
            'historical_unknown'
            if unit_number <= untracked_before_labeling
            else 'available'
        )
        missing_units.append(StockUnit(
            carton=carton,
            location=carton.location,
            unit_number=unit_number,
            reference=f'U-{prefix}-{unit_number:04d}',
            qr_code=f'KAP-UNIT-{carton.pk:06d}-{unit_number:04d}',
            status=status,
        ))
    if missing_units:
        StockUnit.objects.bulk_create(missing_units)
    return list(carton.units.order_by('unit_number'))
