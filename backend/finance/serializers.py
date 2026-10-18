from decimal import Decimal

from rest_framework import serializers

from core.tenancy import tenant_for_user, tenant_scoped_queryset
from users.models import User
from .models import FinancialAccount, FinancialTransaction, Fund, FundReturn


class FinancialAccountSerializer(serializers.ModelSerializer):
    current_balance = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = FinancialAccount
        fields = ['id', 'name', 'account_type', 'currency', 'opening_balance', 'current_balance', 'status', 'created_by', 'created_at', 'updated_at']
        read_only_fields = ['id', 'current_balance', 'created_by', 'created_at', 'updated_at']

    def validate_opening_balance(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError('Le solde initial ne peut pas être négatif.')
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        return super().create(
            {
                **validated_data,
                'tenant': tenant_for_user(getattr(request, 'user', None)),
            },
        )


class FinancialTransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = FinancialTransaction
        fields = ['id', 'reference', 'transaction_date', 'transaction_type', 'direction', 'amount', 'currency', 'account', 'account_name', 'category', 'description', 'origin', 'status', 'created_by', 'validated_by', 'validated_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'reference', 'status', 'created_by', 'validated_by', 'validated_at', 'created_at', 'updated_at']

    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError('Le montant doit être supérieur à zéro.')
        return value

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            fields['account'].queryset = tenant_scoped_queryset(
                fields['account'].queryset,
                user,
            )
        return fields


class FundSerializer(serializers.ModelSerializer):
    responsible_name = serializers.CharField(source='responsible.display_name', read_only=True)
    spent_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    returned_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    remaining_to_regularize = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Fund
        fields = ['id', 'reference', 'purpose', 'responsible', 'responsible_name', 'amount', 'currency', 'assigned_at', 'due_date', 'status', 'spent_amount', 'returned_amount', 'remaining_to_regularize', 'created_by', 'closed_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'reference', 'status', 'spent_amount', 'returned_amount', 'remaining_to_regularize', 'created_by', 'closed_at', 'created_at', 'updated_at']

    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError('Le montant attribué doit être supérieur à zéro.')
        return value

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            fields['responsible'].queryset = tenant_scoped_queryset(
                User.objects.all(),
                user,
            )
        return fields

    def create(self, validated_data):
        request = self.context.get('request')
        return super().create(
            {
                **validated_data,
                'tenant': tenant_for_user(getattr(request, 'user', None)),
            },
        )


class FundReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = FundReturn
        fields = ['id', 'fund', 'reference', 'amount', 'returned_at', 'returned_by', 'notes']
        read_only_fields = ['id', 'reference', 'returned_by']

    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError('Le retour doit être supérieur à zéro.')
        return value

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            fields['fund'].queryset = tenant_scoped_queryset(
                fields['fund'].queryset,
                user,
            )
        return fields


class FinancialTransferSerializer(serializers.Serializer):
    source_account = serializers.PrimaryKeyRelatedField(queryset=FinancialAccount.objects.all())
    destination_account = serializers.PrimaryKeyRelatedField(queryset=FinancialAccount.objects.all())
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            for field_name in ('source_account', 'destination_account'):
                fields[field_name].queryset = tenant_scoped_queryset(
                    fields[field_name].queryset,
                    user,
                )
        return fields

    def validate(self, attrs):
        if attrs['source_account'].pk == attrs['destination_account'].pk:
            raise serializers.ValidationError('Les comptes source et destination doivent être différents.')
        if attrs['source_account'].status != 'active' or attrs['destination_account'].status != 'active':
            raise serializers.ValidationError('Les deux comptes doivent être actifs.')
        if attrs['source_account'].currency != attrs['destination_account'].currency:
            raise serializers.ValidationError(
                'Les comptes doivent utiliser la même devise pour effectuer un transfert.',
            )
        return attrs
