from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from products.models import Product

from .labels import ensure_carton_units
from .models import Carton, InventoryCostLayer, InventoryLocation, StockTransferCarton, StockUnit


def record_cost_layer(
    *,
    product: Product,
    quantity: int,
    unit_cost: Decimal | None,
    source: str,
    location: InventoryLocation | None = None,
    reference: str = '',
    transfer=None,
    received_at=None,
    is_available: bool = True,
) -> InventoryCostLayer | None:
    if quantity <= 0:
        return None
    return InventoryCostLayer.objects.create(
        product=product,
        location=location,
        transfer=transfer,
        source=source,
        reference=reference,
        received_at=received_at or timezone.now(),
        quantity_received=quantity,
        quantity_remaining=quantity,
        unit_cost=unit_cost,
        is_available=is_available,
    )


@transaction.atomic
def consume_fifo_cost(
    *,
    product: Product,
    quantity: int,
    location: InventoryLocation | None = None,
) -> Decimal | None:
    cost, _ = _consume_fifo_cost_layers(
        product=product,
        quantity=quantity,
        location=location,
    )
    return cost


@transaction.atomic
def consume_fifo_cost_with_layers(
    *,
    product: Product,
    quantity: int,
    location: InventoryLocation | None = None,
) -> tuple[Decimal | None, list[tuple[InventoryCostLayer, int]]]:
    return _consume_fifo_cost_layers(
        product=product,
        quantity=quantity,
        location=location,
    )


@transaction.atomic
def consume_fifo_cartons(
    *,
    product: Product,
    quantity: int,
    location: InventoryLocation,
    unit_status: str = 'sold',
    sale_item=None,
) -> list[tuple[Carton, int]]:
    if quantity <= 0:
        return []

    remaining = quantity
    consumed = []
    loose_units = list(
        StockUnit.objects.select_for_update()
        .filter(
            carton__product=product,
            location=location,
            status='available',
        )
        .filter(Q(is_separated=True) | ~Q(carton__location=location))
        .select_related('carton')
        .order_by('carton__created_at', 'carton_id', 'unit_number')
        .values('id', 'carton_id')[:remaining]
    )
    if loose_units:
        loose_unit_ids = [unit['id'] for unit in loose_units]
        StockUnit.objects.filter(id__in=loose_unit_ids).update(
            status=unit_status,
            transfer=None,
            updated_at=timezone.now(),
        )
        _link_units_to_sale(sale_item, loose_unit_ids)
        consumed_by_carton = {}
        for unit in loose_units:
            consumed_by_carton[unit['carton_id']] = consumed_by_carton.get(unit['carton_id'], 0) + 1
        cartons_by_id = Carton.objects.in_bulk(consumed_by_carton)
        consumed.extend(
            (cartons_by_id[carton_id], used)
            for carton_id, used in consumed_by_carton.items()
        )
        remaining -= len(loose_units)

    cartons = Carton.objects.select_for_update().filter(
        product=product,
        location=location,
        quantity__gt=0,
    ).exclude(
        pk__in=StockTransferCarton.objects.filter(
            transfer__status='shipped',
            is_partial=False,
        ).values('carton_id'),
    ).order_by('created_at', 'id')
    for carton in cartons:
        if not remaining:
            break
        ensure_carton_units(carton)
        used = min(remaining, carton.quantity)
        carton.quantity -= used
        carton.save(update_fields=['quantity', 'updated_at'])
        unit_ids = list(
            StockUnit.objects.select_for_update()
            .filter(
                carton=carton,
                location=location,
                status='available',
                is_separated=False,
            )
            .order_by('unit_number')
            .values_list('id', flat=True)[:used]
        )
        if len(unit_ids) != used:
            raise ValueError(
                f'Le carton {carton.reference} ne contient pas assez de pièces identifiables disponibles.'
            )
        StockUnit.objects.filter(id__in=unit_ids).update(
            status=unit_status,
            transfer=None,
            updated_at=timezone.now(),
        )
        _link_units_to_sale(sale_item, unit_ids)
        consumed.append((carton, used))
        remaining -= used
        if not remaining:
            break
    return consumed


def _link_units_to_sale(sale_item, unit_ids: list[int]) -> None:
    if sale_item is None or not unit_ids:
        return
    from sales.models import SaleItemTrackedUnit

    SaleItemTrackedUnit.objects.bulk_create([
        SaleItemTrackedUnit(sale_item=sale_item, stock_unit_id=unit_id)
        for unit_id in unit_ids
    ])


@transaction.atomic
def reserve_fifo_cartons_for_transfer(*, transfer, source_stock_quantity: int) -> list[StockTransferCarton]:
    cartons = Carton.objects.select_for_update().filter(
        product=transfer.product,
        location=transfer.from_location,
        quantity__gt=0,
    ).exclude(
        pk__in=StockTransferCarton.objects.filter(
            transfer__status='shipped',
            is_partial=False,
        ).values('carton_id'),
    ).order_by('created_at', 'id')
    carton_quantities = list(cartons)
    tracked_quantity = sum(carton.quantity for carton in carton_quantities)
    separated_unit_count = StockUnit.objects.filter(
        carton__product=transfer.product,
        location=transfer.from_location,
        status='available',
        is_separated=True,
        transfer__isnull=True,
    ).count()
    if tracked_quantity + separated_unit_count > source_stock_quantity:
        raise ValueError('La quantité suivie par carton dépasse le stock source disponible.')

    untracked_quantity = source_stock_quantity - tracked_quantity - separated_unit_count
    allocations = []
    remaining = transfer.quantity
    for carton in carton_quantities:
        if remaining <= 0:
            break
        quantity_shipped = min(remaining, carton.quantity)
        allocations.append(StockTransferCarton(
            transfer=transfer,
            carton=carton,
            quantity_shipped=quantity_shipped,
            is_partial=quantity_shipped < carton.quantity,
        ))
        remaining -= quantity_shipped

    loose_units_used = min(remaining, separated_unit_count)
    remaining -= loose_units_used
    if remaining > untracked_quantity:
        raise ValueError('La quantité demandée dépasse les unités suivies et le stock disponible.')
    return StockTransferCarton.objects.bulk_create(allocations)


@transaction.atomic
def ship_fifo_transfer_cartons(*, transfer) -> None:
    allocations = list(
        StockTransferCarton.objects.select_for_update()
        .select_related('carton')
        .filter(transfer=transfer)
        .order_by('carton__created_at', 'carton_id')
    )
    for allocation in allocations:
        carton = allocation.carton
        ensure_carton_units(carton)
        unit_ids = list(
            StockUnit.objects.select_for_update()
            .filter(
                carton=carton,
                location=transfer.from_location,
                status='available',
                is_separated=False,
                transfer__isnull=True,
            )
            .order_by('unit_number')
            .values_list('id', flat=True)[:allocation.quantity_shipped]
        )
        if len(unit_ids) != allocation.quantity_shipped:
            raise ValueError(
                f'Le carton {carton.reference} ne contient pas assez de pièces identifiables disponibles.'
            )
        StockUnit.objects.filter(id__in=unit_ids).update(
            status='in_transit',
            transfer=transfer,
            is_separated=allocation.is_partial,
            updated_at=timezone.now(),
        )
        if allocation.is_partial:
            carton.quantity -= allocation.quantity_shipped
            carton.save(update_fields=['quantity', 'updated_at'])
    allocated_quantity = sum(allocation.quantity_shipped for allocation in allocations)
    loose_to_ship = max(transfer.quantity - allocated_quantity, 0)
    if loose_to_ship:
        available_loose_units = StockUnit.objects.select_for_update().filter(
            carton__product=transfer.product,
            location=transfer.from_location,
            status='available',
            is_separated=True,
            transfer__isnull=True,
        ).order_by('carton__created_at', 'carton_id', 'unit_number')
        loose_to_ship = min(loose_to_ship, available_loose_units.count())
        loose_unit_ids = list(
            available_loose_units.values_list('id', flat=True)[:loose_to_ship]
        )
        StockUnit.objects.filter(id__in=loose_unit_ids).update(
            status='in_transit',
            transfer=transfer,
            updated_at=timezone.now(),
        )


@transaction.atomic
def receive_fifo_transfer_cartons(*, transfer, quantity_received: int) -> list[tuple[Carton, int]]:
    missing_quantity = transfer.quantity_shipped - quantity_received
    adjustments = []
    allocations = list(
        StockTransferCarton.objects.select_for_update()
        .select_related('carton')
        .filter(transfer=transfer)
        .order_by('carton__created_at', 'carton_id')
    )
    for allocation in allocations:
        carton = allocation.carton
        loss = min(missing_quantity, allocation.quantity_shipped)
        if not allocation.is_partial:
            carton.quantity -= loss
            carton.location = transfer.to_location
            carton.save(update_fields=['quantity', 'location', 'updated_at'])
        units = list(
            StockUnit.objects.select_for_update()
            .filter(carton=carton, transfer=transfer, status='in_transit')
            .order_by('unit_number')
        )
        if len(units) != allocation.quantity_shipped:
            raise ValueError(
                f'Le transfert {transfer.reference} ne retrouve pas toutes les pièces du carton {carton.reference}.'
            )
        lost_unit_ids = [unit.pk for unit in units[-loss:]] if loss else []
        received_unit_ids = [unit.pk for unit in units[:-loss]] if loss else [unit.pk for unit in units]
        if received_unit_ids:
            StockUnit.objects.filter(id__in=received_unit_ids).update(
                location=transfer.to_location,
                status='available',
                transfer=None,
                updated_at=timezone.now(),
            )
        if lost_unit_ids:
            StockUnit.objects.filter(id__in=lost_unit_ids).update(
                location=transfer.to_location,
                status='written_off',
                transfer=None,
                updated_at=timezone.now(),
            )
        allocation.quantity_received = allocation.quantity_shipped - loss
        allocation.save(update_fields=['quantity_received'])
        adjustments.append((carton, loss))
        missing_quantity -= loss
    allocation_received = sum(
        allocation.quantity_received or 0
        for allocation in allocations
    )
    loose_units = list(
        StockUnit.objects.select_for_update()
        .filter(transfer=transfer, status='in_transit', is_separated=True)
        .order_by('carton__created_at', 'carton_id', 'unit_number')
    )
    loose_received = min(
        len(loose_units),
        max(quantity_received - allocation_received, 0),
    )
    for index, unit in enumerate(loose_units):
        unit.location = transfer.to_location
        unit.status = 'available' if index < loose_received else 'written_off'
        unit.transfer = None
        unit.save(update_fields=['location', 'status', 'transfer', 'updated_at'])
    return adjustments


def _consume_fifo_cost_layers(
    *,
    product: Product,
    quantity: int,
    location: InventoryLocation | None,
) -> tuple[Decimal | None, list[tuple[InventoryCostLayer, int]]]:
    if quantity <= 0:
        return Decimal('0'), []

    layers = InventoryCostLayer.objects.select_for_update().filter(
        product=product,
        is_available=True,
        quantity_remaining__gt=0,
    )
    if location is not None:
        layers = layers.filter(location=location)

    remaining = quantity
    total_cost = Decimal('0')
    cost_is_known = True
    consumed_layers = []
    for layer in layers.order_by('received_at', 'id'):
        used = min(remaining, layer.quantity_remaining)
        layer.quantity_remaining -= used
        layer.save(update_fields=['quantity_remaining'])
        consumed_layers.append((layer, used))
        if layer.unit_cost is None:
            cost_is_known = False
        else:
            total_cost += layer.unit_cost * used
        remaining -= used
        if not remaining:
            break

    if remaining:
        cost_is_known = False
    return (total_cost if cost_is_known else None), consumed_layers


@transaction.atomic
def move_fifo_layers(*, transfer):
    remaining = transfer.quantity
    layers = InventoryCostLayer.objects.select_for_update().filter(
        product=transfer.product,
        location=transfer.from_location,
        is_available=True,
        quantity_remaining__gt=0,
    ).order_by('received_at', 'id')

    for layer in layers:
        moved = min(remaining, layer.quantity_remaining)
        layer.quantity_remaining -= moved
        layer.save(update_fields=['quantity_remaining'])
        record_cost_layer(
            product=transfer.product,
            location=transfer.to_location,
            transfer=transfer,
            quantity=moved,
            unit_cost=layer.unit_cost,
            source='transfer',
            reference=transfer.reference,
            received_at=layer.received_at,
            is_available=False,
        )
        remaining -= moved
        if not remaining:
            break

    if remaining:
        record_cost_layer(
            product=transfer.product,
            location=transfer.to_location,
            transfer=transfer,
            quantity=remaining,
            unit_cost=None,
            source='transfer',
            reference=transfer.reference,
            is_available=False,
        )


def receive_transferred_layers(transfer, quantity_received=None):
    remaining = transfer.quantity_shipped if quantity_received is None else quantity_received
    layers = InventoryCostLayer.objects.select_for_update().filter(
        transfer=transfer,
        is_available=False,
    ).order_by('received_at', 'id')
    for layer in layers:
        received_from_layer = min(remaining, layer.quantity_remaining)
        layer.quantity_remaining = received_from_layer
        layer.is_available = received_from_layer > 0
        layer.save(update_fields=['quantity_remaining', 'is_available'])
        remaining -= received_from_layer
