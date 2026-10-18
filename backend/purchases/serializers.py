from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from core.tenancy import tenant_for_user, tenant_scoped_queryset
from inventory.costing import record_cost_layer
from inventory.labels import ensure_carton_units
from inventory.models import Carton, InventoryLocation, StockItem, StockMovement
from products.models import Product
from suppliers.models import Supplier
from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    ReceiptQuarantine,
)
from suppliers.models import ExchangeRate


@transaction.atomic
def validate_purchase_receipt(purchase_receipt, user=None):
    order = purchase_receipt.purchase_order
    default_location = purchase_receipt.location or InventoryLocation.objects.filter(
        tenant_id=order.tenant_id,
        location_type='warehouse',
    ).first()
    if default_location is None:
        default_location = InventoryLocation.objects.create(
            tenant_id=order.tenant_id,
            name='Entrepôt principal',
            code='WH-DEFAULT',
            location_type='warehouse',
            address='Stock par défaut',
        )
    purchase_receipt.location = default_location

    for item in purchase_receipt.items.order_by('product_id', 'id'):
        product = Product.objects.select_for_update().get(pk=item.product_id)
        item.product = product
        accepted = item.quantity_accepted
        quarantine = item.quantity_quarantined
        unit_cost = item.base_unit_cost

        if accepted:
            stock_item, _ = StockItem.objects.get_or_create(
                product=product,
                location=default_location,
            )
            stock_item = StockItem.objects.select_for_update().get(pk=stock_item.pk)
            stock_item.quantity += accepted
            stock_item.save(update_fields=['quantity', 'updated_at'])

            product.quantity = (product.quantity or 0) + accepted
            product.cost_price = unit_cost
            product.purchase_price = Decimal(str(item.unit_cost)) * purchase_receipt.exchange_rate
            product.save(update_fields=['quantity', 'cost_price', 'purchase_price', 'updated_at'])
            record_cost_layer(
                product=product,
                location=default_location,
                quantity=accepted,
                unit_cost=unit_cost,
                source='receipt',
                reference=purchase_receipt.reference,
            )
            StockMovement.objects.create(
                product=product,
                location=default_location,
                movement_type='in',
                quantity=accepted,
                reference=purchase_receipt.reference,
                notes='Quantité acceptée à la réception fournisseur',
                created_by=user,
            )

        if quarantine:
            ReceiptQuarantine.objects.create(
                receipt_item=item,
                location=default_location,
                quantity=quarantine,
                quantity_remaining=quarantine,
                unit_cost=unit_cost,
                reason=item.discrepancy_reason or purchase_receipt.discrepancy_reason,
            )
            StockMovement.objects.create(
                product=product,
                location=default_location,
                movement_type='quarantine_in',
                quantity=quarantine,
                reference=purchase_receipt.reference,
                notes=item.discrepancy_reason or purchase_receipt.discrepancy_reason,
                created_by=user,
            )

        carton_count = (accepted + item.items_per_carton - 1) // item.items_per_carton
        for carton_index in range(carton_count):
            carton_quantity = min(
                item.items_per_carton,
                accepted - carton_index * item.items_per_carton,
            )
            carton = Carton.objects.create(
                product=product,
                location=default_location,
                purchase_receipt=purchase_receipt,
                reference=f'RECEIPT-{purchase_receipt.pk}-{uuid4().hex[:12]}',
                quantity=carton_quantity,
                initial_quantity=carton_quantity,
                items_per_carton=item.items_per_carton,
                supplier_reference=item.supplier_reference,
                supplier_barcode=item.supplier_barcode,
            )
            carton.reference = f'CTN-{carton.pk:06d}'
            carton.save(update_fields=['reference'])
            ensure_carton_units(carton)

    received_totals = {}
    for receipt in order.receipts.filter(status='received').prefetch_related('items'):
        for receipt_item in receipt.items.all():
            received_totals[receipt_item.product_id] = received_totals.get(receipt_item.product_id, 0) + receipt_item.quantity_received

    is_complete = all(
        received_totals.get(order_item.product_id, 0)
        + sum(
            item.quantity_received
            for item in purchase_receipt.items.all()
            if item.product_id == order_item.product_id
        )
        >= order_item.quantity
        for order_item in order.items.all()
    )
    order.status = 'received' if is_complete else 'partial_received'
    order.save(update_fields=['status', 'updated_at'])
    purchase_receipt.status = 'received'
    purchase_receipt.reviewed_by = user
    purchase_receipt.reviewed_at = timezone.now()
    purchase_receipt.reviewed_version = purchase_receipt.version
    purchase_receipt.save(update_fields=[
        'location',
        'status',
        'reviewed_by',
        'reviewed_at',
        'reviewed_version',
        'updated_at',
    ])
    return purchase_receipt


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'product', 'quantity', 'unit_cost', 'total_price']
        read_only_fields = ['id', 'total_price']

    def get_total_price(self, obj):
        return obj.total_price

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
        if (
            request
            and request.user.is_authenticated
            and request.user.has_role('stock')
            and not request.user.has_role('admin')
        ):
            fields.pop('unit_cost', None)
            fields.pop('total_price', None)
        return fields


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    total_amount = serializers.SerializerMethodField()
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    exchange_rate_applied_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'supplier', 'supplier_name', 'reference', 'order_date',
            'expected_delivery_date', 'status', 'currency', 'exchange_rate',
            'exchange_rate_date', 'reference_exchange_rate', 'exchange_rate_reason',
            'exchange_rate_applied_at', 'exchange_rate_applied_by',
            'exchange_rate_applied_by_name', 'notes',
            'total_amount', 'items', 'created_at', 'updated_at', 'created_by',
        ]
        read_only_fields = [
            'id', 'order_date', 'status', 'created_at', 'updated_at', 'total_amount', 'created_by',
            'exchange_rate_date', 'reference_exchange_rate', 'exchange_rate_applied_at',
            'exchange_rate_applied_by', 'exchange_rate_applied_by_name',
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['supplier'].queryset = tenant_scoped_queryset(
                Supplier.objects.all(),
                request.user,
            )
        if (
            request
            and request.user.is_authenticated
            and request.user.has_role('stock')
            and not request.user.has_role('admin')
        ):
            fields.pop('total_amount', None)
            fields['supplier'].read_only = self.instance is not None
            fields['status'].read_only = True
            fields['exchange_rate_reason'].read_only = True
        return fields

    def get_total_amount(self, obj):
        return obj.total_amount

    def get_exchange_rate_applied_by_name(self, obj):
        user = obj.exchange_rate_applied_by
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()

    def validate(self, attrs):
        currency = attrs.get('currency', getattr(self.instance, 'currency', 'GNF')).upper()
        request = self.context.get('request')
        tenant = tenant_for_user(request.user) if request else None
        supplier = attrs.get(
            'supplier',
            getattr(self.instance, 'supplier', None),
        )
        if supplier and tenant and supplier.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'supplier': 'Le fournisseur doit appartenir à votre entreprise.',
            })
        items = attrs.get('items')
        product_tenant_ids = (
            [item['product'].tenant_id for item in items]
            if items is not None
            else (
                self.instance.items.values_list('product__tenant_id', flat=True)
                if self.instance is not None
                else []
            )
        )
        if supplier and supplier.tenant_id and any(
            product_tenant_id != supplier.tenant_id
            for product_tenant_id in product_tenant_ids
        ):
            raise serializers.ValidationError({
                'items': 'Tous les produits doivent appartenir à la même entreprise que le fournisseur.',
            })
        if currency == 'GNF':
            attrs.update({
                'currency': currency,
                'exchange_rate': Decimal('1'),
                'exchange_rate_date': None,
                'reference_exchange_rate': None,
                'exchange_rate_reason': '',
                'exchange_rate_applied_at': None,
                'exchange_rate_applied_by': None,
            })
            return attrs

        if not currency.isalpha() or len(currency) != 3:
            raise serializers.ValidationError({
                'currency': 'Utilisez un code devise ISO à trois lettres.',
            })

        rate_is_being_changed = (
            self.instance is None
            or 'currency' in attrs
            or 'exchange_rate' in attrs
        )
        if not rate_is_being_changed:
            return attrs

        reference_rate = ExchangeRate.objects.filter(
            source_currency=currency,
            target_currency='GNF',
            effective_date__lte=timezone.localdate(),
        ).order_by('-effective_date', '-created_at').first()
        if reference_rate is None:
            raise serializers.ValidationError({
                'currency': f'Aucun taux de référence validé n’est configuré pour {currency}/GNF.',
            })

        applied_rate = attrs.get('exchange_rate', reference_rate.rate)
        if applied_rate <= 0:
            raise serializers.ValidationError({
                'exchange_rate': 'Le taux de conversion doit être supérieur à zéro.',
            })

        user = getattr(request, 'user', None)
        is_admin = bool(
            user
            and user.is_authenticated
            and (user.has_role('admin') or getattr(user, 'is_superuser', False))
        )
        is_override = applied_rate != reference_rate.rate
        if is_override and not is_admin:
            raise serializers.ValidationError({
                'exchange_rate': 'Seul un administrateur peut appliquer un taux différent du taux de référence.',
            })

        reason = str(attrs.get('exchange_rate_reason', '')).strip()
        if is_override and not reason:
            raise serializers.ValidationError({
                'exchange_rate_reason': 'Un motif est obligatoire pour déroger au taux de référence.',
            })
        attrs.update({
            'currency': currency,
            'exchange_rate': applied_rate,
            'exchange_rate_date': reference_rate.effective_date,
            'reference_exchange_rate': reference_rate.rate,
            'exchange_rate_reason': reason if is_override else '',
            'exchange_rate_applied_at': timezone.now(),
            'exchange_rate_applied_by': user if user and user.is_authenticated else None,
        })
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        validated_data['status'] = 'draft'
        request = self.context.get('request')
        tenant = tenant_for_user(request.user) if request else None
        if tenant is not None:
            validated_data['tenant'] = tenant
        purchase_order = PurchaseOrder.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseOrderItem.objects.create(purchase_order=purchase_order, **item_data)
        return purchase_order

    def update(self, instance, validated_data):
        if instance.status != 'draft':
            raise serializers.ValidationError(
                'Seule une commande brouillon peut être modifiée.'
            )
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseOrderItem.objects.create(purchase_order=instance, **item_data)
        return instance


class PurchaseReceiptItemSerializer(serializers.ModelSerializer):
    items_per_carton = serializers.IntegerField(required=False, min_value=1)
    quantity_accepted = serializers.IntegerField(required=False, min_value=0)
    quantity_quarantined = serializers.IntegerField(required=False, min_value=0)

    line_total = serializers.SerializerMethodField()
    real_unit_cost = serializers.SerializerMethodField()
    real_line_total = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseReceiptItem
        fields = [
            'id', 'product', 'quantity_received', 'quantity_accepted',
            'quantity_quarantined', 'quantity_quarantine_remaining',
            'discrepancy_reason', 'unit_cost', 'items_per_carton',
            'supplier_reference', 'supplier_barcode', 'line_total', 'real_unit_cost',
            'real_line_total', 'supplier_lot_reference', 'condition_status',
            'packaging_condition', 'notes',
        ]
        read_only_fields = [
            'id', 'quantity_quarantine_remaining', 'line_total',
            'real_unit_cost', 'real_line_total',
        ]

    def validate_items_per_carton(self, value):
        if value <= 0:
            raise serializers.ValidationError('La quantité par carton doit être positive.')
        return value

    def get_line_total(self, obj):
        return obj.line_total

    def get_real_unit_cost(self, obj):
        return obj.real_unit_cost

    def get_real_line_total(self, obj):
        return obj.real_line_total

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
        if (
            request
            and request.user.is_authenticated
            and request.user.has_role('stock')
            and not request.user.has_role('admin')
        ):
            for field_name in ('unit_cost', 'line_total', 'real_unit_cost', 'real_line_total'):
                fields.pop(field_name, None)
        return fields

    def validate(self, attrs):
        received = attrs.get(
            'quantity_received',
            getattr(self.instance, 'quantity_received', 0),
        )
        accepted = attrs.get('quantity_accepted', received)
        quarantined = attrs.get('quantity_quarantined', 0)
        if received <= 0:
            raise serializers.ValidationError({
                'quantity_received': 'La quantité réellement reçue doit être positive.',
            })
        if accepted + quarantined != received:
            raise serializers.ValidationError(
                'La quantité acceptée et la quantité mise en quarantaine doivent correspondre à la quantité reçue.'
            )
        attrs['quantity_accepted'] = accepted
        attrs['quantity_quarantined'] = quarantined
        if quarantined and not (
            attrs.get('discrepancy_reason')
            or getattr(self.instance, 'discrepancy_reason', '')
        ):
            raise serializers.ValidationError({
                'discrepancy_reason': 'Un motif est obligatoire pour une quantité mise en quarantaine.',
            })
        return attrs


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    items = PurchaseReceiptItemSerializer(many=True)
    total_cost = serializers.SerializerMethodField()
    supplier_name = serializers.CharField(source='purchase_order.supplier.name', read_only=True)
    reference_exchange_rate = serializers.DecimalField(
        source='purchase_order.reference_exchange_rate',
        max_digits=18,
        decimal_places=6,
        read_only=True,
        allow_null=True,
    )
    exchange_rate_reason = serializers.CharField(
        source='purchase_order.exchange_rate_reason',
        read_only=True,
    )
    exchange_rate_applied_at = serializers.DateTimeField(
        source='purchase_order.exchange_rate_applied_at',
        read_only=True,
        allow_null=True,
    )
    exchange_rate_applied_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseReceipt
        fields = [
            'id', 'purchase_order', 'supplier_name', 'location', 'reference',
            'received_date', 'status', 'currency', 'exchange_rate',
            'exchange_rate_date', 'cost_status', 'allocation_method', 'notes',
            'discrepancy_reason', 'decision_reason', 'created_by', 'submitted_by',
            'submitted_at', 'reviewed_by', 'reviewed_at', 'version',
            'reviewed_version', 'transport_cost', 'customs_cost',
            'handling_cost', 'insurance_cost', 'other_cost', 'total_cost',
            'reference_exchange_rate', 'exchange_rate_reason',
            'exchange_rate_applied_at', 'exchange_rate_applied_by_name',
            'items', 'created_at', 'updated_at', 'supplier_document_reference',
        ]
        read_only_fields = [
            'id', 'status', 'currency', 'exchange_rate',
            'exchange_rate_date', 'cost_status', 'decision_reason', 'created_by',
            'submitted_by', 'submitted_at', 'reviewed_by', 'reviewed_at',
            'version', 'reviewed_version', 'created_at', 'updated_at', 'total_cost',
        ]

    def get_total_cost(self, obj):
        return obj.total_cost

    def get_exchange_rate_applied_by_name(self, obj):
        user = obj.purchase_order.exchange_rate_applied_by
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['purchase_order'].queryset = tenant_scoped_queryset(
                PurchaseOrder.objects.all(),
                request.user,
            )
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        if (
            request
            and request.user.is_authenticated
            and request.user.has_role('stock')
            and not request.user.has_role('admin')
        ):
            for field_name in (
                'transport_cost',
                'customs_cost',
                'handling_cost',
                'insurance_cost',
                'other_cost',
                'total_cost',
            ):
                fields.pop(field_name, None)
            if self.instance is not None:
                fields['purchase_order'].read_only = True
                fields['location'].read_only = True
        return fields

    def validate(self, attrs):
        items = attrs.get('items')
        if self.instance is not None and self.instance.status not in {'draft', 'changes_requested'}:
            raise serializers.ValidationError(
                'Cette réception est verrouillée. Seul un brouillon ou une correction demandée peut être modifié.'
            )
        if self.instance is None and not items:
            raise serializers.ValidationError({'items': 'Au moins un produit doit être reçu.'})

        if items is not None:
            if not items:
                raise serializers.ValidationError({'items': 'Au moins un produit doit être reçu.'})

            purchase_order = attrs.get('purchase_order', getattr(self.instance, 'purchase_order', None))
            if purchase_order is not None:
                request = self.context.get('request')
                tenant = (
                    tenant_for_user(request.user)
                    if request and request.user.is_authenticated
                    else None
                )
                location = attrs.get(
                    'location',
                    getattr(self.instance, 'location', None),
                )
                if (
                    location is not None
                    and location.tenant_id != purchase_order.tenant_id
                    and not (
                        location.tenant_id is None
                        and request
                        and request.user.is_authenticated
                        and request.user.tenant_id is None
                        and tenant is not None
                        and tenant.pk == purchase_order.tenant_id
                    )
                ):
                    raise serializers.ValidationError({
                        'location': 'L’emplacement doit appartenir à la même entreprise que la commande.',
                    })
                if purchase_order.status not in {'approved', 'partial_received', 'received'}:
                    raise serializers.ValidationError({
                        'purchase_order': 'La commande doit être approuvée avant sa réception.',
                    })
                order_item_products = {item.product_id for item in purchase_order.items.all()}
                received_products = {item['product'].id for item in items if 'product' in item}
                if not received_products.issubset(order_item_products):
                    raise serializers.ValidationError({'items': 'Un produit reçu ne correspond pas à la commande fournisseur.'})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        request = self.context.get('request')
        purchase_order = validated_data['purchase_order']
        if purchase_order.status not in {'approved', 'partial_received', 'received'}:
            raise serializers.ValidationError({
                'purchase_order': 'La commande doit être approuvée avant sa réception.',
            })
        order_prices = {
            item.product_id: item.unit_cost
            for item in purchase_order.items.all()
        }
        for item_data in items_data:
            item_data.setdefault('quantity_accepted', item_data['quantity_received'])
            item_data.setdefault('quantity_quarantined', 0)
            item_data['quantity_quarantine_remaining'] = item_data['quantity_quarantined']
            if (
                request
                and request.user.is_authenticated
                and request.user.has_role('stock')
                and not request.user.has_role('admin')
            ):
                item_data['unit_cost'] = order_prices[item_data['product'].id]
        validated_data['status'] = 'draft'
        validated_data['currency'] = purchase_order.currency
        validated_data['exchange_rate'] = purchase_order.exchange_rate
        validated_data['exchange_rate_date'] = purchase_order.exchange_rate_date
        validated_data['cost_status'] = 'provisional'
        validated_data['created_by'] = request.user if request else None
        purchase_receipt = PurchaseReceipt.objects.create(**validated_data)

        for item_data in items_data:
            item_data.setdefault('items_per_carton', item_data['quantity_received'])
            PurchaseReceiptItem.objects.create(purchase_receipt=purchase_receipt, **item_data)

        return purchase_receipt

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        request = self.context.get('request')
        if instance.status == 'changes_requested':
            instance.status = 'draft'
            instance.decision_reason = ''
        if (
            items_data is not None
            and request
            and request.user.has_role('stock')
            and not request.user.has_role('admin')
        ):
            order_prices = {
                item.product_id: item.unit_cost
                for item in instance.purchase_order.items.all()
            }
            for item_data in items_data:
                item_data['unit_cost'] = order_prices[item_data['product'].id]

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                item_data.setdefault('quantity_accepted', item_data['quantity_received'])
                item_data.setdefault('quantity_quarantined', 0)
                item_data['quantity_quarantine_remaining'] = item_data['quantity_quarantined']
                item_data.setdefault('items_per_carton', item_data['quantity_received'])
                PurchaseReceiptItem.objects.create(purchase_receipt=instance, **item_data)

        instance.version += 1
        instance.save(update_fields=['version', 'status', 'decision_reason', 'updated_at'])
        return instance


class ReceiptQuarantineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='receipt_item.product.name', read_only=True)
    receipt_reference = serializers.CharField(
        source='receipt_item.purchase_receipt.reference',
        read_only=True,
    )

    class Meta:
        model = ReceiptQuarantine
        fields = [
            'id', 'receipt_item', 'product_name', 'receipt_reference',
            'location', 'quantity', 'quantity_remaining', 'unit_cost',
            'status', 'reason', 'resolution_reason', 'resolved_by',
            'resolved_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
