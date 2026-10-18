from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from core.tenancy import tenant_for_user, tenant_scoped_queryset
from finance.models import FinancialAccount, FinancialTransaction
from products.models import Product
from sales.models import Sale, SaleItem
from sales.serializers import SaleSerializer
from suppliers.models import Supplier

from .models import (
    ExternalPurchase,
    ExternalPurchaseMovement,
    ExternalPurchasePayment,
    ExternalPurchasePaymentAllocation,
)


class ExternalSalePurchaseLineSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        required=False,
        allow_null=True,
    )
    item_name = serializers.CharField(max_length=220, required=False, allow_blank=True)
    item_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    purchase_quantity = serializers.IntegerField(min_value=1, required=False)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    additional_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0'),
        required=False,
        default=Decimal('0'),
    )
    purchase_date = serializers.DateTimeField(required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    delivery_mode = serializers.ChoiceField(choices=ExternalPurchase.DELIVERY_MODES)
    proof_reference = serializers.CharField(max_length=255, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        product = attrs.get('product')
        item_name = attrs.get('item_name', '').strip()
        if product is None and not item_name:
            raise serializers.ValidationError({
                'item_name': 'Indiquez la désignation de l’article hors catalogue.',
            })
        attrs['item_name'] = product.name if product else item_name
        attrs['item_reference'] = (
            product.sku if product else attrs.get('item_reference', '').strip()
        )
        purchase_quantity = attrs.get('purchase_quantity', attrs['quantity'])
        if purchase_quantity > attrs['quantity']:
            raise serializers.ValidationError({
                'purchase_quantity': 'La quantité achetée ne peut pas dépasser la quantité vendue.',
            })
        attrs['purchase_quantity'] = purchase_quantity
        return attrs


class ExternalSalePurchaseCreateSerializer(serializers.Serializer):
    customer = serializers.IntegerField(required=False, allow_null=True)
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    sale_payment_method = serializers.ChoiceField(
        choices=Sale.PAYMENT_CHOICES,
        default='cash',
    )
    sale_amount_paid = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0'),
        required=False,
        default=Decimal('0'),
    )
    financial_account = serializers.PrimaryKeyRelatedField(
        queryset=FinancialAccount.objects.all(),
        required=False,
        allow_null=True,
    )
    discount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0'),
        required=False,
        default=Decimal('0'),
    )
    external_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    sale_notes = serializers.CharField(required=False, allow_blank=True)
    items = ExternalSalePurchaseLineSerializer(many=True, allow_empty=False)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            fields['supplier'].queryset = tenant_scoped_queryset(
                Supplier.objects.all(),
                user,
            )
            fields['financial_account'].queryset = tenant_scoped_queryset(
                FinancialAccount.objects.all(),
                user,
            )
        return fields

    def validate(self, attrs):
        tenant = tenant_for_user(self.context['request'].user)
        if tenant is None:
            raise serializers.ValidationError({
                'tenant': 'Votre compte doit être rattaché à une entreprise.',
            })
        supplier = attrs['supplier']
        if supplier.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'supplier': 'Le commerçant doit appartenir à votre entreprise.',
            })
        items = attrs['items']
        subtotal = sum(
            (item['quantity'] * item['unit_price'] for item in items),
            Decimal('0'),
        )
        discount = attrs.get('discount', Decimal('0'))
        if discount > subtotal:
            raise serializers.ValidationError({
                'discount': 'La remise ne peut pas dépasser le total de la vente.',
            })
        amount_due = subtotal - discount
        if attrs['sale_amount_paid'] > amount_due:
            raise serializers.ValidationError({
                'sale_amount_paid': 'Le paiement client dépasse le montant de la vente.',
            })
        if attrs['sale_amount_paid'] and attrs.get('financial_account') is None:
            raise serializers.ValidationError({
                'financial_account': 'Un compte de trésorerie est requis si le client paie.',
            })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        tenant = tenant_for_user(request.user)
        if tenant is None:
            raise serializers.ValidationError({
                'tenant': 'Votre compte doit être rattaché à une entreprise.',
            })
        supplier = validated_data['supplier']
        line_data = validated_data['items']
        sale_items = [
            {
                'product': line['product'].pk if line.get('product') is not None else None,
                'item_name': line['item_name'],
                'item_reference': line['item_reference'],
                'quantity': line['quantity'],
                'unit_price': line['unit_price'],
            }
            for line in line_data
        ]
        subtotal = sum(
            (item['quantity'] * item['unit_price'] for item in sale_items),
            Decimal('0'),
        )
        sale_amount_paid = validated_data['sale_amount_paid']
        total = subtotal - validated_data.get('discount', Decimal('0'))
        financial_account = validated_data.get('financial_account')
        sale_data = {
            'customer': validated_data.get('customer'),
            'payment_method': validated_data['sale_payment_method'],
            'financial_account': financial_account.pk if financial_account else None,
            'amount_paid': sale_amount_paid,
            'status': 'paid' if sale_amount_paid == total else 'partial',
            'discount': validated_data.get('discount', Decimal('0')),
            'is_external': True,
            'external_supplier': supplier.pk,
            'external_reference': validated_data.get('external_reference', ''),
            'notes': validated_data.get('sale_notes', ''),
            'items': sale_items,
        }
        sale_serializer = SaleSerializer(
            data=sale_data,
            context=self.context,
        )
        sale_serializer.is_valid(raise_exception=True)
        saved_sale = sale_serializer.save()
        if not isinstance(saved_sale, Sale):
            raise serializers.ValidationError('La facture externe n’a pas été créée correctement.')
        sale = saved_sale
        created_items = list(SaleItem.objects.filter(sale=sale).order_by('id'))
        purchases = []
        for source, sale_item in zip(line_data, created_items, strict=True):
            purchase = ExternalPurchase.objects.create(
                tenant=tenant,
                supplier=supplier,
                sale=sale,
                sale_item=sale_item,
                reference=f'EXT-{uuid4().hex[:12].upper()}',
                item_name=source['item_name'],
                item_reference=source['item_reference'],
                quantity=source['purchase_quantity'],
                unit_cost=source['unit_cost'],
                additional_cost=source['additional_cost'],
                purchase_date=source.get('purchase_date', timezone.now()),
                due_date=source.get('due_date'),
                delivery_mode=source['delivery_mode'],
                proof_reference=source.get('proof_reference', ''),
                notes=source.get('notes', ''),
                created_by=request.user,
            )
            if purchase.quantity == sale_item.quantity:
                sale_item.cost_total = purchase.total_cost
                sale_item.save(update_fields=['cost_total'])
            purchases.append(purchase)
        return sale, purchases


class ExternalPurchaseSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    sale_invoice = serializers.CharField(source='sale.invoice.invoice_number', read_only=True)
    sale_item_name = serializers.SerializerMethodField()
    total_cost = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    received_quantity = serializers.SerializerMethodField()
    delivered_quantity = serializers.SerializerMethodField()

    class Meta:
        model = ExternalPurchase
        fields = [
            'id', 'reference', 'supplier', 'supplier_name', 'sale', 'sale_invoice',
            'sale_item', 'sale_item_name', 'item_name', 'item_reference', 'quantity',
            'unit_cost', 'additional_cost', 'total_cost', 'total_paid', 'balance_due',
            'payment_status', 'purchase_date', 'due_date', 'delivery_mode', 'status',
            'received_quantity', 'delivered_quantity', 'proof_reference', 'notes',
            'created_by', 'created_at',
        ]

    def get_sale_item_name(self, obj):
        item = obj.sale_item
        return item.product.name if item.product_id else item.item_name

    def get_total_paid(self, obj):
        return getattr(obj, 'calculated_paid', obj.total_paid)

    def get_balance_due(self, obj):
        return max(obj.total_cost - self.get_total_paid(obj), Decimal('0'))

    def get_payment_status(self, obj):
        balance = self.get_balance_due(obj)
        if balance == 0:
            return 'paid'
        return 'partial' if self.get_total_paid(obj) else 'unpaid'

    def get_received_quantity(self, obj):
        return obj.movements.filter(movement_type='received').aggregate(
            total=Sum('quantity'),
        )['total'] or 0

    def get_delivered_quantity(self, obj):
        return obj.movements.filter(
            movement_type__in=['delivered', 'direct_delivery'],
        ).aggregate(total=Sum('quantity'))['total'] or 0


class ExternalPurchasePaymentSerializer(serializers.ModelSerializer):
    allocations = serializers.SerializerMethodField()
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    account_name = serializers.CharField(source='financial_account.name', read_only=True)

    class Meta:
        model = ExternalPurchasePayment
        fields = [
            'id', 'reference', 'supplier', 'supplier_name', 'financial_account',
            'account_name', 'financial_transaction', 'amount', 'payment_method',
            'payment_date', 'proof_reference', 'notes', 'allocations',
            'created_by', 'created_at',
        ]

    def get_allocations(self, obj):
        allocations = obj.allocations.select_related('purchase').all()
        return [
            {
                'purchase': allocation.purchase_id,
                'reference': allocation.purchase.reference,
                'item_name': allocation.purchase.item_name,
                'amount': allocation.amount,
            }
            for allocation in allocations
        ]


class ExternalPurchasePaymentCreateSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    purchase_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        allow_empty=False,
    )
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal('0.01'),
    )
    payment_method = serializers.ChoiceField(
        choices=ExternalPurchasePayment.PAYMENT_METHOD_CHOICES,
    )
    financial_account = serializers.PrimaryKeyRelatedField(
        queryset=FinancialAccount.objects.all(),
    )
    payment_date = serializers.DateTimeField(required=False, default=timezone.now)
    proof_reference = serializers.CharField(max_length=255, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            fields['supplier'].queryset = tenant_scoped_queryset(
                Supplier.objects.all(),
                user,
            )
            fields['financial_account'].queryset = tenant_scoped_queryset(
                FinancialAccount.objects.all(),
                user,
            )
        return fields

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        tenant = tenant_for_user(request.user)
        if tenant is None:
            raise serializers.ValidationError({
                'tenant': 'Votre compte doit être rattaché à une entreprise.',
            })
        supplier = validated_data['supplier']
        account = validated_data['financial_account']
        if account is None:
            raise serializers.ValidationError({
                'financial_account': 'Choisissez un compte actif en GNF.',
            })
        if account.status != 'active' or account.currency != 'GNF':
            raise serializers.ValidationError({
                'financial_account': 'Choisissez un compte actif en GNF.',
            })
        if supplier.tenant_id not in (None, tenant.pk) or account.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'supplier': 'Le commerçant et le compte doivent appartenir à votre entreprise.',
            })
        purchase_ids = validated_data['purchase_ids']
        if len(set(purchase_ids)) != len(purchase_ids):
            raise serializers.ValidationError({
                'purchase_ids': 'Un achat ne peut être sélectionné qu’une seule fois.',
            })
        purchases = list(
            ExternalPurchase.objects.select_for_update()
            .filter(
                pk__in=purchase_ids,
                tenant=tenant,
                supplier=supplier,
                status='confirmed',
            )
            .order_by('purchase_date', 'id')
        )
        if len(purchases) != len(purchase_ids):
            raise serializers.ValidationError({
                'purchase_ids': 'Un ou plusieurs achats sont introuvables pour ce commerçant.',
            })
        balances = {}
        for purchase in purchases:
            paid = ExternalPurchasePaymentAllocation.objects.filter(
                purchase=purchase,
                payment__financial_transaction__status='validated',
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            balances[purchase.pk] = max(purchase.total_cost - paid, Decimal('0'))
        if validated_data['amount'] > sum(balances.values(), Decimal('0')):
            raise serializers.ValidationError({
                'amount': 'Le paiement dépasse le solde dû sur les achats sélectionnés.',
            })

        payment_reference = f'FPP-{uuid4().hex[:12].upper()}'
        payment_date = validated_data['payment_date']
        financial_transaction = FinancialTransaction.objects.create(
            tenant=tenant,
            transaction_date=payment_date,
            transaction_type='payment',
            direction='out',
            amount=validated_data['amount'],
            currency='GNF',
            account=account,
            category='Paiement fournisseur externe',
            description=f'Règlement {payment_reference} — {supplier.name}',
            origin=payment_reference,
            status='validated',
            created_by=request.user,
            validated_by=request.user,
            validated_at=timezone.now(),
        )
        payment = ExternalPurchasePayment.objects.create(
            tenant=tenant,
            supplier=supplier,
            financial_transaction=financial_transaction,
            financial_account=account,
            reference=payment_reference,
            amount=validated_data['amount'],
            payment_method=validated_data['payment_method'],
            payment_date=payment_date,
            proof_reference=validated_data.get('proof_reference', ''),
            notes=validated_data.get('notes', ''),
            created_by=request.user,
        )
        remaining = validated_data['amount']
        for purchase in purchases:
            allocation = min(remaining, balances[purchase.pk])
            if allocation:
                ExternalPurchasePaymentAllocation.objects.create(
                    payment=payment,
                    purchase=purchase,
                    amount=allocation,
                )
                remaining -= allocation
            if not remaining:
                break
        return payment


class ExternalPurchaseMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalPurchaseMovement
        fields = [
            'id', 'purchase', 'location', 'movement_type', 'quantity', 'reference',
            'proof_reference', 'notes', 'occurred_at', 'created_by', 'created_at',
        ]
        read_only_fields = ['id', 'purchase', 'created_by', 'created_at']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['location'].queryset = tenant_scoped_queryset(
                fields['location'].queryset,
                request.user,
            )
        return fields

    def validate(self, attrs):
        purchase = self.context['purchase']
        if purchase.status != 'confirmed':
            raise serializers.ValidationError('Un achat annulé ne peut pas être livré ou réceptionné.')
        movement_type = attrs['movement_type']
        location = attrs.get('location')
        if movement_type == 'direct_delivery':
            if purchase.delivery_mode != 'direct' or location is not None:
                raise serializers.ValidationError(
                    'La livraison directe ne peut pas créer de mouvement d’entrepôt.',
                )
        elif purchase.delivery_mode != 'warehouse' or location is None:
            raise serializers.ValidationError(
                'Une réception ou sortie physique exige un achat en transit et un emplacement.',
            )
        if location and location.tenant_id not in (None, purchase.tenant_id):
            raise serializers.ValidationError({
                'location': 'L’emplacement doit appartenir à votre entreprise.',
            })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        purchase = ExternalPurchase.objects.select_for_update().get(
            pk=self.context['purchase'].pk,
        )
        if purchase.status != 'confirmed':
            raise serializers.ValidationError(
                'Un achat annulé ne peut pas être livré ou réceptionné.',
            )
        movement_type = validated_data['movement_type']
        previous_received = ExternalPurchaseMovement.objects.filter(
            purchase=purchase,
            movement_type='received',
        ).aggregate(total=Sum('quantity'))['total'] or 0
        previous_delivered = ExternalPurchaseMovement.objects.filter(
            purchase=purchase,
            movement_type__in=['delivered', 'direct_delivery'],
        ).aggregate(total=Sum('quantity'))['total'] or 0
        quantity = validated_data['quantity']
        if movement_type == 'received' and previous_received + quantity > purchase.quantity:
            raise serializers.ValidationError({
                'quantity': 'La quantité réceptionnée dépasse la quantité achetée.',
            })
        if movement_type == 'delivered':
            if previous_delivered + quantity > previous_received:
                raise serializers.ValidationError({
                    'quantity': 'La sortie dépasse la quantité réellement réceptionnée.',
                })
        elif movement_type == 'direct_delivery' and previous_delivered + quantity > purchase.quantity:
            raise serializers.ValidationError({
                'quantity': 'La livraison dépasse la quantité achetée.',
            })
        return ExternalPurchaseMovement.objects.create(
            purchase=purchase,
            created_by=self.context['request'].user,
            **validated_data,
        )
