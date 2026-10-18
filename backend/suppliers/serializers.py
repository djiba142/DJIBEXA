from rest_framework import serializers

from purchases.serializers import PurchaseOrderSerializer
from .models import ExchangeRate, Supplier, SupplierImport, SupplierImportRow


class SupplierImportRequestSerializer(serializers.Serializer):
    supplier = serializers.IntegerField()
    file = serializers.FileField()


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_name', 'phone', 'email', 'address',
            'company_name', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExchangeRateSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeRate
        fields = [
            'id', 'source_currency', 'target_currency', 'rate', 'effective_date',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_by_name', 'created_at']

    def get_created_by_name(self, obj):
        if obj.created_by is None:
            return ''
        return obj.created_by.get_full_name() or obj.created_by.get_username()

    def validate_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError('Le taux de change doit être supérieur à zéro.')
        return value

    def validate_source_currency(self, value):
        return value.strip().upper()

    def validate_target_currency(self, value):
        return value.strip().upper()


class SupplierImportRowSerializer(serializers.ModelSerializer):
    matched_product_id = serializers.IntegerField(source='product_id', read_only=True)

    class Meta:
        model = SupplierImportRow
        fields = [
            'id', 'reference', 'name', 'quantity', 'unit_price', 'currency',
            'matched_product', 'matched_product_id', 'validation_errors', 'notes',
        ]
        read_only_fields = ['id']


class SupplierImportSerializer(serializers.ModelSerializer):
    rows = SupplierImportRowSerializer(many=True, read_only=True)
    purchase_order = serializers.SerializerMethodField()

    class Meta:
        model = SupplierImport
        fields = [
            'id', 'supplier', 'file_name', 'status', 'parsed_rows', 'created_at',
            'rows', 'purchase_order', 'file_sha256', 'possible_duplicate_of',
        ]
        read_only_fields = [
            'id', 'created_at', 'rows', 'purchase_order', 'file_sha256', 'possible_duplicate_of',
        ]

    def get_purchase_order(self, obj):
        if not getattr(obj, 'purchase_order', None):
            return None
        return PurchaseOrderSerializer(obj.purchase_order).data
