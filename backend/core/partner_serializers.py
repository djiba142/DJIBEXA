from rest_framework import serializers

from .models import Partner


class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = [
            'id', 'name', 'tagline', 'logo_url', 'phone', 'whatsapp', 'email',
            'website', 'notes', 'show_on_invoice', 'show_on_orders', 'active',
            'sort_order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
