from django.db import transaction
from django.db.models import Q, Sum
from datetime import datetime, time

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from core.models import AuditLog
from core.idempotency import execute_idempotent_request
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from expenses.models import Expense
from users.permissions import IsAdminUser, IsTenantAssignedUser, role_permission

from .models import FinancialAccount, FinancialTransaction, Fund, FundReturn
from .serializers import FinancialAccountSerializer, FinancialTransactionSerializer, FinancialTransferSerializer, FundReturnSerializer, FundSerializer


class FinancialAccountPermission(permissions.BasePermission):
    message = 'La gestion des comptes financiers exige un rôle de gestion.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return (
                request.user.has_any_role('admin', 'sales')
                or getattr(request.user, 'is_superuser', False)
            )
        return request.user.has_role('admin') or getattr(request.user, 'is_superuser', False)


class FinancialSummaryView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get(self, request):
        accounts = tenant_scoped_queryset(FinancialAccount.objects.all(), request.user)
        transactions = tenant_scoped_queryset(
            FinancialTransaction.objects.filter(status='validated'),
            request.user,
        )
        expenses = tenant_scoped_queryset(Expense.objects.all(), request.user)
        funds = tenant_scoped_queryset(
            Fund.objects.filter(status='open'),
            request.user,
        )
        cash_in = transactions.filter(direction='in').aggregate(total=Sum('amount'))['total'] or 0
        cash_out = transactions.filter(direction='out').aggregate(total=Sum('amount'))['total'] or 0
        return Response({
            'total_balance': sum((account.current_balance for account in accounts), 0),
            'cash_in': cash_in,
            'cash_out': cash_out,
            'net_cash': cash_in - cash_out,
            'pending_expenses': expenses.filter(status='pending').count(),
            'unjustified_expenses': expenses.filter(status__in=['validated', 'pending'], justification='').count(),
            'funds_in_progress': funds.count(),
            'funds_to_regularize': sum((fund.remaining_to_regularize for fund in funds), 0),
        }, status=status.HTTP_200_OK)


def period_bounds(request):
    start_value = request.query_params.get('start')
    end_value = request.query_params.get('end')
    try:
        start = datetime.fromisoformat(start_value).date() if start_value else timezone.localdate().replace(month=1, day=1)
        end = datetime.fromisoformat(end_value).date() if end_value else timezone.localdate()
    except ValueError:
        return None, None
    if end < start:
        return None, None
    return timezone.make_aware(datetime.combine(start, time.min)), timezone.make_aware(datetime.combine(end, time.max))


class FinancialReportView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get(self, request):
        start, end = period_bounds(request)
        if not start:
            return Response({'detail': 'Les dates de période sont invalides.'}, status=status.HTTP_400_BAD_REQUEST)
        transactions = tenant_scoped_queryset(
            FinancialTransaction.objects.filter(
                transaction_date__range=(start, end),
                status='validated',
            ),
            request.user,
        )
        expenses = tenant_scoped_queryset(
            Expense.objects.filter(expense_date__range=(start, end)),
            request.user,
        )
        funds = tenant_scoped_queryset(
            Fund.objects.filter(assigned_at__range=(start, end)),
            request.user,
        )
        accounts = tenant_scoped_queryset(FinancialAccount.objects.all(), request.user)
        by_category = list(expenses.filter(status='validated').values('category__name').annotate(total=Sum('amount')).order_by('-total'))
        by_account = list(transactions.values('account__name').annotate(total=Sum('amount')).order_by('-total'))
        cash_in = transactions.filter(direction='in').aggregate(total=Sum('amount'))['total'] or 0
        cash_out = transactions.filter(direction='out').aggregate(total=Sum('amount'))['total'] or 0
        return Response({
            'period': {'start': start.date(), 'end': end.date()},
            'opening_balance': sum((account.opening_balance for account in accounts), 0),
            'total_income': cash_in,
            'total_expenses': cash_out,
            'total_funds_assigned': funds.aggregate(total=Sum('amount'))['total'] or 0,
            'total_fund_returns': FundReturn.objects.filter(
                fund__in=funds,
                returned_at__range=(start, end),
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'closing_balance': sum((account.current_balance for account in accounts), 0),
            'expenses_by_category': by_category,
            'movements_by_account': by_account,
            'pending_expenses': expenses.filter(status='pending').count(),
            'unjustified_expenses': expenses.filter(status='validated', justification='').count(),
        }, status=status.HTTP_200_OK)


class FinancialAuditView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get(self, request):
        tenant_expenses = tenant_scoped_queryset(
            Expense.objects.all(),
            request.user,
        )
        tenant_funds = tenant_scoped_queryset(Fund.objects.all(), request.user)
        tenant_transactions = tenant_scoped_queryset(
            FinancialTransaction.objects.all(),
            request.user,
        )
        tenant_accounts = tenant_scoped_queryset(
            FinancialAccount.objects.all(),
            request.user,
        )
        logs = AuditLog.objects.filter(
            Q(model_name='Expense', record_id__in=tenant_expenses.values('pk'))
            | Q(model_name='Fund', record_id__in=tenant_funds.values('pk'))
            | Q(
                model_name='FinancialTransaction',
                record_id__in=tenant_transactions.values('pk'),
            )
            | Q(
                model_name='FinancialAccount',
                record_id__in=tenant_accounts.values('pk'),
            ),
        ).select_related('user')
        return Response([{
            'id': log.id, 'action': log.action, 'model_name': log.model_name,
            'record_id': log.record_id, 'details': log.details,
            'user': log.user.display_name if log.user else None,
            'created_at': log.created_at,
        } for log in logs[:100]], status=status.HTTP_200_OK)


class FinancialAccountListCreateView(generics.ListCreateAPIView):
    queryset = FinancialAccount.objects.all()
    serializer_class = FinancialAccountSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        FinancialAccountPermission,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            tenant=tenant_for_user(self.request.user),
        )


class FinancialAccountDetailView(generics.RetrieveUpdateAPIView):
    queryset = FinancialAccount.objects.all()
    serializer_class = FinancialAccountSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        FinancialAccountPermission,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)


class FinancialTransactionListCreateView(generics.ListCreateAPIView):
    queryset = FinancialTransaction.objects.select_related('account', 'created_by', 'validated_by').all()
    serializer_class = FinancialTransactionSerializer
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


class FinancialTransactionDetailView(generics.RetrieveUpdateAPIView):
    queryset = FinancialTransaction.objects.select_related('account', 'created_by', 'validated_by').all()
    serializer_class = FinancialTransactionSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
        IsAdminUser,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    def patch(self, request, *args, **kwargs):
        transaction = self.get_object()
        if transaction.status == 'validated':
            return Response({'detail': 'Un mouvement validé ne peut pas être modifié.'}, status=status.HTTP_409_CONFLICT)
        return super().patch(request, *args, **kwargs)

class FinancialTransactionValidateView(generics.GenericAPIView):
    queryset = FinancialTransaction.objects.select_related('account', 'created_by', 'validated_by').all()
    serializer_class = FinancialTransactionSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
        IsAdminUser,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    def post(self, request, *args, **kwargs):
        transaction = self.get_object()
        if transaction.status != 'pending':
            return Response({'detail': 'Seul un mouvement en attente peut être validé.'}, status=status.HTTP_409_CONFLICT)
        transaction.status = 'validated'
        transaction.validated_by = request.user
        transaction.validated_at = timezone.now()
        transaction.save(update_fields=['status', 'validated_by', 'validated_at', 'updated_at'])
        return Response(self.get_serializer(transaction).data, status=status.HTTP_200_OK)


class FinancialTransferView(generics.GenericAPIView):
    serializer_class = FinancialTransferSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
        IsAdminUser,
    ]

    def post(self, request):
        def transfer_funds():
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                account_ids = sorted((
                    serializer.validated_data['source_account'].pk,
                    serializer.validated_data['destination_account'].pk,
                ))
                locked_accounts = {
                    account.pk: account
                    for account in FinancialAccount.objects.select_for_update()
                    .filter(pk__in=account_ids)
                    .order_by('pk')
                }
                source = locked_accounts[serializer.validated_data['source_account'].pk]
                destination = locked_accounts[serializer.validated_data['destination_account'].pk]
                if source.status != 'active' or destination.status != 'active':
                    return Response(
                        {'detail': 'Les deux comptes doivent être actifs.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if source.currency != destination.currency:
                    return Response(
                        {'detail': 'Les comptes doivent utiliser la même devise pour effectuer un transfert.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                amount = serializer.validated_data['amount']
                if source.current_balance < amount:
                    return Response(
                        {'detail': 'Le solde du compte source est insuffisant.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                transfer_id = timezone.now().strftime('%Y%m%d%H%M%S%f')
                description = serializer.validated_data.get('description', '') or f'Transfert {source.name} vers {destination.name}'
                for account, direction in ((source, 'out'), (destination, 'in')):
                    FinancialTransaction.objects.create(
                        transaction_type='transfer', direction=direction, amount=amount,
                        currency=source.currency, account=account,
                        tenant=tenant_for_user(request.user),
                        description=description, origin=f'transfer:{transfer_id}',
                        status='validated', created_by=request.user, validated_by=request.user,
                        validated_at=timezone.now(),
                    )
                AuditLog.objects.create(user=request.user, action='update', model_name='FinancialTransfer', record_id=source.id, details=f'Transfert de {amount} de {source.name} vers {destination.name}')
                return Response(
                    {
                        'transfer_id': transfer_id,
                        'amount': amount,
                        'source_account': source.id,
                        'destination_account': destination.id,
                    },
                    status=status.HTTP_201_CREATED,
                )

        return execute_idempotent_request(request, request.path, transfer_funds)


class FundListCreateView(generics.ListCreateAPIView):
    queryset = Fund.objects.select_related('responsible', 'created_by').all()
    serializer_class = FundSerializer
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


class FundDetailView(generics.RetrieveUpdateAPIView):
    queryset = Fund.objects.select_related('responsible', 'created_by').all()
    serializer_class = FundSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
        IsAdminUser,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)


class FundActionView(generics.GenericAPIView):
    queryset = Fund.objects.select_related('responsible', 'created_by').all()
    serializer_class = FundSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
        IsAdminUser,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(super().get_queryset(), self.request.user)

    @transaction.atomic
    def post(self, request, pk, action):
        fund = self.get_object()
        if action == 'return':
            if fund.status != 'open':
                return Response({'detail': 'Seul un fonds en cours peut recevoir un retour.'}, status=status.HTTP_409_CONFLICT)
            amount = request.data.get('amount')
            account_id = request.data.get('account')
            if not account_id:
                return Response({'detail': 'Un compte financier est requis pour enregistrer le retour.'}, status=status.HTTP_400_BAD_REQUEST)
            account = tenant_scoped_queryset(
                FinancialAccount.objects.all(),
                request.user,
            ).filter(pk=account_id).first()
            if account is None:
                return Response(
                    {'detail': 'Le compte financier ne fait pas partie de votre entreprise.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer = FundReturnSerializer(data={'fund': fund.id, 'amount': amount, 'notes': request.data.get('notes', '')})
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data['amount'] > fund.remaining_to_regularize:
                return Response({'detail': 'Le retour dépasse le solde à régulariser.'}, status=status.HTTP_400_BAD_REQUEST)
            fund_return = serializer.save(returned_by=request.user)
            FinancialTransaction.objects.create(
                transaction_type='fund_return', direction='in', amount=fund_return.amount,
                currency=fund.currency, account=account, tenant=fund.tenant,
                description=f'Retour du fonds {fund.reference}', origin=f'fund_return:{fund_return.id}',
                status='validated', created_by=request.user, validated_by=request.user,
                validated_at=timezone.now(),
            )
        elif action == 'close':
            if fund.remaining_to_regularize != 0:
                return Response({'detail': 'Le fonds doit être entièrement régularisé avant clôture.'}, status=status.HTTP_400_BAD_REQUEST)
            fund.status = 'closed'
            fund.closed_at = timezone.now()
            fund.save(update_fields=['status', 'closed_at', 'updated_at'])
        else:
            return Response({'detail': 'Action de fonds inconnue.'}, status=status.HTTP_404_NOT_FOUND)
        AuditLog.objects.create(user=request.user, action='update', model_name='Fund', record_id=fund.id, details=f'Action finance: {action}')
        return Response(self.get_serializer(fund).data, status=status.HTTP_200_OK)