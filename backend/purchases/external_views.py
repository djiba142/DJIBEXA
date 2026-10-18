from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.idempotency import execute_idempotent_request
from core.tenancy import tenant_scoped_queryset
from sales.serializers import SaleSerializer
from users.permissions import (
    IsAdminUser,
    IsTenantAssignedUser,
    PurchaseOrderAccessPermission,
    StockOperationsMutationPermission,
    role_permission,
)

from .external_serializers import (
    ExternalPurchaseMovementSerializer,
    ExternalPurchasePaymentCreateSerializer,
    ExternalPurchasePaymentSerializer,
    ExternalPurchaseSerializer,
    ExternalSalePurchaseCreateSerializer,
)
from .models import (
    ExternalPurchase,
    ExternalPurchaseMovement,
    ExternalPurchasePayment,
    ExternalPurchasePaymentAllocation,
)


def external_purchase_queryset(user):
    queryset = tenant_scoped_queryset(
        ExternalPurchase.objects.select_related(
            'supplier',
            'sale__invoice',
            'sale_item__product',
        ).annotate(
            calculated_total_cost=ExpressionWrapper(
                F('quantity') * F('unit_cost') + F('additional_cost'),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
            calculated_paid=Coalesce(
                Sum(
                    'payment_allocations__amount',
                    filter=Q(
                        payment_allocations__payment__financial_transaction__status='validated',
                    ),
                ),
                Value(Decimal('0')),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
        ),
        user,
    )
    return queryset


class ExternalSalePurchaseCreateView(generics.GenericAPIView):
    serializer_class = ExternalSalePurchaseCreateSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
        role_permission('purchases'),
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        def create_external_sale_and_purchases():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            sale, purchases = serializer.save()
            return Response(
                {
                    'sale': SaleSerializer(
                        sale,
                        context=self.get_serializer_context(),
                    ).data,
                    'purchases': ExternalPurchaseSerializer(
                        purchases,
                        many=True,
                        context=self.get_serializer_context(),
                    ).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return execute_idempotent_request(
            request,
            request.path,
            create_external_sale_and_purchases,
        )


class ExternalPurchaseListView(generics.ListAPIView):
    serializer_class = ExternalPurchaseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseOrderAccessPermission,
    ]

    def get_queryset(self):
        queryset = external_purchase_queryset(self.request.user)
        supplier_id = self.request.query_params.get('supplier')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        payment_status = self.request.query_params.get('payment_status')
        if payment_status == 'paid':
            queryset = queryset.filter(
                calculated_paid__gte=F('calculated_total_cost'),
            )
        elif payment_status == 'partial':
            queryset = queryset.filter(
                calculated_paid__gt=0,
                calculated_paid__lt=F('calculated_total_cost'),
            )
        elif payment_status == 'unpaid':
            queryset = queryset.filter(calculated_paid=0)
        return queryset


class ExternalPurchaseSummaryView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseOrderAccessPermission,
    ]

    def get(self, request, *args, **kwargs):
        queryset = external_purchase_queryset(request.user).filter(status='confirmed')
        supplier_id = request.query_params.get('supplier')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        summary = queryset.aggregate(
            purchase_total=Coalesce(
                Sum('calculated_total_cost'),
                Value(Decimal('0')),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
            total_paid=Coalesce(
                Sum('calculated_paid'),
                Value(Decimal('0')),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
        )
        return Response({
            'purchase_total': summary['purchase_total'],
            'total_paid': summary['total_paid'],
            'balance_due': max(
                summary['purchase_total'] - summary['total_paid'],
                Decimal('0'),
            ),
            'purchase_count': queryset.count(),
        })


class ExternalPurchasePaymentListCreateView(generics.ListCreateAPIView):
    serializer_class = ExternalPurchasePaymentSerializer
    queryset = ExternalPurchasePayment.objects.select_related(
        'supplier',
        'financial_account',
        'financial_transaction',
        'created_by',
    ).prefetch_related('allocations__purchase')
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('purchases'),
    ]

    def get_permissions(self):
        permissions_list = super().get_permissions()
        if self.request.method == 'POST':
            permissions_list.append(IsAdminUser())
        return permissions_list

    def get_queryset(self):
        queryset = tenant_scoped_queryset(super().get_queryset(), self.request.user)
        supplier_id = self.request.query_params.get('supplier')
        return queryset.filter(supplier_id=supplier_id) if supplier_id else queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ExternalPurchasePaymentCreateSerializer
        return self.serializer_class

    def create(self, request, *args, **kwargs):
        def create_supplier_payment():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            payment = serializer.save()
            response = ExternalPurchasePaymentSerializer(
                payment,
                context=self.get_serializer_context(),
            )
            return Response(response.data, status=status.HTTP_201_CREATED)

        return execute_idempotent_request(
            request,
            request.path,
            create_supplier_payment,
        )


class ExternalPurchaseMovementListCreateView(generics.ListCreateAPIView):
    serializer_class = ExternalPurchaseMovementSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockOperationsMutationPermission,
    ]

    def get_purchase(self):
        return get_object_or_404(
            tenant_scoped_queryset(
                ExternalPurchase.objects.all(),
                self.request.user,
            ),
            pk=self.kwargs['purchase_id'],
        )

    def get_queryset(self):
        return tenant_scoped_queryset(
            ExternalPurchaseMovement.objects.select_related(
                'purchase',
                'location',
                'created_by',
            ).filter(purchase_id=self.kwargs['purchase_id']),
            self.request.user,
            tenant_field='purchase__tenant',
        )

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            'purchase': self.get_purchase(),
        }

    def perform_create(self, serializer):
        serializer.save()


class ExternalPurchaseCancelView(generics.GenericAPIView):
    queryset = ExternalPurchase.objects.select_related('sale')
    serializer_class = ExternalPurchaseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsAdminUser,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        purchase = get_object_or_404(
            tenant_scoped_queryset(
                ExternalPurchase.objects.select_for_update().select_related('sale'),
                request.user,
            ),
            pk=kwargs['pk'],
        )
        if purchase.status == 'cancelled':
            return Response(
                {'detail': 'Cet achat externe est déjà annulé.'},
                status=status.HTTP_409_CONFLICT,
            )
        if purchase.sale.status != 'cancelled':
            raise PermissionDenied(
                'Annulez d’abord la vente client via le processus de vente existant.',
            )
        if (
            ExternalPurchasePaymentAllocation.objects.filter(purchase=purchase).exists()
            or ExternalPurchaseMovement.objects.filter(purchase=purchase).exists()
        ):
            return Response(
                {'detail': 'Un achat payé ou physiquement traité ne peut pas être annulé.'},
                status=status.HTTP_409_CONFLICT,
            )
        purchase.status = 'cancelled'
        purchase.save(update_fields=['status', 'updated_at'])
        return Response(
            ExternalPurchaseSerializer(
                purchase,
                context={'request': request},
            ).data,
            status=status.HTTP_200_OK,
        )
