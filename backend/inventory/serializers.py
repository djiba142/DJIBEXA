from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from core.tenancy import tenant_for_user, tenant_scoped_queryset

from .costing import (
    consume_fifo_cartons,
    consume_fifo_cost,
    move_fifo_layers,
    receive_fifo_transfer_cartons,
    receive_transferred_layers,
    record_cost_layer,
    reserve_fifo_cartons_for_transfer,
    ship_fifo_transfer_cartons,
)
from products.models import Product
from users.permissions import role_permission
from .labels import ensure_carton_units
from .models import (
    Carton,
    InventoryCount,
    InventoryCountItem,
    InventoryLocation,
    SampleCarton,
    StockItem,
    StockMovement,
    StockReplenishmentRequest,
    StockTransfer,
    StockUnit,
)


@transaction.atomic
def transition_stock_transfer(
    transfer,
    target_status,
    user=None,
    quantity_received=None,
    variance_reason='',
):
    transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    product = Product.objects.select_for_update().get(pk=transfer.product_id)
    transfer.product = product
    source_item, _ = StockItem.objects.select_for_update().get_or_create(
        product=product,
        location=transfer.from_location,
    )

    if target_status == 'validated':
        if transfer.status != 'requested':
            raise ValidationError('Le transfert doit être demandé avant validation.')
        if source_item.quantity < transfer.quantity:
            raise ValidationError('La quantité demandée dépasse le stock disponible dans l’emplacement source.')
        transfer.approved_by = user
    elif target_status == 'shipped':
        if transfer.status != 'validated':
            raise ValidationError('Le transfert doit être validé avant expédition.')
        if source_item.quantity < transfer.quantity:
            raise ValidationError('La quantité en stock source est insuffisante pour ce transfert.')
        try:
            reserve_fifo_cartons_for_transfer(
                transfer=transfer,
                source_stock_quantity=source_item.quantity,
            )
            ship_fifo_transfer_cartons(transfer=transfer)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        source_item.quantity -= transfer.quantity
        source_item.save(update_fields=['quantity', 'updated_at'])
        move_fifo_layers(transfer=transfer)
        transfer.quantity_shipped = transfer.quantity
        transfer.shipped_by = user
        transfer.shipped_at = timezone.now()
        StockMovement.objects.create(
            product=transfer.product,
            location=transfer.from_location,
            movement_type='out',
            quantity=transfer.quantity,
            reference=transfer.reference,
            notes=(
                f'Transfert vers {transfer.to_location.name}. '
                'Les cartons suivis concernés sont réservés entiers selon FIFO.'
            ),
            created_by=user,
        )
    elif target_status == 'received':
        if transfer.status != 'shipped':
            raise ValidationError('Le transfert doit être expédié avant réception.')
        received = transfer.quantity_shipped if quantity_received is None else quantity_received
        if received < 0 or received > transfer.quantity_shipped:
            raise ValidationError(
                "La quantité réceptionnée doit être comprise entre zéro et la quantité expédiée."
            )
        if received != transfer.quantity_shipped and not variance_reason.strip():
            raise ValidationError(
                "Un motif est obligatoire lorsque la quantité reçue diffère de la quantité expédiée."
            )
        destination_item, _ = StockItem.objects.select_for_update().get_or_create(
            product=transfer.product,
            location=transfer.to_location,
        )
        destination_item.quantity += received
        destination_item.save(update_fields=['quantity', 'updated_at'])
        receive_transferred_layers(transfer, received)
        try:
            carton_adjustments = receive_fifo_transfer_cartons(
                transfer=transfer,
                quantity_received=received,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if received:
            carton_notes = ', '.join(
                f'{carton.reference}: -{lost} unité(s)'
                for carton, lost in carton_adjustments
                if lost
            )
            StockMovement.objects.create(
                product=transfer.product,
                location=transfer.to_location,
                movement_type='in',
                quantity=received,
                reference=transfer.reference,
                notes=(
                    f'Transfert depuis {transfer.from_location.name}.'
                    + (f' Écart ajusté FIFO sur les cartons: {carton_notes}.' if carton_notes else '')
                ),
                created_by=user,
            )
        lost_quantity = transfer.quantity_shipped - received
        if lost_quantity:
            if (product.quantity or 0) < lost_quantity:
                raise ValidationError(
                    'Le stock global ne permet pas de comptabiliser la perte du transfert.'
                )
            product.quantity -= lost_quantity
            product.save(update_fields=['quantity', 'updated_at'])
            StockMovement.objects.create(
                product=transfer.product,
                location=transfer.to_location,
                movement_type='out',
                quantity=lost_quantity,
                reference=f'{transfer.reference}-LOSS',
                notes=f'Écart perdu pendant le transfert {transfer.reference}. {variance_reason.strip()}',
                created_by=user,
            )
        transfer.quantity_received = received
        transfer.variance_reason = variance_reason
        transfer.received_by = user
        transfer.received_at = timezone.now()
    else:
        raise ValidationError('Transition de transfert non supportée.')

    transfer.status = target_status
    transfer.save()
    return transfer


class InventoryLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryLocation
        fields = [
            'id', 'tenant', 'name', 'code', 'location_type', 'address',
            'is_active', 'authorized_users', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['authorized_users'].queryset = tenant_scoped_queryset(
                get_user_model().objects.all(),
                request.user,
            )
        return fields


class StockItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()
    sample_quantity = serializers.IntegerField(read_only=True, default=0)
    physical_quantity = serializers.SerializerMethodField()

    class Meta:
        model = StockItem
        fields = [
            'id', 'product', 'product_name', 'location', 'location_name',
            'quantity', 'sample_quantity', 'physical_quantity', 'updated_at',
        ]
        read_only_fields = ['id', 'updated_at']

    def get_product_name(self, obj):
        return obj.product.name if obj.product else None

    def get_location_name(self, obj):
        return obj.location.name if obj.location else None

    def get_physical_quantity(self, obj):
        return obj.quantity + getattr(obj, 'sample_quantity', 0)


class StockUnitSerializer(serializers.ModelSerializer):
    product = serializers.IntegerField(source='carton.product_id', read_only=True)
    product_name = serializers.CharField(source='carton.product.name', read_only=True)
    product_reference = serializers.CharField(source='carton.product.sku', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    carton_reference = serializers.CharField(source='carton.reference', read_only=True)

    class Meta:
        model = StockUnit
        fields = [
            'id', 'product', 'product_name', 'product_reference', 'location',
            'location_name', 'carton_reference', 'unit_number', 'reference',
            'status', 'is_separated', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class StockUnitInitializationSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    location = serializers.PrimaryKeyRelatedField(queryset=InventoryLocation.objects.all())

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        if attrs['product'].tenant_id != attrs['location'].tenant_id:
            raise serializers.ValidationError(
                'Le produit et l’emplacement doivent appartenir à la même entreprise.',
            )
        return attrs


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'location', 'location_name',
            'movement_type', 'quantity', 'reference', 'notes', 'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'product_name', 'location_name']

    def get_product_name(self, obj):
        return obj.product.name if obj.product else None

    def get_location_name(self, obj):
        return obj.location.name if obj.location else None

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        product = attrs.get('product')
        location = attrs.get('location')
        quantity = attrs.get('quantity', 0)
        movement_type = attrs.get('movement_type')

        if quantity < 0 or (movement_type != 'adjustment' and quantity == 0):
            raise serializers.ValidationError({
                'quantity': 'La quantité doit être positive (ou zéro pour un ajustement).',
            })
        if movement_type == 'adjustment':
            raise serializers.ValidationError({
                'movement_type': (
                    'Les corrections de stock doivent passer par un inventaire soumis '
                    'et validé afin de conserver leur justification.'
                ),
            })
        if movement_type in {'quarantine_in', 'quarantine_out'}:
            raise serializers.ValidationError({
                'movement_type': 'Les mouvements de quarantaine sont créés uniquement par les flux de contrôle.',
            })

        if not product or not location:
            raise serializers.ValidationError('Produit et emplacement sont obligatoires.')
        if product.tenant_id != location.tenant_id:
            raise serializers.ValidationError(
                'Le produit et l’emplacement doivent appartenir à la même entreprise.',
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        product = Product.objects.select_for_update().get(pk=validated_data['product'].pk)
        location = validated_data['location']
        quantity = validated_data['quantity']
        movement_type = validated_data['movement_type']
        created_by = validated_data.get('created_by')

        stock_item, _ = StockItem.objects.get_or_create(product=product, location=location)
        stock_item = StockItem.objects.select_for_update().get(pk=stock_item.pk)

        if movement_type == 'in':
            stock_item.quantity += quantity
            product.quantity = (product.quantity or 0) + quantity
            record_cost_layer(
                product=product,
                location=location,
                quantity=quantity,
                unit_cost=product.cost_price if product.cost_price > 0 else None,
                source='movement',
                reference=validated_data.get('reference', ''),
            )
        elif movement_type == 'out':
            if stock_item.quantity < quantity:
                raise serializers.ValidationError({
                    'quantity': 'La quantité sortante dépasse le stock disponible.',
                })
            stock_item.quantity -= quantity
            if (product.quantity or 0) - quantity < 0:
                raise ValidationError('La quantité globale du produit ne peut pas devenir négative.')
            product.quantity -= quantity
            consume_fifo_cost(product=product, quantity=quantity, location=location)
        elif movement_type == 'adjustment':
            difference = quantity - stock_item.quantity
            product.quantity += quantity - stock_item.quantity
            stock_item.quantity = quantity
            if difference > 0:
                record_cost_layer(
                    product=product,
                    location=location,
                    quantity=difference,
                    unit_cost=product.cost_price if product.cost_price > 0 else None,
                    source='adjustment',
                    reference=validated_data.get('reference', ''),
                )
            elif difference < 0:
                consume_fifo_cost(
                    product=product,
                    quantity=abs(difference),
                    location=location,
                )
        else:
            raise ValidationError('Type de mouvement non supporté.')

        stock_item.save(update_fields=['quantity', 'updated_at'])
        if movement_type in {'in', 'out', 'adjustment'}:
            product.save(update_fields=['quantity', 'updated_at'])

        movement_data = dict(validated_data)
        movement_data.pop('created_by', None)

        movement = StockMovement.objects.create(
            created_by=created_by,
            **movement_data,
        )
        return movement


class StockTransferSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    from_location_name = serializers.SerializerMethodField()
    to_location_name = serializers.SerializerMethodField()

    class Meta:
        model = StockTransfer
        fields = [
            'id', 'product', 'product_name', 'from_location', 'from_location_name',
            'to_location', 'to_location_name', 'quantity', 'reference', 'status',
            'quantity_shipped', 'quantity_received', 'variance_reason', 'approved_by',
            'shipped_by', 'received_by', 'shipped_at', 'received_at',
            'notes', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'quantity_shipped', 'quantity_received', 'variance_reason',
            'approved_by', 'shipped_by', 'received_by', 'shipped_at', 'received_at',
            'created_by', 'created_at', 'updated_at', 'product_name',
            'from_location_name', 'to_location_name',
        ]

    def get_product_name(self, obj):
        return obj.product.name if obj.product else None

    def get_from_location_name(self, obj):
        return obj.from_location.name if obj.from_location else None

    def get_to_location_name(self, obj):
        return obj.to_location.name if obj.to_location else None

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
            fields['from_location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
            fields['to_location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        product = attrs.get('product')
        from_location = attrs.get('from_location')
        to_location = attrs.get('to_location')
        quantity = attrs.get('quantity', 0)

        if not product or not from_location or not to_location:
            raise serializers.ValidationError('Produit et emplacements sont obligatoires.')
        if from_location == to_location:
            raise serializers.ValidationError({'to_location': 'La destination doit être différente de l’origine.'})
        if quantity <= 0:
            raise serializers.ValidationError({'quantity': 'La quantité du transfert doit être strictement positive.'})
        if (
            product.tenant_id != from_location.tenant_id
            or product.tenant_id != to_location.tenant_id
        ):
            raise serializers.ValidationError(
                'Le produit et les deux emplacements doivent appartenir à la même entreprise.',
            )

        source_item = StockItem.objects.filter(product=product, location=from_location).first()
        if not source_item or source_item.quantity < quantity:
            raise serializers.ValidationError({'quantity': 'La quantité demandée dépasse le stock disponible dans l’emplacement source.'})

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        created_by = request.user if request and getattr(request, 'user', None) else None
        validated_data.pop('created_by', None)
        validated_data['status'] = 'requested'
        return StockTransfer.objects.create(created_by=created_by, **validated_data)


class StockReplenishmentRequestSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_reference = serializers.CharField(source='product.sku', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    requester_name = serializers.CharField(source='requested_by.display_name', read_only=True)
    reviewer_name = serializers.CharField(source='reviewed_by.display_name', read_only=True)
    remaining_quantity = serializers.SerializerMethodField()

    class Meta:
        model = StockReplenishmentRequest
        fields = [
            'id', 'reference', 'product', 'product_name', 'product_reference',
            'shop', 'shop_name', 'requested_quantity', 'approved_quantity',
            'request_reason', 'refusal_reason', 'status', 'requested_by',
            'requester_name', 'reviewed_by', 'reviewer_name', 'reviewed_at',
            'completed_at', 'remaining_quantity', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reference', 'approved_quantity', 'refusal_reason', 'status',
            'requested_by', 'requester_name', 'reviewed_by', 'reviewer_name',
            'reviewed_at', 'completed_at', 'created_at', 'updated_at',
            'product_name', 'product_reference', 'shop_name',
        ]
        validators = []

    def validate_requested_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError('La quantité demandée doit être positive.')
        return value

    def get_remaining_quantity(self, obj):
        received = sum(
            transfer.quantity_received or 0
            for transfer in obj.transfers.all()
            if transfer.status == 'received'
        )
        committed = sum(
            transfer.quantity
            for transfer in obj.transfers.all()
            if transfer.status in {'requested', 'validated', 'shipped'}
        )
        return max(obj.requested_quantity - received - committed, 0)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
            fields['shop'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        product = attrs.get('product')
        shop = attrs.get('shop')
        if product and not product.is_active:
            raise serializers.ValidationError({'product': 'Ce produit est inactif.'})
        if shop and (shop.location_type != 'shop' or not shop.is_active):
            raise serializers.ValidationError(
                {'shop': 'La demande doit viser une boutique active.'}
            )
        if product and shop and product.tenant_id != shop.tenant_id:
            raise serializers.ValidationError(
                'Le produit et la boutique doivent appartenir à la même entreprise.',
            )
        return attrs


class CartonSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_reference = serializers.CharField(source='product.sku', read_only=True)
    location_name = serializers.SerializerMethodField()
    receipt_reference = serializers.CharField(source='purchase_receipt.reference', read_only=True, allow_null=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Carton
        fields = [
            'id', 'product', 'product_name', 'product_reference', 'location', 'location_name',
            'purchase_receipt', 'receipt_reference', 'reference', 'quantity', 'initial_quantity',
            'items_per_carton', 'supplier_reference', 'supplier_barcode', 'status', 'qr_code',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'purchase_receipt', 'receipt_reference', 'initial_quantity', 'status',
            'qr_code', 'created_at', 'updated_at', 'product_name', 'product_reference',
            'location_name',
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        if request and not role_permission('cartons.manage')().has_permission(request, None):
            fields.pop('qr_code', None)
        return fields

    def get_product_name(self, obj):
        return obj.product.name if obj.product else None

    def get_location_name(self, obj):
        return obj.location.name if obj.location else None

    def get_status(self, obj):
        if obj.transfer_allocations.filter(
            transfer__status='shipped',
            is_partial=False,
        ).exists():
            return 'en_transit'
        if obj.quantity <= 0:
            return 'vide'
        if obj.quantity < obj.initial_quantity:
            return 'partiellement_utilise'
        if obj.location.location_type == 'shop':
            return 'boutique'
        return 'en_stock'

    def validate(self, attrs):
        if self.instance is not None and 'quantity' in attrs:
            raise serializers.ValidationError({
                'quantity': 'Le contenu d’un carton doit être modifié via une réception ou un inventaire validé.',
            })

        product = attrs.get('product', self.instance.product if self.instance else None)
        location = attrs.get('location', self.instance.location if self.instance else None)
        quantity = attrs.get('quantity', self.instance.quantity if self.instance else 0)
        items_per_carton = attrs.get(
            'items_per_carton',
            self.instance.items_per_carton if self.instance else 0,
        )

        if not product or not location:
            raise serializers.ValidationError('Produit et emplacement sont obligatoires.')
        if product.tenant_id != location.tenant_id:
            raise serializers.ValidationError(
                'Le produit et l’emplacement doivent appartenir à la même entreprise.',
            )
        if quantity <= 0:
            raise serializers.ValidationError({'quantity': 'La quantité du carton doit être strictement positive.'})
        if items_per_carton <= 0:
            raise serializers.ValidationError({'items_per_carton': 'Le nombre d’éléments par carton doit être positif.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        product = Product.objects.select_for_update().get(pk=validated_data['product'].pk)
        location = validated_data['location']
        stock_item = StockItem.objects.select_for_update().filter(
            product=product,
            location=location,
        ).first()
        if stock_item is None:
            raise serializers.ValidationError({
                'quantity': 'Le carton doit correspondre à un stock déjà enregistré dans cet emplacement.',
            })
        tracked_carton_quantity = Carton.objects.select_for_update().filter(
            product=product,
            location=location,
        ).aggregate(total=Sum('quantity'))['total'] or 0
        historical_unknown_quantity = StockUnit.objects.filter(
            carton__product=product,
            location=location,
            status='historical_unknown',
        ).count()
        separated_unit_quantity = StockUnit.objects.filter(
            carton__product=product,
            location=location,
            status='available',
            is_separated=True,
            transfer__isnull=True,
        ).count()
        untracked_quantity = (
            stock_item.quantity
            - tracked_carton_quantity
            - historical_unknown_quantity
            - separated_unit_quantity
        )
        if validated_data['quantity'] > untracked_quantity:
            raise serializers.ValidationError({
                'quantity': (
                    f'Il ne reste que {max(untracked_quantity, 0)} unité(s) de stock non suivies '
                    'à rattacher à un carton.'
                ),
            })
        carton = Carton.objects.create(**validated_data)
        ensure_carton_units(carton)
        return carton


class SampleCartonSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_reference = serializers.CharField(source='product.sku', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = SampleCarton
        fields = [
            'id', 'product', 'product_name', 'product_reference', 'location', 'location_name',
            'reference', 'sample_count', 'qr_code', 'created_at',
        ]
        read_only_fields = [
            'id', 'product_name', 'product_reference', 'reference', 'qr_code', 'created_at',
            'location_name',
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        product = attrs.get('product')
        location = attrs.get('location')
        sample_count = attrs.get('sample_count')
        if not product or not product.is_active:
            raise serializers.ValidationError({'product': 'Choisissez un produit actif.'})
        if not location or location.location_type != 'shop':
            raise serializers.ValidationError({'location': 'Les cartons d’échantillons doivent être rattachés à une boutique.'})
        if product and location and product.tenant_id != location.tenant_id:
            raise serializers.ValidationError(
                'Le produit et la boutique doivent appartenir à la même entreprise.',
            )
        if sample_count is None or sample_count <= 0:
            raise serializers.ValidationError({'sample_count': 'Le nombre d’échantillons doit être supérieur à zéro.'})
        return attrs


class InventoryCountItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = InventoryCountItem
        fields = ['id', 'product', 'product_name', 'product_sku', 'theoretical_quantity', 'counted_quantity']
        read_only_fields = ['product', 'product_name', 'product_sku', 'theoretical_quantity']

    def validate_counted_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError('La quantité comptée ne peut pas être négative.')
        return value


class InventoryCountSerializer(serializers.ModelSerializer):
    items = InventoryCountItemSerializer(many=True, required=False)
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = InventoryCount
        fields = [
            'id', 'number', 'period_type', 'location', 'location_name', 'status', 'notes',
            'created_by', 'created_at', 'submitted_by', 'submitted_at', 'validated_at', 'items',
        ]
        read_only_fields = [
            'id', 'status', 'created_by', 'created_at', 'submitted_by', 'submitted_at', 'validated_at',
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        return fields

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('items', None)
        request = self.context.get('request')
        created_by = validated_data.pop('created_by', None)
        count = InventoryCount.objects.create(
            created_by=request.user if request else created_by,
            **validated_data,
        )
        for product in tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            request.user if request else None,
        ):
            stock, _ = StockItem.objects.get_or_create(product=product, location=count.location)
            InventoryCountItem.objects.create(
                inventory_count=count,
                product=product,
                theoretical_quantity=stock.quantity,
                counted_quantity=stock.quantity,
            )
        return count

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        if instance.status != 'draft' and (items_data is not None or validated_data):
            raise serializers.ValidationError({'items': 'Un inventaire soumis ne peut plus être modifié.'})
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            for item_data in items_data:
                item_id = item_data.get('id')
                try:
                    item = instance.items.get(pk=item_id)
                except InventoryCountItem.DoesNotExist as exc:
                    raise serializers.ValidationError({'items': 'Ligne d’inventaire inconnue.'}) from exc
                item.counted_quantity = item_data['counted_quantity']
                item.save(update_fields=['counted_quantity'])
        return instance
