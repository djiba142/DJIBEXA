from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from core.models import AuditLog
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from finance.models import FinancialTransaction
from users.permissions import IsTenantAssignedUser, role_permission
from .models import Expense, ExpenseAttachment, ExpenseCategory
from .serializers import ExpenseAttachmentSerializer, ExpenseCategorySerializer, ExpenseSerializer


class ExpenseCategoryListCreateView(generics.ListCreateAPIView):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for_user(self.request.user))


class ExpenseListCreateView(generics.ListCreateAPIView):
    queryset = Expense.objects.select_related('category', 'created_by', 'account').all()
    serializer_class = ExpenseSerializer
    pagination_class = None
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            tenant=tenant_for_user(self.request.user),
        )


class ExpenseDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Expense.objects.select_related('category', 'created_by', 'account').all()
    serializer_class = ExpenseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'La suppression physique d’une dépense est interdite.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


class ExpenseActionView(generics.GenericAPIView):
    queryset = Expense.objects.select_related('category', 'created_by', 'account').all()
    serializer_class = ExpenseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    @transaction.atomic
    def post(self, request, pk, action):
        expense = self.get_object()
        if action == 'submit':
            if expense.status != 'draft':
                return Response({'detail': 'Seul un brouillon peut être soumis.'}, status=status.HTTP_409_CONFLICT)
            expense.status = 'pending'
            expense.save(update_fields=['status', 'updated_at'])
        elif action == 'validate':
            if expense.status != 'pending':
                return Response({'detail': 'Seule une dépense en attente peut être validée.'}, status=status.HTTP_409_CONFLICT)
            if not expense.account:
                return Response({'detail': 'Un compte financier est requis pour valider la dépense.'}, status=status.HTTP_400_BAD_REQUEST)
            now = timezone.now()
            expense.status = 'validated'
            expense.approved_by = request.user
            expense.approved_at = now
            expense.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
            FinancialTransaction.objects.create(
                transaction_type='expense', direction='out', amount=expense.amount,
                currency='GNF', account=expense.account, category=expense.category.name,
                tenant=expense.tenant,
                description=expense.title, origin=f'expense:{expense.id}',
                status='validated', created_by=expense.created_by or request.user,
                validated_by=request.user, validated_at=now,
            )
        elif action == 'reject':
            reason = request.data.get('reason', '').strip()
            if expense.status != 'pending' or not reason:
                return Response({'detail': 'Une dépense en attente et un motif sont requis.'}, status=status.HTTP_400_BAD_REQUEST)
            expense.status = 'rejected'
            expense.rejection_reason = reason
            expense.save(update_fields=['status', 'rejection_reason', 'updated_at'])
        elif action == 'cancel':
            reason = request.data.get('reason', '').strip()
            if expense.status == 'validated' and not reason:
                return Response({'detail': 'Un motif est requis pour annuler une dépense validée.'}, status=status.HTTP_400_BAD_REQUEST)
            if expense.status in {'cancelled', 'rejected'}:
                return Response({'detail': 'Cette dépense est déjà clôturée.'}, status=status.HTTP_409_CONFLICT)
            expense.status = 'cancelled'
            expense.cancellation_reason = reason
            expense.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
        else:
            return Response({'detail': 'Action de dépense inconnue.'}, status=status.HTTP_404_NOT_FOUND)
        AuditLog.objects.create(user=request.user, action='update', model_name='Expense', record_id=expense.id, details=f'Action finance: {action}')
        return Response(self.get_serializer(expense).data, status=status.HTTP_200_OK)


class ExpenseAttachmentListCreateView(generics.ListCreateAPIView):
    queryset = ExpenseAttachment.objects.select_related('expense', 'uploaded_by').all()
    serializer_class = ExpenseAttachmentSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('core'),
    ]

    def get_queryset(self):
        expense = get_object_or_404(
            tenant_scoped_queryset(Expense.objects.all(), self.request.user),
            pk=self.kwargs['expense_id'],
        )
        return self.queryset.filter(expense=expense)

    def perform_create(self, serializer):
        expense = get_object_or_404(
            tenant_scoped_queryset(Expense.objects.all(), self.request.user),
            pk=self.kwargs['expense_id'],
        )
        uploaded_file = self.request.FILES.get('file')
        serializer.save(
            expense=expense,
            original_name=getattr(uploaded_file, 'name', ''),
            uploaded_by=self.request.user,
        )
        attachment = serializer.instance
        AuditLog.objects.create(
            user=self.request.user,
            action='create',
            model_name='ExpenseAttachment',
            record_id=attachment.id,
            details=f'Justificatif ajouté à la dépense {attachment.expense_id}: {attachment.original_name}',
        )
