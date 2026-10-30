from rest_framework import serializers

from .models import InvoiceBranding
from sales.models import Invoice


def invoice_verification_url(obj):
    from django.conf import settings

    return f'{settings.INVOICE_VERIFICATION_BASE_URL}{obj.verification_token}'


class InvoiceSerializer(serializers.ModelSerializer):
    customer = serializers.SerializerMethodField()
    sale_id = serializers.IntegerField(read_only=True)
    verification_url = serializers.SerializerMethodField()
    qr_image_url = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    print_mode = serializers.SerializerMethodField()
    validation_reference = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id',
            'sale_id',
            'customer',
            'company_name',
            'invoice_number',
            'qr_code',
            'verification_url',
            'qr_image_url',
            'status',
            'validation_reference',
            'print_mode',
            'balance_due',
            'issue_date',
            'total_amount',
            'paid_amount',
            'document_status',
            'document_sha256',
            'document_pages',
            'signed_at',
            'created_at',
        ]
        read_only_fields = [
            'id', 'invoice_number', 'qr_code', 'verification_token',
            'verification_url', 'qr_image_url', 'issue_date', 'created_at',
            'status', 'balance_due', 'print_mode', 'validation_reference',
            'document_status', 'document_sha256', 'document_pages', 'signed_at',
        ]

    def get_customer(self, obj):
        customer = obj.sale.customer
        return {
            'id': customer.id,
            'full_name': customer.full_name,
            'phone': customer.phone,
        }

    def get_verification_url(self, obj):
        return invoice_verification_url(obj)

    def get_qr_image_url(self, obj):
        request = self.context.get('request')
        path = f'/api/invoices/{obj.pk}/qr-image/'
        return request.build_absolute_uri(path) if request else path

    def get_balance_due(self, obj):
        return obj.balance_due

    def get_status(self, obj):
        return obj.status

    def get_print_mode(self, obj):
        return obj.print_mode

    def get_validation_reference(self, obj):
        return obj.validation_reference


class InvoiceBrandingSerializer(serializers.ModelSerializer):
    logo_image = serializers.ImageField(required=False, write_only=True)
    automotive_image = serializers.ImageField(required=False, write_only=True)
    watermark_image = serializers.ImageField(required=False, write_only=True)
    stamp_image = serializers.ImageField(required=False, write_only=True)
    seller_signature_image = serializers.ImageField(required=False, write_only=True)
    logo_url = serializers.SerializerMethodField()
    automotive_image_url = serializers.SerializerMethodField()
    watermark_image_url = serializers.SerializerMethodField()
    stamp_image_url = serializers.SerializerMethodField()
    seller_signature_image_url = serializers.SerializerMethodField()
    is_configured = serializers.SerializerMethodField()
    phone_numbers = serializers.ListField(
        child=serializers.CharField(max_length=30, allow_blank=False),
        allow_empty=True,
    )
    email_addresses = serializers.ListField(
        child=serializers.EmailField(),
        allow_empty=True,
    )
    additional_lines = serializers.ListField(
        child=serializers.CharField(max_length=240, allow_blank=False),
        allow_empty=True,
    )

    class Meta:
        model = InvoiceBranding
        fields = [
            'id', 'company_name', 'activity', 'distributor_details', 'address',
            'phone_numbers', 'email', 'email_addresses', 'additional_lines',
            'rccm', 'nif', 'line_display_mode', 'header_alignment', 'header_color',
            'text_color', 'show_company_name', 'show_activity', 'show_distributor',
            'show_address', 'show_phones', 'show_emails', 'show_rccm', 'show_nif',
            'show_logo', 'show_automotive_image', 'show_watermark', 'show_stamp',
            'show_seller_signature', 'show_qr', 'seller_signature_name',
            'seller_signature_title', 'logo_image',
            'automotive_image', 'watermark_image', 'logo_url', 'automotive_image_url',
            'watermark_image_url', 'stamp_image', 'stamp_image_url',
            'seller_signature_image', 'seller_signature_image_url', 'stamp_position',
            'stamp_size_mm', 'stamp_opacity', 'updated_at', 'is_configured',
        ]
        read_only_fields = ['id', 'updated_at']

    def validate(self, attrs):
        email_addresses = attrs.get('email_addresses')
        if email_addresses is not None:
            attrs['email'] = email_addresses[0] if email_addresses else ''
        for field_name in (
            'logo_image',
            'automotive_image',
            'watermark_image',
            'stamp_image',
            'seller_signature_image',
        ):
            image = attrs.get(field_name)
            if image and image.size > 5 * 1024 * 1024:
                raise serializers.ValidationError({field_name: 'La taille maximale d’une image est de 5 Mo.'})
        return attrs

    def _asset_url(self, obj, asset):
        request = self.context.get('request')
        path = f'/api/v1/invoices/branding/assets/{asset}/'
        return request.build_absolute_uri(path) if request else path

    def get_logo_url(self, obj):
        return self._asset_url(obj, 'logo') if obj.logo_image else ''

    def get_automotive_image_url(self, obj):
        return self._asset_url(obj, 'automotive') if obj.automotive_image else ''

    def get_watermark_image_url(self, obj):
        return self._asset_url(obj, 'watermark') if obj.watermark_image else ''

    def get_stamp_image_url(self, obj):
        return self._asset_url(obj, 'stamp') if obj.stamp_image else ''

    def get_seller_signature_image_url(self, obj):
        return self._asset_url(obj, 'signature') if obj.seller_signature_image else ''

    def get_is_configured(self, obj):
        return obj.updated_by_id is not None
