from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from rest_framework import serializers

from core.models import AuditLog
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from customers.models import Customer
from finance.models import FinancialAccount
from invoices.branding import get_tenant_invoice_company_name
from purchases.models import ExternalPurchase
from suppliers.models import Supplier
from inventory.costing import consume_fifo_cartons, consume_fifo_cost_with_layers, record_cost_layer
from inventory.models import (
    Carton,
    InventoryCostLayer,
    InventoryLocation,
    StockItem,
    StockMovement,
)
from products.models import Product

from .models import (
    CustomerOrder,
    CustomerOrderItem,
    Invoice,
    Sale,
    SaleItem,
    SaleItemCostAllocation,
    SaleItemStockOrigin,
    SaleItemTrackedUnit,
    SaleReturn,
    SaleReturnCostAllocation,
    SaleReturnItem,
    SaleReturnQuarantine,
)
from .reservations import reserved_quantity
from .utils import sales_locations_for_user


class SaleCatalogSerializer(serializers.ModelSerializer):
    quantity = serializers.SerializerMethodField()
    stock_by_location = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'alternative_references', 'brand', 'vehicle',
            'category', 'selling_price', 'quantity', 'stock_by_location', 'is_active',
        ]

    def get_quantity(self, obj):
        request = self.context.get('request')
        if (
            request
            and request.user.is_authenticated
            and request.user.has_role('sales')
            and not request.user.has_role('admin')
        ):
            stock_items = getattr(obj, 'sale_catalog_stock_items', [])
            if not stock_items:
                return 0
            return sum(
                max(
                    stock_item.quantity - reserved_quantity(
                        product_id=obj.pk,
                        location_id=stock_item.location_id,
                    ),
                    0,
                )
                for stock_item in stock_items
            )
        return obj.quantity

    def get_stock_by_location(self, obj):
        stock_items = getattr(obj, 'sale_catalog_stock_items', [])
        return [
            {
                'location_id': stock_item.location_id,
                'location': stock_item.location.name,
                'quantity': max(
                    stock_item.quantity - reserved_quantity(
                        product_id=obj.pk,
                        location_id=stock_item.location_id,
                    ),
                    0,
                ),
            }
            for stock_item in stock_items
        ]


class SaleLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryLocation
        fields = ['id', 'name', 'location_type']


class SaleExternalSupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name']


class SaleExternalPurchaseSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    unit_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0'),
    )
    additional_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0'),
        required=False,
        default=Decimal('0'),
    )
    delivery_mode = serializers.ChoiceField(choices=ExternalPurchase.DELIVERY_MODES)
    payment_terms = serializers.ChoiceField(choices=['immediate', 'deferred'])
    due_date = serializers.DateField(required=False, allow_null=True)
    proof_reference = serializers.CharField(max_length=255, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['supplier'].queryset = tenant_scoped_queryset(
                Supplier.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        today = timezone.localdate()
        if attrs['payment_terms'] == 'immediate':
            attrs['due_date'] = today
        elif attrs.get('due_date') is None or attrs['due_date'] <= today:
            raise serializers.ValidationError({
                'due_date': 'Une échéance future est obligatoire pour un paiement différé.',
            })
        attrs.pop('payment_terms')
        return attrs


class SaleItemSerializer(serializers.ModelSerializer):
    total_price = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    product_sku = serializers.SerializerMethodField()
    product_cost = serializers.SerializerMethodField()
    stock_origins = serializers.SerializerMethodField()
    tracked_unit_references = serializers.SerializerMethodField()
    stock_removed_quantity = serializers.SerializerMethodField()
    external_purchase = SaleExternalPurchaseSerializer(write_only=True, required=False)

    class Meta:
        model = SaleItem
        fields = [
            'id', 'product', 'item_name', 'item_reference', 'product_name', 'product_sku', 'product_cost', 'quantity',
            'unit_price', 'total_price', 'stock_origins', 'tracked_unit_references',
            'stock_removed_quantity', 'external_purchase',
        ]
        read_only_fields = ['id', 'total_price']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
        return fields

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
            and request.user.has_role('sales')
            and not request.user.has_role('admin')
        ):
            fields.pop('product_cost')
        return fields

    def get_total_price(self, obj):
        return obj.total_price

    def get_product_name(self, obj):
        return obj.product.name if obj.product_id else obj.item_name

    def get_product_sku(self, obj):
        return obj.product.sku if obj.product_id else obj.item_reference

    def get_product_cost(self, obj):
        return obj.product.cost_price if obj.product_id else None

    def get_stock_origins(self, obj):
        origins = getattr(obj, '_prefetched_objects_cache', {}).get('stock_origins')
        if origins is None:
            origins = obj.stock_origins.select_related('carton', 'location').all()
        if not origins:
            if not obj.product_id:
                return []
            return [{
                'source_type': 'historical_unknown',
                'reference': 'ORIGINE-HISTORIQUE-INCONNUE',
                'quantity': obj.quantity,
                'carton_reference': None,
                'location': obj.sale.location.name if obj.sale.location_id else None,
                'supplier': None,
            }]
        return [
            {
                'source_type': origin.source_type,
                'reference': origin.reference,
                'quantity': origin.quantity,
                'carton_reference': origin.carton.reference if origin.carton_id else None,
                'location': origin.location.name if origin.location_id else None,
                'supplier': (
                    obj.sale.external_supplier.name
                    if origin.source_type == 'external_supplier' and obj.sale.external_supplier_id
                    else None
                ),
            }
            for origin in origins
        ]

    def get_tracked_unit_references(self, obj):
        allocations = getattr(obj, '_prefetched_objects_cache', {}).get('tracked_unit_allocations')
        if allocations is None:
            allocations = obj.tracked_unit_allocations.select_related('stock_unit__carton').all()
        return [
            {
                'reference': allocation.stock_unit.reference,
                'carton_reference': allocation.stock_unit.carton.reference,
            }
            for allocation in allocations
        ]

    def get_stock_removed_quantity(self, obj):
        return 0 if obj.sale.is_external or not obj.product_id else obj.quantity


class CustomerOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_reference = serializers.CharField(source='product.sku', read_only=True)
    total_price = serializers.SerializerMethodField()
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0'),
    )

    class Meta:
        model = CustomerOrderItem
        fields = [
            'id', 'product', 'product_name', 'product_reference',
            'quantity', 'unit_price', 'total_price',
        ]
        read_only_fields = ['id', 'product_name', 'product_reference', 'total_price']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['product'].queryset = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            )
        return fields

    def get_total_price(self, obj):
        return obj.total_price


class CustomerOrderSerializer(serializers.ModelSerializer):
    items = CustomerOrderItemSerializer(many=True)
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    sale_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = CustomerOrder
        fields = [
            'id', 'reference', 'customer', 'customer_name', 'location', 'location_name',
            'created_by', 'created_by_name', 'status', 'discount', 'total_amount',
            'notes', 'sale_id', 'items', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reference', 'created_by', 'created_by_name', 'status', 'total_amount',
            'sale_id', 'created_at', 'updated_at',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else ''

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['customer'].queryset = tenant_scoped_queryset(
                Customer.objects.all(),
                request.user,
            )
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        items = attrs.get('items', [])
        if not items:
            raise serializers.ValidationError({'items': 'Un devis doit contenir au moins un article.'})

        customer = attrs.get('customer')
        if customer and not customer.is_active:
            raise serializers.ValidationError({'customer': 'Choisissez un client actif.'})
        location = attrs.get('location')
        request = self.context.get('request')
        tenant = tenant_for_user(request.user) if request else None
        if tenant is None:
            raise serializers.ValidationError({
                'tenant': 'Votre compte doit être rattaché à un espace d’entreprise.',
            })
        if customer and customer.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'customer': 'Le client doit appartenir à votre entreprise.',
            })
        if location and location.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'location': 'La boutique doit appartenir à votre entreprise.',
            })
        if any(item['product'].tenant_id not in (None, tenant.pk) for item in items):
            raise serializers.ValidationError({
                'items': 'Tous les produits doivent appartenir à votre entreprise.',
            })
        if not location or location.location_type != 'shop' or not location.is_active:
            raise serializers.ValidationError({
                'location': 'Le devis doit être rattaché à une boutique active.',
            })
        if (
            request
            and request.user.has_role('sales')
            and not request.user.has_role('admin')
            and not sales_locations_for_user(request.user).filter(pk=location.pk).exists()
        ):
            raise serializers.ValidationError({
                'location': 'Vous n’êtes pas autorisé à créer un devis pour cette boutique.',
            })

        seen_product_ids = set()
        subtotal = Decimal('0.00')
        for item in items:
            product = item['product']
            if not product.is_active:
                raise serializers.ValidationError({'items': f'{product.name} est inactif.'})
            if product.pk in seen_product_ids:
                raise serializers.ValidationError({
                    'items': 'Chaque produit doit apparaître une seule fois dans le devis.',
                })
            seen_product_ids.add(product.pk)
            if (
                request
                and request.user.has_role('sales')
                and not request.user.has_role('admin')
                and item['unit_price'] != product.selling_price
            ):
                raise serializers.ValidationError({
                    'items': f'Le prix de {product.name} doit correspondre au prix catalogue.',
                })
            subtotal += item['quantity'] * item['unit_price']

        discount = attrs.get('discount', Decimal('0.00'))
        if discount < 0 or discount > subtotal:
            raise serializers.ValidationError({
                'discount': 'La remise doit être comprise entre zéro et le sous-total.',
            })
        if request and request.user.has_role('sales') and not request.user.has_role('admin') and discount:
            raise serializers.ValidationError({'discount': 'La remise est réservée aux utilisateurs autorisés.'})
        attrs['total_amount'] = subtotal - discount
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop('items')
        total_amount = validated_data.pop('total_amount')
        request = self.context.get('request')
        order = CustomerOrder.objects.create(
            **validated_data,
            tenant=tenant_for_user(request.user) if request else None,
            created_by=request.user if request else None,
            total_amount=total_amount,
        )
        CustomerOrderItem.objects.bulk_create([
            CustomerOrderItem(order=order, **item)
            for item in items
        ])
        AuditLog.objects.create(
            user=request.user if request else None,
            action='customer_order',
            model_name='CustomerOrder',
            record_id=order.id,
            details=f'Devis {order.reference} créé sans réservation de stock.',
        )
        return order


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    total_amount = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()
    invoice_qr_code = serializers.SerializerMethodField()
    seller = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all(), required=False, allow_null=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    seller_name = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = ['id', 'customer', 'customer_name', 'seller', 'seller_name', 'location', 'sale_date', 'status', 'payment_method', 'financial_account', 'total_amount', 'discount', 'amount_paid', 'is_external', 'external_supplier', 'external_reference', 'notes', 'items', 'invoice_number', 'invoice_qr_code', 'created_at', 'updated_at']
        read_only_fields = ['id', 'sale_date', 'created_at', 'updated_at', 'total_amount', 'invoice_number', 'invoice_qr_code']

    def get_total_amount(self, obj):
        return obj.total_amount

    def get_seller_name(self, obj):
        return obj.seller.get_full_name() if obj.seller else ''

    def get_invoice_number(self, obj):
        invoice = getattr(obj, 'invoice', None)
        return invoice.invoice_number if invoice else None

    def get_invoice_qr_code(self, obj):
        invoice = getattr(obj, 'invoice', None)
        return invoice.qr_code if invoice else None

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['customer'].queryset = tenant_scoped_queryset(
                Customer.objects.all(),
                request.user,
            )
            fields['seller'].queryset = tenant_scoped_queryset(
                get_user_model().objects.all(),
                request.user,
            )
            fields['location'].queryset = tenant_scoped_queryset(
                InventoryLocation.objects.all(),
                request.user,
            )
            fields['external_supplier'].queryset = tenant_scoped_queryset(
                Supplier.objects.all(),
                request.user,
            )
            fields['financial_account'].queryset = tenant_scoped_queryset(
                FinancialAccount.objects.all(),
                request.user,
            )
        return fields

    def validate(self, attrs):
        items = attrs.get('items', [])
        customer = attrs.get('customer', getattr(self.instance, 'customer', None))
        payment_method = attrs.get('payment_method', getattr(self.instance, 'payment_method', None))
        request = self.context.get('request')
        is_sales_user = (
            request
            and request.user.has_role('sales')
            and not request.user.has_role('admin')
        )
        location = attrs.get('location', getattr(self.instance, 'location', None))
        is_external = attrs.get('is_external', getattr(self.instance, 'is_external', False))
        tenant = tenant_for_user(request.user) if request else None
        if tenant is None:
            raise serializers.ValidationError({
                'tenant': 'Votre compte doit être rattaché à un espace d’entreprise.',
            })
        if customer and customer.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'customer': 'Le client doit appartenir à votre entreprise.',
            })
        if location and location.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'location': 'La boutique doit appartenir à votre entreprise.',
            })
        seller = attrs.get('seller', getattr(self.instance, 'seller', None))
        if seller and seller.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'seller': 'Le vendeur doit appartenir à votre entreprise.',
            })
        external_supplier = attrs.get(
            'external_supplier',
            getattr(self.instance, 'external_supplier', None),
        )
        if external_supplier and external_supplier.tenant_id not in (None, tenant.pk):
            raise serializers.ValidationError({
                'external_supplier': 'Le fournisseur doit appartenir à votre entreprise.',
            })
        if any(
            item.get('product')
            and item['product'].tenant_id not in (None, tenant.pk)
            for item in items
        ):
            raise serializers.ValidationError({
                'items': 'Tous les produits doivent appartenir à votre entreprise.',
            })
        if any(
            item.get('external_purchase')
            and item['external_purchase']['supplier'].tenant_id not in (None, tenant.pk)
            for item in items
        ):
            raise serializers.ValidationError({
                'items': 'Tous les commerçants doivent appartenir à votre entreprise.',
            })
        if not items:
            raise serializers.ValidationError({'items': 'Une vente doit contenir au moins un article.'})
        if any(
            not item.get('product')
            and not str(item.get('item_name', '')).strip()
            for item in items
        ):
            raise serializers.ValidationError({
                'items': 'Un article hors catalogue exige une désignation.',
            })
        if is_external and self.instance is not None and not self.instance.is_external:
            raise serializers.ValidationError({
                'is_external': 'Une vente de stock interne ne peut pas être convertie en vente externe.',
            })
        if is_sales_user and (attrs.get('discount', 0) or 0) > 0:
            raise serializers.ValidationError(
                {'discount': 'La remise est réservée aux utilisateurs autorisés.'}
            )
        if is_external and location is not None:
            raise serializers.ValidationError({
                'location': 'Une vente externe ne doit pas utiliser le stock interne d’une boutique.',
            })
        if self.instance is None and not is_external and location is None:
            raise serializers.ValidationError(
                {'location': 'Une boutique est obligatoire pour une vente de stock.'}
            )
        if location and not is_external and (
            location.location_type != 'shop' or not location.is_active
        ):
            raise serializers.ValidationError(
                {'location': 'Une vente de stock doit être effectuée depuis une boutique active.'}
            )
        if is_sales_user and location and not sales_locations_for_user(request.user).filter(
            pk=location.pk,
        ).exists():
            raise serializers.ValidationError(
                {'location': 'Vous n’êtes pas autorisé à vendre depuis cet emplacement.'}
            )
        if payment_method == 'credit' and customer is None:
            raise serializers.ValidationError({'customer': 'Un client identifié est obligatoire pour une vente à crédit.'})
        if payment_method == 'credit' and not customer.phone:
            raise serializers.ValidationError({'customer': 'Un numéro WhatsApp est obligatoire pour les rappels de crédit.'})
        if attrs.get('is_external') and not attrs.get('external_supplier'):
            raise serializers.ValidationError({'external_supplier': 'Le fournisseur est obligatoire pour une vente externe.'})

        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        discount = attrs.get('discount', 0) or 0
        if discount < 0 or discount > subtotal:
            raise serializers.ValidationError({'discount': 'La remise doit être comprise entre zéro et le sous-total.'})
        total_amount = subtotal - discount
        amount_paid = attrs.get('amount_paid', 0) or 0
        if amount_paid < 0 or amount_paid > total_amount:
            raise serializers.ValidationError({'amount_paid': 'Le montant payé doit être compris entre zéro et le total de la vente.'})

        for item_data in items:
            product = item_data.get('product')
            quantity = item_data.get('quantity', 0)
            if product and not is_external and not item_data.get('external_purchase') and location:
                stock_item = StockItem.objects.filter(product=product, location=location).first()
                available_quantity = (
                    stock_item.quantity - reserved_quantity(
                        product_id=product.pk,
                        location_id=location.pk,
                        exclude_order_id=self.context.get('customer_order_id'),
                    )
                    if stock_item else 0
                )
                if stock_item is None or quantity > available_quantity:
                    raise serializers.ValidationError(
                        {'quantity': f'Le stock disponible de {product.name} est insuffisant dans cette boutique.'}
                    )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        requested_amount_paid = validated_data.get('amount_paid', 0) or 0

        request = self.context.get('request')
        if validated_data.get('customer') is None:
            validated_data['customer'], _ = Customer.objects.get_or_create(
                tenant=tenant_for_user(request.user) if request else None,
                full_name='Client comptoir',
                phone='',
                defaults={'is_active': True},
            )
        if (
            request
            and getattr(request, 'user', None)
            and request.user.has_role('sales')
        ):
            validated_data['seller'] = request.user
        elif request and getattr(request, 'user', None) and validated_data.get('seller') is None:
            validated_data['seller'] = request.user

        product_ids = sorted({
            item_data['product'].pk
            for item_data in items_data
            if item_data.get('product')
        })
        locked_products = {
            product.pk: product
            for product in Product.objects.select_for_update()
            .filter(pk__in=product_ids)
            .order_by('pk')
        }
        location = validated_data.get('location')
        if not validated_data.get('is_external', False):
            location = (
                InventoryLocation.objects.select_for_update()
                .filter(pk=getattr(location, 'pk', None), location_type='shop', is_active=True)
                .first()
            )
            if location is None:
                raise serializers.ValidationError(
                    {'location': 'La boutique est introuvable ou inactive.'}
                )
            if request and not request.user.has_role('admin') and not sales_locations_for_user(
                request.user,
            ).filter(pk=location.pk).exists():
                raise serializers.ValidationError(
                    {'location': 'Vous n’êtes pas autorisé à vendre depuis cette boutique.'}
                )
        tenant = tenant_for_user(request.user) if request else None
        sale = Sale.objects.create(
            **validated_data,
            tenant=tenant,
        )

        for item_data in items_data:
            external_purchase_data = item_data.pop('external_purchase', None)
            product = (
                locked_products[item_data['product'].pk]
                if item_data.get('product')
                else None
            )
            if (
                product
                and
                request
                and request.user.has_role('sales')
                and not request.user.has_role('admin')
                and item_data['unit_price'] != product.selling_price
            ):
                raise serializers.ValidationError(
                    {'unit_price': f'Le prix de {product.name} a changé. Actualisez le catalogue.'}
                )
            if product:
                item_data['product'] = product
                item_data.setdefault('item_name', product.name)
                item_data.setdefault('item_reference', product.sku)
            else:
                item_data['item_name'] = str(item_data['item_name']).strip()
                item_data['item_reference'] = str(
                    item_data.get('item_reference', ''),
                ).strip()
            item = SaleItem.objects.create(sale=sale, **item_data)
            if external_purchase_data:
                purchase = ExternalPurchase.objects.create(
                    tenant=sale.tenant,
                    supplier=external_purchase_data['supplier'],
                    sale=sale,
                    sale_item=item,
                    reference=f'EXT-{uuid4().hex[:12].upper()}',
                    item_name=item.product.name if item.product_id else item.item_name,
                    item_reference=item.product.sku if item.product_id else item.item_reference,
                    quantity=item.quantity,
                    unit_cost=external_purchase_data['unit_cost'],
                    additional_cost=external_purchase_data['additional_cost'],
                    purchase_date=timezone.now(),
                    due_date=external_purchase_data['due_date'],
                    delivery_mode=external_purchase_data['delivery_mode'],
                    proof_reference=external_purchase_data.get('proof_reference', ''),
                    notes=external_purchase_data.get('notes', ''),
                    created_by=getattr(request, 'user', None) if request else None,
                )
                item.cost_total = purchase.total_cost
                item.save(update_fields=['cost_total'])
                SaleItemStockOrigin.objects.create(
                    sale_item=item,
                    source_type='external_supplier',
                    reference=purchase.reference,
                    quantity=item.quantity,
                )
            elif product and not sale.is_external:
                stock_item = StockItem.objects.select_for_update().filter(
                    product=product,
                    location_id=sale.location_id,
                ).first()
                if stock_item is None or stock_item.quantity < item.quantity:
                    raise serializers.ValidationError({'quantity': f'Le stock de {product.name} est insuffisant dans cet emplacement.'})
                available_quantity = stock_item.quantity - reserved_quantity(
                    product_id=product.pk,
                    location_id=sale.location_id,
                    exclude_order_id=self.context.get('customer_order_id'),
                )
                if available_quantity < item.quantity:
                    raise serializers.ValidationError({
                        'quantity': f'Le stock disponible de {product.name} est réservé à une autre commande.',
                    })
                stock_item.quantity -= item.quantity
                stock_item.save(update_fields=['quantity', 'updated_at'])
                consumed_cartons = consume_fifo_cartons(
                    product=product,
                    quantity=item.quantity,
                    location=sale.location,
                    sale_item=item,
                )
                carton_details = ', '.join(
                    f'{carton.reference} x {quantity}'
                    for carton, quantity in consumed_cartons
                )
                tracked_quantity = sum(quantity for _, quantity in consumed_cartons)
                for carton, origin_quantity in consumed_cartons:
                    SaleItemStockOrigin.objects.create(
                        sale_item=item,
                        source_type='carton',
                        carton=carton,
                        location=sale.location,
                        reference=carton.reference,
                        quantity=origin_quantity,
                    )
                untracked_quantity = item.quantity - tracked_quantity
                if untracked_quantity:
                    SaleItemStockOrigin.objects.create(
                        sale_item=item,
                        source_type='historical_unknown',
                        location=sale.location,
                        reference='STOCK-HISTORIQUE-NON-TRACE',
                        quantity=untracked_quantity,
                    )
                StockMovement.objects.create(
                    product=product,
                    location=sale.location,
                    movement_type='out',
                    quantity=item.quantity,
                    reference=f'SALE-{sale.id}',
                    notes=(
                        f'Vente {sale.id}.'
                        + (f' Cartons consommés: {carton_details}.' if carton_details else '')
                    ),
                    created_by=getattr(request, 'user', None) if request else None,
                )
                if product.quantity < item.quantity:
                    raise serializers.ValidationError({'quantity': f'Le stock de {product.name} est insuffisant.'})
                product.quantity -= item.quantity
                product.save(update_fields=['quantity'])
                item.cost_total, consumed_layers = consume_fifo_cost_with_layers(
                    product=product,
                    quantity=item.quantity,
                    location=sale.location,
                )
                SaleItemCostAllocation.objects.bulk_create([
                    SaleItemCostAllocation(
                        sale_item=item,
                        cost_layer=layer,
                        quantity=quantity,
                        unit_cost=layer.unit_cost,
                    )
                    for layer, quantity in consumed_layers
                ])
                item.save(update_fields=['cost_total'])
            elif sale.is_external:
                supplier_reference = sale.external_reference or f'SUPPLIER-{sale.external_supplier_id}'
                SaleItemStockOrigin.objects.create(
                    sale_item=item,
                    source_type='external_supplier',
                    reference=supplier_reference,
                    quantity=item.quantity,
                )

        sale.total_amount = sum(item.total_price for item in sale.items.all()) - sale.discount
        sale.amount_paid = sale.total_amount if sale.status == 'paid' else requested_amount_paid
        sale.save(update_fields=['total_amount', 'amount_paid'])

        invoice = Invoice.objects.create(
            sale=sale,
            company_name=get_tenant_invoice_company_name(tenant),
            total_amount=sale.total_amount,
            paid_amount=sale.amount_paid,
            status='validated' if sale.status != 'cancelled' else 'cancelled',
            validated_by=getattr(request, 'user', None) if request else None,
        )
        invoice.generate_qr_code()
        invoice.save(update_fields=['qr_code'])

        from payments.models import CreditLedger, Payment, PaymentAllocation
        from payments.serializers import PaymentSerializer

        if sale.amount_paid > 0:
            payment = Payment.objects.create(
                customer=sale.customer,
                sale=sale,
                amount=sale.amount_paid,
                payment_method=sale.payment_method,
                financial_account=sale.financial_account,
                reference=f'PAY-SALE-{sale.id:06d}',
                notes='Paiement généré automatiquement lors de la vente',
                created_by=getattr(request, 'user', None) if request else None,
            )
            PaymentSerializer.sync_financial_transaction(payment, getattr(request, 'user', None) if request else None)
            PaymentAllocation.objects.create(
                payment=payment,
                sale=sale,
                amount=payment.amount,
            )
            PaymentSerializer.sync_sale_payment(sale)

        if sale.total_amount > sale.amount_paid:
            ledger, _ = CreditLedger.objects.get_or_create(
                customer=sale.customer,
                sale=sale,
                defaults={'total_credit': sale.total_amount, 'total_paid': sale.amount_paid},
            )
            ledger.total_credit = sale.total_amount
            ledger.total_paid = sale.amount_paid
            ledger.update_balance()

        from invoices.rendering import build_invoice_snapshot

        invoice.document_snapshot = build_invoice_snapshot(invoice)
        invoice.save(update_fields=['document_snapshot'])

        request = self.context.get('request')
        AuditLog.objects.create(
            user=getattr(request, 'user', None) if request else None,
            action='sale',
            model_name='Sale',
            record_id=sale.id,
            details=f'Vente créée: {sale.id}, total={sale.total_amount}',
        )
        return sale


class SaleReturnItemInputSerializer(serializers.Serializer):
    sale_item = serializers.PrimaryKeyRelatedField(queryset=SaleItem.objects.all())
    quantity = serializers.IntegerField(min_value=1)
    restock_quantity = serializers.IntegerField(min_value=0, write_only=True)
    quarantined_quantity = serializers.IntegerField(min_value=0, write_only=True)
    quarantine_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        write_only=True,
    )


class SaleReturnSerializer(serializers.ModelSerializer):
    sale_id = serializers.IntegerField(read_only=True)
    items = SaleReturnItemInputSerializer(many=True)
    returned_amount = serializers.SerializerMethodField()

    class Meta:
        model = SaleReturn
        fields = ['id', 'sale_id', 'reason', 'created_by', 'created_at', 'returned_amount', 'items']
        read_only_fields = ['id', 'sale_id', 'created_by', 'created_at', 'returned_amount']

    def get_returned_amount(self, obj):
        return sum((item.revenue_total for item in obj.items.all()), Decimal('0.00'))

    def validate(self, attrs):
        sale = self.context['sale']
        if sale.status in {'draft', 'cancelled'}:
            raise serializers.ValidationError({'sale': 'Seules les ventes validées peuvent être retournées.'})

        items = attrs.get('items', [])
        if not items:
            raise serializers.ValidationError({'items': 'Ajoutez au moins un article retourné.'})

        sale_item_ids = set(sale.items.values_list('id', flat=True))
        submitted_ids = set()
        for item_data in items:
            sale_item = item_data['sale_item']
            if sale_item.id not in sale_item_ids:
                raise serializers.ValidationError({'items': 'Un article ne correspond pas à cette vente.'})
            if sale_item.id in submitted_ids:
                raise serializers.ValidationError({'items': 'Chaque article doit apparaître une seule fois.'})
            if (
                item_data['restock_quantity'] + item_data['quarantined_quantity']
                != item_data['quantity']
            ):
                raise serializers.ValidationError({
                    'items': 'Les quantités remises en stock et isolées doivent correspondre au retour.',
                })
            if item_data['quarantined_quantity'] and not item_data['quarantine_reason'].strip():
                raise serializers.ValidationError({
                    'items': 'Un motif est obligatoire pour isoler un article retourné.',
                })
            if item_data['quarantined_quantity'] and sale.location_id is None:
                raise serializers.ValidationError({
                    'items': 'Le lieu de vente est requis pour tracer les articles isolés.',
                })
            if sale.is_external and (
                item_data['restock_quantity'] or item_data['quarantined_quantity']
            ):
                raise serializers.ValidationError({
                    'items': 'Un retour externe ne peut pas modifier le stock interne sans réception dédiée.',
                })
            submitted_ids.add(sale_item.id)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        sale = self.context['sale']
        request = self.context['request']
        return_record = SaleReturn.objects.create(
            sale=sale,
            created_by=request.user,
            reason=validated_data.get('reason', ''),
        )

        for submitted_item in validated_data['items']:
            sale_item = SaleItem.objects.select_for_update().select_related('product').get(
                pk=submitted_item['sale_item'].pk,
            )
            quantity = submitted_item['quantity']
            restock_quantity = submitted_item['restock_quantity']
            quarantined_quantity = submitted_item['quarantined_quantity']
            returned_so_far = SaleReturnItem.objects.filter(sale_item=sale_item).aggregate(
                quantity=Sum('quantity'),
                revenue=Sum('revenue_total'),
            )
            previous_quantity = returned_so_far['quantity'] or 0
            if previous_quantity + quantity > sale_item.quantity:
                raise serializers.ValidationError({
                    'items': (
                        'La quantité retournée dépasse la quantité vendue pour '
                        f'{sale_item.product.name if sale_item.product_id else sale_item.item_name}.'
                    ),
                })

            sale_subtotal = sum(
                (item.total_price for item in sale.items.all()),
                Decimal('0.00'),
            )
            cumulative_quantity = previous_quantity + quantity
            cumulative_gross = sale_item.unit_price * cumulative_quantity
            allocated_revenue = (
                (sale.total_amount * cumulative_gross / sale_subtotal).quantize(
                    Decimal('0.01'),
                    rounding=ROUND_HALF_UP,
                )
                if sale_subtotal else Decimal('0.00')
            )
            revenue_total = allocated_revenue - (returned_so_far['revenue'] or Decimal('0.00'))

            return_item = SaleReturnItem.objects.create(
                sale_return=return_record,
                sale_item=sale_item,
                quantity=quantity,
                gross_revenue_total=sale_item.unit_price * quantity,
                revenue_total=revenue_total,
            )
            if sale.is_external:
                continue
            product = Product.objects.select_for_update().get(pk=sale_item.product_id)

            tracked_return_links = list(
                SaleItemTrackedUnit.objects.select_for_update()
                .select_related('stock_unit__carton')
                .filter(
                    sale_item=sale_item,
                    sale_return_item__isnull=True,
                    stock_unit__status='sold',
                )
                .order_by('id')[:quantity]
            )
            carton_additions = {}
            for index, link in enumerate(tracked_return_links):
                unit = link.stock_unit
                link.sale_return_item = return_item
                link.save(update_fields=['sale_return_item'])
                unit.location = sale.location or unit.location
                unit.status = 'available' if index < restock_quantity else 'quarantined'
                unit.save(update_fields=['location', 'status', 'updated_at'])
                if (
                    index < restock_quantity
                    and sale.location_id
                    and unit.carton.location_id == sale.location_id
                ):
                    carton_additions[unit.carton_id] = carton_additions.get(unit.carton_id, 0) + 1
            for carton_id, restored_quantity in carton_additions.items():
                carton = Carton.objects.select_for_update().get(pk=carton_id)
                carton.quantity += restored_quantity
                carton.save(update_fields=['quantity', 'updated_at'])

            remaining = quantity
            restock_remaining = restock_quantity
            known_cost = Decimal('0.00')
            cost_is_known = True
            allocations = sale_item.cost_allocations.select_for_update().order_by('created_at', 'id')
            for allocation in allocations:
                already_returned = SaleReturnCostAllocation.objects.filter(
                    original_allocation=allocation,
                ).aggregate(quantity=Sum('quantity'))['quantity'] or 0
                available = allocation.quantity - already_returned
                restored = min(remaining, available)
                if not restored:
                    continue

                accepted_from_allocation = min(restock_remaining, restored)
                quarantined_from_allocation = restored - accepted_from_allocation
                if accepted_from_allocation:
                    SaleReturnCostAllocation.objects.create(
                        return_item=return_item,
                        original_allocation=allocation,
                        quantity=accepted_from_allocation,
                        unit_cost=allocation.unit_cost,
                    )
                    record_cost_layer(
                        product=product,
                        location=sale.location,
                        quantity=accepted_from_allocation,
                        unit_cost=allocation.unit_cost,
                        source='return',
                        reference=f'RETURN-{return_record.id}',
                    )
                if quarantined_from_allocation:
                    SaleReturnCostAllocation.objects.create(
                        return_item=return_item,
                        original_allocation=allocation,
                        quantity=quarantined_from_allocation,
                        unit_cost=allocation.unit_cost,
                        quantity_quarantined_remaining=quarantined_from_allocation,
                    )
                    record_cost_layer(
                        product=product,
                        location=sale.location,
                        quantity=quarantined_from_allocation,
                        unit_cost=allocation.unit_cost,
                        source='return',
                        reference=f'RETURN-{return_record.id}-Q-{allocation.id}',
                        is_available=False,
                    )
                restock_remaining -= accepted_from_allocation
                if allocation.unit_cost is None:
                    cost_is_known = False
                else:
                    known_cost += allocation.unit_cost * restored
                remaining -= restored

            if remaining:
                accepted_unknown = min(restock_remaining, remaining)
                quarantined_unknown = remaining - accepted_unknown
                if accepted_unknown:
                    SaleReturnCostAllocation.objects.create(
                        return_item=return_item,
                        quantity=accepted_unknown,
                        unit_cost=None,
                    )
                    record_cost_layer(
                        product=product,
                        location=sale.location,
                        quantity=accepted_unknown,
                        unit_cost=None,
                        source='return',
                        reference=f'RETURN-{return_record.id}',
                    )
                if quarantined_unknown:
                    SaleReturnCostAllocation.objects.create(
                        return_item=return_item,
                        quantity=quarantined_unknown,
                        unit_cost=None,
                        quantity_quarantined_remaining=quarantined_unknown,
                    )
                    record_cost_layer(
                        product=product,
                        location=sale.location,
                        quantity=quarantined_unknown,
                        unit_cost=None,
                        source='return',
                        reference=f'RETURN-{return_record.id}-Q-UNKNOWN',
                        is_available=False,
                    )
                cost_is_known = False
            return_item.cost_total = known_cost if cost_is_known else None
            return_item.save(update_fields=['cost_total'])

            if sale.location_id and (restock_quantity or quarantined_quantity):
                if restock_quantity:
                    stock_item, _ = StockItem.objects.select_for_update().get_or_create(
                        product=product,
                        location=sale.location,
                    )
                    stock_item.quantity += restock_quantity
                    stock_item.save(update_fields=['quantity', 'updated_at'])
                if restock_quantity:
                    StockMovement.objects.create(
                        product=product,
                        location=sale.location,
                        movement_type='in',
                        quantity=restock_quantity,
                        reference=f'RETURN-{return_record.id}',
                        notes=f'Retour conforme de la vente {sale.id}',
                        created_by=request.user,
                    )
                if quarantined_quantity:
                    quarantine = SaleReturnQuarantine.objects.create(
                        return_item=return_item,
                        location=sale.location,
                        quantity=quarantined_quantity,
                        quantity_remaining=quarantined_quantity,
                        reason=submitted_item['quarantine_reason'].strip(),
                    )
                    StockMovement.objects.create(
                        product=product,
                        location=sale.location,
                        movement_type='quarantine_in',
                        quantity=quarantined_quantity,
                        reference=f'RETURN-Q-{quarantine.id}',
                        notes=quarantine.reason,
                        created_by=request.user,
                    )

            product.quantity = (product.quantity or 0) + restock_quantity
            product.save(update_fields=['quantity', 'updated_at'])

        AuditLog.objects.create(
            user=request.user,
            action='sale_return',
            model_name='SaleReturn',
            record_id=return_record.id,
            details=f'Retour enregistré pour la vente {sale.id}: {return_record.reason}',
        )
        return return_record


class SaleReturnQuarantineReleaseSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField()

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError('Un motif de remise en stock est obligatoire.')
        return value.strip()


class SaleReturnQuarantineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source='return_item.sale_item.product.name',
        read_only=True,
    )
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = SaleReturnQuarantine
        fields = [
            'id',
            'product_name',
            'location_name',
            'quantity',
            'quantity_remaining',
            'reason',
            'status',
            'created_at',
        ]
        read_only_fields = fields
