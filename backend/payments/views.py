from django.db.models import Count, F, Max, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from core.models import Company
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from customers.models import Customer
from sales.models import Sale
from users.permissions import (
    IsTenantAssignedUser,
    SensitiveMutationPermission,
    role_permission,
)
from core.idempotency import execute_idempotent_request
from .models import CreditLedger, Payment, PaymentAllocation
from .serializers import CreditLedgerSerializer, PaymentSerializer


def credit_sales_queryset(user=None):
    queryset = Sale.objects.filter(
        payment_method='credit',
        status__in=['partial', 'paid'],
    )
    if user is not None:
        queryset = tenant_scoped_queryset(queryset, user)
    if user and user.has_role('sales') and not user.has_role('admin') and not user.is_superuser:
        queryset = queryset.filter(seller=user)
    return queryset


def payments_for_user(queryset, user):
    tenant = tenant_for_user(user)
    queryset = tenant_scoped_queryset(
        queryset,
        user,
        tenant_field='customer__tenant',
    )
    if tenant is not None:
        sale_scope = Q(sale__isnull=True) | Q(sale__tenant=tenant)
        if user.tenant_id is None:
            sale_scope |= Q(sale__tenant__isnull=True)
        queryset = queryset.filter(sale_scope)
    allocations = tenant_scoped_queryset(
        PaymentAllocation.objects.select_related('sale__invoice'),
        user,
        tenant_field='sale__tenant',
    )
    if not user.has_role('sales') or user.has_role('admin') or user.is_superuser:
        return queryset.prefetch_related(None).prefetch_related(
            Prefetch('allocations', queryset=allocations),
        )

    own_allocation_payment_ids = PaymentAllocation.objects.filter(
        sale__seller=user,
    ).values('payment_id')
    other_allocation_payment_ids = PaymentAllocation.objects.exclude(
        sale__seller=user,
    ).values('payment_id')
    return (
        queryset.filter(
            Q(sale__seller=user) | Q(pk__in=own_allocation_payment_ids),
        )
        .filter(Q(sale__isnull=True) | Q(sale__seller=user))
        .exclude(pk__in=other_allocation_payment_ids)
        .distinct()
        .prefetch_related(None)
        .prefetch_related(Prefetch(
            'allocations',
            queryset=allocations.filter(sale__seller=user),
        ))
    )


def aging_bucket_for_days(days_overdue):
    if days_overdue <= 30:
        return '0-30'
    if days_overdue <= 60:
        return '31-60'
    if days_overdue <= 90:
        return '61-90'
    return '90+'


def credit_aging_summary(customer_id, queryset=None):
    sales_queryset = queryset if queryset is not None else credit_sales_queryset()
    open_sale = sales_queryset.filter(customer_id=customer_id).filter(total_amount__gt=F('amount_paid')).order_by('sale_date').first()
    if not open_sale:
        return {'days_overdue': 0, 'aging_bucket': 'paid', 'oldest_open_credit_date': None}

    days_overdue = max((timezone.now() - open_sale.sale_date).days, 0)
    return {
        'days_overdue': days_overdue,
        'aging_bucket': aging_bucket_for_days(days_overdue),
        'oldest_open_credit_date': open_sale.sale_date,
    }


class PaymentListCreateView(generics.ListCreateAPIView):
    queryset = Payment.objects.select_related('customer', 'sale', 'created_by').prefetch_related(
        'allocations__sale__invoice',
    ).all()
    serializer_class = PaymentSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('payments'),
    ]

    def get_queryset(self):
        return payments_for_user(super().get_queryset(), self.request.user)

    def create(self, request, *args, **kwargs):
        endpoint = request.path

        def create_payment():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return execute_idempotent_request(request, endpoint, create_payment)


class PaymentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Payment.objects.select_related('customer', 'sale', 'created_by').prefetch_related(
        'allocations__sale__invoice',
    ).all()
    serializer_class = PaymentSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('payments'),
        SensitiveMutationPermission,
    ]

    def get_queryset(self):
        return payments_for_user(super().get_queryset(), self.request.user)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'La suppression physique d’un paiement est interdite.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class PaymentReceiptView(generics.GenericAPIView):
    queryset = Payment.objects.select_related('customer', 'sale', 'created_by').prefetch_related(
        'allocations__sale__invoice',
    )
    serializer_class = PaymentSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('payments'),
    ]

    def get_queryset(self):
        return payments_for_user(super().get_queryset(), self.request.user)

    def get(self, request, *args, **kwargs):
        payment = self.get_object()
        return Response({
            'type': 'payment_receipt',
            'payment_id': payment.id,
            'reference': payment.reference,
            'customer': payment.customer.full_name,
            'sale_id': payment.sale_id,
            'amount': str(payment.amount),
            'payment_method': payment.payment_method,
            'payment_date': payment.payment_date,
            'created_by': payment.created_by.display_name if payment.created_by else '',
            'allocations': PaymentSerializer(payment).data['allocations'],
        }, status=status.HTTP_200_OK)


class CustomerPaymentSummaryView(generics.GenericAPIView):
    serializer_class = CreditLedgerSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('payments'),
    ]

    def get(self, request, customer_id):
        get_object_or_404(
            tenant_scoped_queryset(Customer.objects.all(), request.user),
            pk=customer_id,
        )
        customer_sales = credit_sales_queryset(request.user).filter(customer_id=customer_id)
        sales_total = customer_sales.aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = customer_sales.aggregate(total=Sum('amount_paid'))['total'] or 0
        balance = max(sales_total - total_paid, 0)
        latest_payment = PaymentAllocation.objects.filter(
            sale__in=customer_sales,
        ).aggregate(last=Max('payment__payment_date'))['last']

        aging = credit_aging_summary(customer_id, customer_sales)
        return Response({
            'customer_id': customer_id,
            'sales_count': customer_sales.count(),
            'sales_total': sales_total,
            'total_paid': total_paid,
            'balance': balance,
            'last_payment': latest_payment,
            'status': 'settled' if balance == 0 else ('partial' if total_paid else 'unpaid'),
            'days_overdue': aging['days_overdue'],
            'aging_bucket': aging['aging_bucket'],
            'oldest_open_credit_date': aging['oldest_open_credit_date'],
        }, status=status.HTTP_200_OK)


class CreditListView(generics.GenericAPIView):
    serializer_class = CreditLedgerSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('payments'),
    ]

    def get(self, request, *args, **kwargs):
        search = request.query_params.get('search', '').strip()
        queryset = credit_sales_queryset(request.user)
        if search:
            matching_customers = queryset.filter(
                Q(customer__full_name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(invoice__invoice_number__icontains=search)
            ).values_list('customer_id', flat=True).distinct()
            queryset = queryset.filter(customer_id__in=matching_customers)
        credits = queryset.values('customer_id').annotate(
            customer_name=F('customer__full_name'),
            customer_phone=F('customer__phone'),
            sales_count=Count('id', distinct=True),
            total_credit=Sum('total_amount'),
            total_paid=Sum('amount_paid'),
        ).order_by('customer_id')

        result = []
        for credit in credits:
            total_credit = credit['total_credit'] or 0
            total_paid = credit['total_paid'] or 0
            last_payment = PaymentAllocation.objects.filter(
                sale__in=queryset.filter(customer_id=credit['customer_id']),
            ).aggregate(last=Max('payment__payment_date'))['last']
            balance = max(total_credit - total_paid, 0)
            aging = credit_aging_summary(credit['customer_id'], queryset)
            result.append({
                'customer_id': credit['customer_id'],
                'customer_name': credit['customer_name'],
                'customer_phone': credit['customer_phone'],
                'sales_count': credit['sales_count'],
                'total_credit': total_credit,
                'total_paid': total_paid,
                'balance': balance,
                'last_payment': last_payment,
                'status': 'settled' if total_credit <= total_paid else ('partial' if total_paid else 'unpaid'),
                'days_overdue': aging['days_overdue'],
                'aging_bucket': aging['aging_bucket'],
                'oldest_open_credit_date': aging['oldest_open_credit_date'],
            })
        return Response(result, status=status.HTTP_200_OK)


class CustomerCreditDetailView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('payments'),
    ]

    def get(self, request, customer_id):
        get_object_or_404(
            tenant_scoped_queryset(Customer.objects.all(), request.user),
            pk=customer_id,
        )
        sales = credit_sales_queryset(request.user).filter(
            customer_id=customer_id,
        ).select_related('customer', 'invoice')
        if not sales.exists():
            return Response({'detail': 'Aucune vente à crédit pour ce client.'}, status=status.HTTP_404_NOT_FOUND)

        customer = sales.first().customer
        company = Company.objects.first()
        sale_ids = list(sales.values_list('id', flat=True))
        payments = payments_for_user(Payment.objects.filter(
            customer_id=customer_id,
        ).filter(
            Q(allocations__sale_id__in=sale_ids) | Q(sale_id__in=sale_ids),
        ).select_related('created_by').distinct().order_by('-payment_date', '-id'), request.user)
        total_credit = sales.aggregate(total=Sum('total_amount'))['total'] or 0
        total_paid = sales.aggregate(total=Sum('amount_paid'))['total'] or 0
        history = []
        for sale in sales.order_by('-sale_date'):
            sale_paid = sale.amount_paid
            invoice = getattr(sale, 'invoice', None)
            history.append({
                'sale_id': sale.id,
                'invoice_number': invoice.invoice_number if invoice else None,
                'date': sale.sale_date,
                'total_credit': sale.total_amount,
                'total_paid': sale_paid,
                'balance': max(sale.total_amount - sale_paid, 0),
            })

        aging = credit_aging_summary(customer_id, sales)
        return Response({
            'customer': {
                'id': customer.id,
                'full_name': customer.full_name,
                'phone': customer.phone,
                'email': customer.email,
            },
            'currency': company.currency if company else 'GNF',
            'sales_count': sales.count(),
            'total_credit': total_credit,
            'total_paid': total_paid,
            'balance': max(total_credit - total_paid, 0),
            'status': 'settled' if total_credit <= total_paid else ('partial' if total_paid else 'unpaid'),
            'days_overdue': aging['days_overdue'],
            'aging_bucket': aging['aging_bucket'],
            'oldest_open_credit_date': aging['oldest_open_credit_date'],
            'sales': history,
            'payments': PaymentSerializer(payments, many=True).data,
        }, status=status.HTTP_200_OK)
