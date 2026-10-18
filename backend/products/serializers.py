from rest_framework import serializers

from core.tenancy import tenant_scoped_queryset

from .models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    margin_amount = serializers.SerializerMethodField()
    margin_percent = serializers.SerializerMethodField()
    quantity = serializers.IntegerField(required=False, min_value=0)

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'manufacturer_reference', 'name', 'category', 'category_name', 'brand', 'vehicle',
            'description', 'alternative_references', 'unit', 'package_unit', 'units_per_package',
            'purchase_price', 'cost_price', 'selling_price', 'currency', 'quantity', 'alert_threshold',
            'weight', 'volume', 'barcode', 'qr_code', 'sample_qr_code', 'image', 'is_active',
            'created_at', 'updated_at', 'margin_amount', 'margin_percent'
        ]
        read_only_fields = [
            'id', 'sample_qr_code', 'created_at', 'updated_at', 'margin_amount', 'margin_percent',
        ]

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and 'category' in fields:
            fields['category'].queryset = tenant_scoped_queryset(
                fields['category'].queryset,
                request.user,
            )
        if (
            request
            and request.user.is_authenticated
            and request.user.has_any_role('stock', 'sales')
            and not request.user.has_role('admin')
        ):
            for field_name in ('purchase_price', 'cost_price', 'margin_amount', 'margin_percent'):
                fields.pop(field_name, None)
        return fields

    def to_internal_value(self, data):
        if self.instance is not None and 'quantity' in data:
            raise serializers.ValidationError({
                'quantity': 'La quantité doit être modifiée via les mouvements de stock.',
            })
        return super().to_internal_value(data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        if (
            request
            and request.user.is_authenticated
            and request.user.has_role('stock')
            and not request.user.has_role('admin')
        ):
            representation['quantity'] = getattr(instance, 'accessible_quantity', 0) or 0
        else:
            representation['quantity'] = instance.quantity
        return representation

    def validate(self, attrs):
        if self.instance is not None and 'quantity' in attrs:
            raise serializers.ValidationError({
                'quantity': 'La quantité doit être modifiée via les mouvements de stock.',
            })
        if self.instance is None and attrs.get('quantity', 0) > 0:
            raise serializers.ValidationError({
                'quantity': (
                    'Le stock initial doit être créé via une réception ou un '
                    'inventaire validé pour un emplacement précis.'
                ),
            })
        package_unit = attrs.get('package_unit', getattr(self.instance, 'package_unit', ''))
        units_per_package = attrs.get(
            'units_per_package',
            getattr(self.instance, 'units_per_package', None),
        )
        if package_unit and not units_per_package:
            raise serializers.ValidationError({
                'units_per_package': 'Indiquez le nombre d’unités par conditionnement.',
            })
        if not package_unit and units_per_package:
            raise serializers.ValidationError({
                'package_unit': 'Choisissez un conditionnement ou laissez le nombre d’unités vide.',
            })
        return attrs

    def get_margin_amount(self, obj):
        return obj.selling_price - obj.cost_price

    def get_margin_percent(self, obj):
        if not obj.cost_price:
            return 0
        return round(float((obj.selling_price - obj.cost_price) / obj.cost_price * 100), 2)
