from rest_framework import serializers

from .models import AppSetting, AuditLog, Company


class JsonResponseSerializer(serializers.Serializer):
    payload = serializers.JSONField(required=False)


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'action', 'model_name', 'record_id', 'details', 'created_at']
        read_only_fields = ['id', 'created_at']


class AppSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppSetting
        fields = ['id', 'key', 'value', 'description', 'updated_at']
        read_only_fields = ['id', 'updated_at']


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'legal_name', 'phone', 'email', 'address', 'currency', 'updated_at']
        read_only_fields = ['id', 'updated_at']
