from rest_framework import serializers

from customers.models import Customer
from core.tenancy import tenant_for_user
from sales.models import Sale

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True,
    )
    sale = serializers.PrimaryKeyRelatedField(
        queryset=Sale.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Notification
        fields = [
            'id', 'tenant', 'recipient_user', 'sale', 'customer', 'channel', 'event_type', 'status', 'message',
            'recipient_phone', 'attempt_count', 'last_error', 'next_attempt_at',
            'reminder_period', 'is_read', 'read_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'tenant', 'recipient_user', 'attempt_count', 'last_error', 'next_attempt_at', 'reminder_period',
            'is_read', 'read_at', 'created_at', 'updated_at',
        ]
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        tenant = tenant_for_user(getattr(request, 'user', None))
        if tenant is not None and getattr(request.user, 'tenant_id', None) is not None:
            self.fields['sale'].queryset = Sale.objects.filter(tenant=tenant)
            self.fields['customer'].queryset = Customer.objects.filter(tenant=tenant)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        tenant = tenant_for_user(user)
        if tenant is None or getattr(user, 'tenant_id', None) is None:
            return attrs

        sale = attrs.get('sale', getattr(self.instance, 'sale', None))
        customer = attrs.get('customer', getattr(self.instance, 'customer', None))
        if sale and sale.customer.tenant_id != tenant.pk:
            raise serializers.ValidationError({
                'sale': 'La vente doit appartenir à votre entreprise.',
            })
        if customer and customer.tenant_id != tenant.pk:
            raise serializers.ValidationError({
                'customer': 'Le client doit appartenir à votre entreprise.',
            })
        if sale and customer and sale.customer_id != customer.pk:
            raise serializers.ValidationError({
                'customer': 'Le client doit correspondre à celui de la vente.',
            })
        return attrs
