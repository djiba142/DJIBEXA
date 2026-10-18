from rest_framework import serializers
from django.db import transaction
import uuid

from core.tenancy import tenant_scoped_queryset
from sales.models import Sale
from .models import DeliveryNote, DeliveryNoteItem, Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            'id', 'title', 'document_type', 'file_name', 'file_url',
            'related_model', 'related_id', 'status', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DeliveryNoteItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = DeliveryNoteItem
        fields = ['id', 'product', 'product_name', 'product_sku', 'quantity']
        read_only_fields = ['id']


class DeliveryNoteSerializer(serializers.ModelSerializer):
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.none())
    items = DeliveryNoteItemSerializer(many=True, read_only=True)
    sale_reference = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source='sale.customer.full_name', read_only=True)
    customer_phone = serializers.CharField(source='sale.customer.phone', read_only=True)
    customer_address = serializers.CharField(source='sale.customer.address', read_only=True)
    verification_url = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryNote
        fields = [
            'id', 'reference', 'sale', 'sale_reference', 'customer_name', 'customer_phone',
            'customer_address', 'status', 'notes', 'verification_token', 'verification_url',
            'created_at', 'items',
        ]
        read_only_fields = [
            'id', 'reference', 'sale_reference', 'customer_name', 'customer_phone',
            'customer_address', 'verification_token', 'verification_url', 'created_at', 'items',
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['sale'].queryset = tenant_scoped_queryset(
                Sale.objects.all(),
                request.user,
            )
        return fields

    def get_sale_reference(self, obj):
        invoice = getattr(obj.sale, 'invoice', None)
        return invoice.invoice_number if invoice else f'VTE-{obj.sale_id}'

    def get_verification_url(self, obj):
        request = self.context.get('request')
        path = f'/verifier/{obj.verification_token}'
        return request.build_absolute_uri(path) if request else path

    def validate_status(self, value):
        if self.instance and self.instance.status != 'prepared' and value != self.instance.status:
            raise serializers.ValidationError('Seul un bon préparé peut être modifié.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        sale = validated_data['sale']
        reference = f"BL-{sale.pk:06d}-{uuid.uuid4().hex[:6].upper()}"
        note = DeliveryNote.objects.create(reference=reference, **validated_data)
        for item in sale.items.all():
            DeliveryNoteItem.objects.create(
                delivery_note=note,
                product=item.product,
                quantity=item.quantity,
            )
        return note
