from rest_framework import serializers

from core.tenancy import tenant_scoped_queryset
from finance.models import FinancialAccount, Fund
from .models import Expense, ExpenseAttachment, ExpenseCategory


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    account_name = serializers.CharField(source='account.name', read_only=True)
    fund_reference = serializers.CharField(source='fund.reference', read_only=True)
    attachments_count = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            'id', 'category', 'category_name', 'title', 'amount', 'expense_date',
            'beneficiary', 'reference', 'justification', 'notes', 'account', 'account_name', 'fund', 'fund_reference', 'attachments_count',
            'status', 'approved_by', 'approved_at', 'rejection_reason', 'cancellation_reason',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'expense_date', 'account_name', 'status', 'approved_by', 'approved_at', 'rejection_reason', 'cancellation_reason', 'created_by', 'created_by_name', 'created_at', 'updated_at']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        if user and user.is_authenticated:
            fields['category'].queryset = tenant_scoped_queryset(
                fields['category'].queryset,
                user,
            )
            fields['account'].queryset = tenant_scoped_queryset(
                FinancialAccount.objects.all(),
                user,
            )
            fields['fund'].queryset = tenant_scoped_queryset(
                Fund.objects.all(),
                user,
            )
        return fields

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Le montant doit être supérieur à zéro.')
        return value

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_created_by_name(self, obj):
        return obj.created_by.display_name if obj.created_by else None

    def get_attachments_count(self, obj):
        return obj.attachments.count()


class ExpenseAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseAttachment
        fields = ['id', 'expense', 'file', 'original_name', 'uploaded_by', 'uploaded_at']
        read_only_fields = ['id', 'expense', 'original_name', 'uploaded_by', 'uploaded_at']

    def validate_file(self, value):
        allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.webp'}
        name = (value.name or '').lower()
        extension = '.' + name.rsplit('.', 1)[-1] if '.' in name else ''
        if extension not in allowed_extensions:
            raise serializers.ValidationError('Format non autorisé. Utilisez PDF, JPG, JPEG, PNG ou WEBP.')
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('La taille maximale d’un justificatif est de 10 Mo.')
        return value
