from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate, TruncDay, TruncMonth, TruncQuarter, TruncWeek, TruncYear
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from customers.models import Customer
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from expenses.models import Expense
from inventory.access import accessible_locations
from inventory.models import Carton, InventoryCount, InventoryLocation, StockItem, StockMovement
from payments.models import Payment, PaymentAllocation
from purchases.models import (
    ExternalPurchase,
    ExternalPurchasePaymentAllocation,
    PurchaseOrder,
    PurchaseReceipt,
    PurchaseReceiptItem,
)
from products.models import Product
from sales.models import (
    CustomerOrder,
    Invoice,
    Sale,
    SaleItem,
    SaleReturnItem,
    SaleReturnQuarantine,
)
from suppliers.models import Supplier
from users.permissions import (
    IsAdminUser,
    DashboardOverviewAccessPermission,
    IsTenantAssignedUser,
    SalesReportAccessPermission,
    SensitiveMutationPermission,
    role_permission,
)
from .models import AppSetting, AuditLog, Company
from .models import Partner
from .partner_serializers import PartnerSerializer
from .serializers import AppSettingSerializer, AuditLogSerializer, CompanySerializer, JsonResponseSerializer


def _get_date_range(request, date_field='sale_date'):
    start_value = request.query_params.get('start_date') or request.query_params.get('date_from') or request.query_params.get('start')
    end_value = request.query_params.get('end_date') or request.query_params.get('date_to') or request.query_params.get('end')

    if not start_value and not end_value:
        return None, None

    start_dt = parse_date(start_value) if start_value else None
    end_dt = parse_date(end_value) if end_value else None
    if start_value and start_dt is None:
        raise ValidationError({'start_date': 'Format invalide; utilisez AAAA-MM-JJ.'})
    if end_value and end_dt is None:
        raise ValidationError({'end_date': 'Format invalide; utilisez AAAA-MM-JJ.'})

    if start_dt is not None:
        start_boundary = datetime.combine(start_dt, time.min)
        if timezone.is_naive(start_boundary):
            start_boundary = timezone.make_aware(start_boundary)
    else:
        start_boundary = None

    if end_dt is not None:
        end_boundary = datetime.combine(end_dt, time.max)
        if timezone.is_naive(end_boundary):
            end_boundary = timezone.make_aware(end_boundary)
    else:
        end_boundary = None

    if start_boundary and end_boundary and end_boundary < start_boundary:
        start_boundary, end_boundary = end_boundary, start_boundary

    return start_boundary, end_boundary


def _get_integer_parameter(request, name, default=None, minimum=1, maximum=None):
    value = request.query_params.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: 'Une valeur entière valide est requise.'}) from None
    if parsed < minimum or maximum is not None and parsed > maximum:
        bounds = f'entre {minimum} et {maximum}' if maximum is not None else f'au moins {minimum}'
        raise ValidationError({name: f'La valeur doit être {bounds}.'})
    return parsed


def _apply_date_range(queryset, request, field_name):
    start_boundary, end_boundary = _get_date_range(request)
    if start_boundary:
        queryset = queryset.filter(**{f'{field_name}__gte': start_boundary})
    if end_boundary:
        queryset = queryset.filter(**{f'{field_name}__lte': end_boundary})
    return queryset


def _inventory_health_metrics(
    product_queryset=None,
    include_financials=True,
    stock_locations=None,
):
    product_fields = ['id', 'name', 'sku', 'alert_threshold']
    if stock_locations is None:
        product_fields.append('quantity')
    if include_financials:
        product_fields.extend(['cost_price', 'selling_price'])
    if product_queryset is None:
        product_queryset = Product.objects.filter(is_active=True)
    products = list(product_queryset.values(*product_fields))
    if stock_locations is not None:
        stock_by_product = dict(
            StockItem.objects.filter(
                product_id__in=[product['id'] for product in products],
                location__in=stock_locations,
            )
            .values('product_id')
            .annotate(quantity=Sum('quantity'))
            .values_list('product_id', 'quantity')
        )
        for product in products:
            product['quantity'] = stock_by_product.get(product['id'], 0)

    total_stock_items = sum(int(product['quantity'] or 0) for product in products)
    low_stock_products = sum(
        1 for product in products
        if int(product['quantity'] or 0) <= int(product['alert_threshold'] or 0)
    )
    healthy_products = sum(
        1 for product in products
        if int(product['quantity'] or 0) > int(product['alert_threshold'] or 0)
    )

    inventory_value = Decimal('0')
    margin_values = []
    low_margin_products = []
    known_cost_products = 0
    if include_financials:
        for product in products:
            quantity = Decimal(str(product['quantity'] or 0))
            cost_price = Decimal(str(product['cost_price'] or 0))
            selling_price = Decimal(str(product['selling_price'] or 0))
            inventory_value += quantity * cost_price

            if cost_price > 0:
                known_cost_products += 1
                margin_percent = ((selling_price - cost_price) / cost_price) * Decimal('100')
                margin_values.append(float(margin_percent))
                low_margin_products.append({
                    'id': product['id'],
                    'name': product['name'],
                    'sku': product['sku'],
                    'quantity': product['quantity'],
                    'cost_price': float(cost_price),
                    'selling_price': float(selling_price),
                    'margin_percent': float(margin_percent),
                })

    metrics: dict[str, object] = {
        'total_stock_items': total_stock_items,
        'low_stock_products': low_stock_products,
        'healthy_products': healthy_products,
    }
    if include_financials:
        products_with_missing_cost = len(products) - known_cost_products
        metrics.update({
            'inventory_value': float(inventory_value),
            'average_margin_percent': round(
                sum(margin_values) / len(margin_values), 2,
            ) if margin_values else 0,
            'low_margin_products': sorted(
                low_margin_products,
                key=lambda item: item['margin_percent'],
            )[:5],
            'financial_data_quality': {
                'cost_basis': 'current_product_cost_price',
                'historical_profitability_available': False,
                'products_with_cost': known_cost_products,
                'products_missing_cost': products_with_missing_cost,
                'cost_coverage_percent': round(
                    known_cost_products / len(products) * 100, 2,
                ) if products else 0,
            },
        })
    return metrics


@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})


class AuditLogListView(generics.ListAPIView):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, role_permission('core')]


class AppSettingListCreateView(generics.ListCreateAPIView):
    queryset = AppSetting.objects.all()
    serializer_class = AppSettingSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app_setting = serializer.save()
        AuditLog.objects.create(
            user=request.user,
            action='create',
            model_name='AppSetting',
            record_id=app_setting.id,
            details=f"Paramètre créé: {app_setting.key}",
        )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class AppSettingDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = AppSetting.objects.all()
    serializer_class = AppSettingSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser, SensitiveMutationPermission]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        app_setting = serializer.save()
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='AppSetting',
            record_id=app_setting.id,
            details=f"Paramètre mis à jour: {app_setting.key}",
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        app_setting_key = instance.key
        self.perform_destroy(instance)
        AuditLog.objects.create(
            user=request.user,
            action='delete',
            model_name='AppSetting',
            record_id=instance.id,
            details=f"Paramètre supprimé: {app_setting_key}",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompanyView(generics.RetrieveUpdateAPIView):
    serializer_class = CompanySerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('core'),
        SensitiveMutationPermission,
    ]

    def get_object(self):
        tenant = tenant_for_user(self.request.user)
        company, _ = Company.objects.get_or_create(
            tenant=tenant,
            defaults={'name': tenant.name or 'DJIBEXA'},
        )
        return company

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        company = serializer.save()
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='Company',
            record_id=company.id,
            details=f"Profil société mis à jour: {company.name}",
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class PartnerListView(generics.ListAPIView):
    queryset = Partner.objects.filter(active=True)
    serializer_class = PartnerSerializer
    permission_classes = [permissions.IsAuthenticated, role_permission('core')]

    def get_queryset(self):
        queryset = super().get_queryset()
        surface = self.request.query_params.get('surface')
        if surface == 'invoice':
            return queryset.filter(show_on_invoice=True)
        if surface == 'orders':
            return queryset.filter(show_on_orders=True)
        return queryset


class PartnerManageListView(generics.ListCreateAPIView):
    queryset = Partner.objects.all()
    serializer_class = PartnerSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]


class PartnerManageDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Partner.objects.all()
    serializer_class = PartnerSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser, SensitiveMutationPermission]

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'La suppression physique d’un partenaire est interdite. Désactivez-le à la place.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class DashboardSummaryView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('core'),
    ]

    def get(self, request, *args, **kwargs):
        sales_queryset = _apply_date_range(
            tenant_scoped_queryset(Sale.objects.all(), request.user),
            request,
            'sale_date',
        )
        payments_queryset = _tenant_cash_payments(request)

        products = tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            request.user,
        )
        total_products = products.count()
        total_customers = tenant_scoped_queryset(
            Customer.objects.filter(is_active=True),
            request.user,
        ).count()
        total_sales = sales_queryset.aggregate(total=Sum('total_amount'))['total'] or 0
        total_received = payments_queryset.aggregate(total=Sum('amount'))['total'] or 0
        total_open_balance = float(total_sales) - float(total_received)
        low_stock_products = products.filter(
            quantity__lte=F('alert_threshold'),
        ).count()

        summary = {
            'total_products': total_products,
            'total_customers': total_customers,
            'total_sales': float(total_sales),
            'total_received': float(total_received),
            'outstanding_balance': float(total_open_balance),
            'low_stock_products': low_stock_products,
            'total_stock_items': products.aggregate(total=Sum('quantity'))['total'] or 0,
        }
        return Response(summary, status=status.HTTP_200_OK)


class DashboardOverviewView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        DashboardOverviewAccessPermission,
    ]

    def get(self, request, *args, **kwargs):
        user = request.user
        is_sales_user = user.has_role('sales') and not user.has_role('admin')
        today = timezone.localdate()
        start_boundary = timezone.make_aware(datetime.combine(today, time.min))
        end_boundary = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
        can_view_sales = user.has_any_role('admin', 'sales')
        can_view_operations = user.has_any_role('admin', 'stock')
        can_review_returns = user.has_role('admin')

        locations = tenant_scoped_queryset(
            InventoryLocation.objects.filter(is_active=True),
            user,
        )
        if is_sales_user and not user.has_role('stock'):
            locations = locations.filter(location_type='shop')
        if not user.has_role('admin') and user.has_any_role('sales', 'stock') and locations.filter(
            authorized_users__isnull=False,
        ).exists():
            locations = locations.filter(authorized_users=request.user)
        location_ids = locations.values_list('id', flat=True)

        products = tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            user,
        )
        stock_filter = Q(stock_items__location__in=location_ids)
        products = products.annotate(
            dashboard_stock=Sum('stock_items__quantity', filter=stock_filter),
        )
        low_stock_products = products.filter(
            dashboard_stock__lte=F('alert_threshold'),
        ).order_by('dashboard_stock', 'name')
        low_stock = [
            {
                'id': product.id,
                'name': product.name,
                'reference': product.sku,
                'stock': product.dashboard_stock or 0,
                'threshold': product.alert_threshold,
            }
            for product in low_stock_products[:8]
        ]

        response_data = {
            'date': today.isoformat(),
            'timezone': timezone.get_current_timezone_name(),
            'currency': 'GNF',
            'stock_alert_count': low_stock_products.count(),
            'out_of_stock_count': low_stock_products.filter(dashboard_stock__lte=0).count(),
            'low_stock': low_stock,
            'pending_receipts': None,
            'draft_receipts': None,
            'pending_inventory_counts': None,
            'pending_return_quarantines': None,
            'sales_amount': None,
            'sales_count': None,
            'collected_amount': None,
            'returned_amount': None,
            'sold_references': None,
            'recent_sales': [],
            'sales_trend': None,
            'pending_customer_quotes': None,
            'confirmed_customer_orders': None,
        }

        if can_view_operations:
            receipts = PurchaseReceipt.objects.filter(location__in=location_ids)
            response_data.update({
                'pending_receipts': receipts.filter(
                    status__in=['submitted', 'on_hold'],
                ).count(),
                'draft_receipts': receipts.filter(status='draft').count(),
                'pending_inventory_counts': InventoryCount.objects.filter(
                    location__in=location_ids,
                    status='submitted',
                ).count(),
            })
        if can_review_returns:
            customer_orders = tenant_scoped_queryset(
                CustomerOrder.objects.all(),
                user,
            )
            response_data.update({
                'pending_customer_quotes': customer_orders.filter(status='quote').count(),
                'confirmed_customer_orders': customer_orders.filter(
                    status='confirmed',
                ).count(),
            })
            return_quarantines = SaleReturnQuarantine.objects.filter(
                status='pending',
                quantity_remaining__gt=0,
            ).select_related(
                'return_item__sale_return__sale__invoice',
                'return_item__sale_item__product',
                'location',
            )
            return_quarantines = tenant_scoped_queryset(
                return_quarantines,
                user,
                tenant_field='location__tenant',
            )
            response_data['pending_return_quarantines'] = return_quarantines.count()
            response_data['pending_return_items'] = [
                {
                    'id': quarantine.id,
                    'sale_id': quarantine.return_item.sale_return.sale_id,
                    'invoice_number': (
                        quarantine.return_item.sale_return.sale.invoice.invoice_number
                        if hasattr(quarantine.return_item.sale_return.sale, 'invoice')
                        else None
                    ),
                    'product_name': quarantine.return_item.sale_item.product.name,
                    'location_name': quarantine.location.name,
                    'quantity_remaining': quarantine.quantity_remaining,
                    'reason': quarantine.reason,
                }
                for quarantine in return_quarantines.order_by('created_at', 'id')[:5]
            ]

        if can_view_sales:
            sales = tenant_scoped_queryset(
                Sale.objects.filter(
                    sale_date__gte=start_boundary,
                    sale_date__lt=end_boundary,
                    status__in=['paid', 'partial'],
                ),
                user,
            )
            if is_sales_user:
                sales = sales.filter(seller=request.user)
            sales = sales.select_related('customer', 'invoice').order_by('-sale_date')
            sale_ids = sales.values_list('id', flat=True)
            return_totals = SaleReturnItem.objects.filter(
                sale_item__sale_id__in=sale_ids,
            ).aggregate(
                amount=Sum('revenue_total'),
                quantity=Sum('quantity'),
            )
            sold_references = SaleItem.objects.filter(
                sale_id__in=sale_ids,
            ).values('product_id').distinct().count()

            recent_sales = list(sales[:6])
            recent_return_totals = {
                row['sale_item__sale_id']: row['amount'] or Decimal('0.00')
                for row in SaleReturnItem.objects.filter(
                    sale_item__sale_id__in=[sale.id for sale in recent_sales],
                ).values('sale_item__sale_id').annotate(amount=Sum('revenue_total'))
            }
            response_data.update({
                'sales_amount': float(
                    (sales.aggregate(amount=Sum('total_amount'))['amount'] or Decimal('0.00'))
                    - (return_totals['amount'] or Decimal('0.00'))
                ),
                'sales_count': sales.count(),
                'returned_amount': float(return_totals['amount'] or Decimal('0.00')),
                'sold_references': sold_references,
                'recent_sales': [
                    {
                        'id': sale.id,
                        'invoice_number': sale.invoice.invoice_number if hasattr(sale, 'invoice') else None,
                        'customer_name': sale.customer.full_name if sale.customer_id else '',
                        'sale_date': sale.sale_date.isoformat(),
                        'status': sale.status,
                        'amount': float(
                            sale.total_amount - recent_return_totals.get(sale.id, Decimal('0.00'))
                        ),
                    }
                    for sale in recent_sales
                ],
            })

            trend_start_day = today - timedelta(days=6)
            trend_start = timezone.make_aware(datetime.combine(trend_start_day, time.min))
            trend_sales = tenant_scoped_queryset(
                Sale.objects.filter(
                    sale_date__gte=trend_start,
                    sale_date__lt=end_boundary,
                ).exclude(status__in=['draft', 'cancelled']),
                user,
            )
            if is_sales_user:
                trend_sales = trend_sales.filter(seller=user)
            trend_day = TruncDate('sale_date', tzinfo=timezone.get_current_timezone())
            daily_sales = {
                row['day'].isoformat(): {
                    'sales': row['amount'] or Decimal('0.00'),
                    'sales_count': row['count'],
                }
                for row in trend_sales.annotate(day=trend_day).values('day').annotate(
                    amount=Sum('total_amount'),
                    count=Count('id'),
                )
            }
            daily_returns = {
                row['day'].isoformat(): row['amount'] or Decimal('0.00')
                for row in SaleReturnItem.objects.filter(
                    sale_item__sale_id__in=trend_sales.values('id'),
                ).annotate(day=TruncDate(
                    'sale_item__sale__sale_date',
                    tzinfo=timezone.get_current_timezone(),
                )).values('day').annotate(amount=Sum('revenue_total'))
            }
            trend = []
            for offset in range(7):
                day = trend_start_day + timedelta(days=offset)
                day_key = day.isoformat()
                day_sales = daily_sales.get(day_key, {})
                trend.append({
                    'date': day_key,
                    'sales': float(
                        day_sales.get('sales', Decimal('0.00'))
                        - daily_returns.get(day_key, Decimal('0.00'))
                    ),
                    'sales_count': day_sales.get('sales_count', 0),
                })
            response_data['sales_trend'] = trend

            payments = _tenant_cash_payments(request).filter(
                Q(sale__isnull=True) | Q(sale__status__in=['paid', 'partial']),
                payment_date__gte=start_boundary,
                payment_date__lt=end_boundary,
            )
            if is_sales_user:
                payments = payments.filter(sale__seller=request.user)
            response_data['collected_amount'] = float(
                payments.aggregate(amount=Sum('amount'))['amount'] or Decimal('0.00')
            )

        return Response(response_data, status=status.HTTP_200_OK)


class AdvancedReportingView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SalesReportAccessPermission,
    ]

    def get(self, request, *args, **kwargs):
        start_boundary, end_boundary = _get_date_range(request)
        is_sales_user = request.user.has_role('sales') and not request.user.has_role('admin')
        can_view_financial_costs = (
            request.user.has_role('admin')
            or getattr(request.user, 'is_superuser', False)
        )
        period = request.query_params.get('period', 'month').lower()
        period_functions = {
            'day': TruncDay,
            'week': TruncWeek,
            'month': TruncMonth,
            'quarter': TruncQuarter,
            'year': TruncYear,
        }
        if period not in period_functions:
            return Response(
                {'period': 'Valeur invalide. Choisissez day, week, month, quarter ou year.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        period_function = period_functions[period]
        customer_id = _get_integer_parameter(request, 'customer')
        product_id = _get_integer_parameter(request, 'product')
        category_id = _get_integer_parameter(request, 'category')
        location_id = _get_integer_parameter(request, 'location')
        seller_id = _get_integer_parameter(request, 'seller')
        customer_search = request.query_params.get('customer_search', '').strip()
        product_search = request.query_params.get('product_search', '').strip()
        category_search = request.query_params.get('category_search', '').strip()
        location_search = request.query_params.get('location_search', '').strip()
        seller_search = request.query_params.get('seller_search', '').strip()
        payment_method = request.query_params.get('payment_method', '').strip()

        sales_queryset = tenant_scoped_queryset(
            Sale.objects.select_related('customer').exclude(
                status__in=['draft', 'cancelled'],
            ),
            request.user,
        )
        if start_boundary:
            sales_queryset = sales_queryset.filter(sale_date__gte=start_boundary)
        if end_boundary:
            sales_queryset = sales_queryset.filter(sale_date__lte=end_boundary)
        if is_sales_user:
            sales_queryset = sales_queryset.filter(seller_id=request.user.id)
        if customer_id:
            sales_queryset = sales_queryset.filter(customer_id=customer_id)
        if customer_search:
            sales_queryset = sales_queryset.filter(
                Q(customer__full_name__icontains=customer_search)
                | Q(customer__phone__icontains=customer_search)
            )
        if seller_id and not is_sales_user:
            sales_queryset = sales_queryset.filter(seller_id=seller_id)
        if seller_search:
            sales_queryset = sales_queryset.filter(
                Q(seller__first_name__icontains=seller_search)
                | Q(seller__last_name__icontains=seller_search)
                | Q(seller__username__icontains=seller_search)
            )
        if location_id:
            sales_queryset = sales_queryset.filter(location_id=location_id)
        if location_search:
            sales_queryset = sales_queryset.filter(
                location__name__icontains=location_search,
            )
        if payment_method:
            if payment_method not in dict(Sale.PAYMENT_CHOICES):
                raise ValidationError({
                    'payment_method': 'Mode de paiement invalide.',
                })
            sales_queryset = sales_queryset.filter(payment_method=payment_method)
        if product_id:
            sales_queryset = sales_queryset.filter(items__product_id=product_id).distinct()
        if product_search:
            sales_queryset = sales_queryset.filter(
                Q(items__product__name__icontains=product_search)
                | Q(items__product__sku__icontains=product_search)
            ).distinct()
        if category_id:
            sales_queryset = sales_queryset.filter(items__product__category_id=category_id).distinct()
        if category_search:
            sales_queryset = sales_queryset.filter(
                items__product__category__name__icontains=category_search,
            ).distinct()

        sale_ids = list(sales_queryset.values_list('id', flat=True))

        sales_aggregates = sales_queryset.aggregate(
            total_discount=Sum('discount'),
            sale_count=Count('id'),
        )
        sale_rows = list(sales_queryset.values(
            'id',
            'total_amount',
            'amount_paid',
            'seller_id',
            'seller__first_name',
            'seller__last_name',
            'seller__username',
            'location_id',
            'location__name',
            'location__location_type',
            'payment_method',
            'status',
            'customer_id',
            'customer__full_name',
            'sale_date',
        ))
        returned_by_sale = {
            row['sale_item__sale_id']: row
            for row in SaleReturnItem.objects.filter(
                sale_item__sale_id__in=sale_ids,
            ).values('sale_item__sale_id').annotate(
                returned_amount=Sum('revenue_total'),
                returned_gross=Sum('gross_revenue_total'),
                returned_quantity=Sum('quantity'),
                returned_cost=Sum('cost_total'),
            )
        }
        sale_net_amounts = {
            row['id']: Decimal(row['total_amount'])
            - (returned_by_sale.get(row['id'], {}).get('returned_amount') or Decimal('0.00'))
            for row in sale_rows
        }
        total_sales = sum(sale_net_amounts.values(), Decimal('0.00'))
        total_returned_amount = sum(
            (row.get('returned_amount') or Decimal('0.00') for row in returned_by_sale.values()),
            Decimal('0.00'),
        )
        total_returned_quantity = sum(
            row.get('returned_quantity') or 0 for row in returned_by_sale.values()
        )
        payment_allocations = PaymentAllocation.objects.filter(sale_id__in=sale_ids)
        payments_without_allocations = Payment.objects.filter(
            sale_id__in=sale_ids,
            allocations__isnull=True,
        )
        if start_boundary:
            payment_allocations = payment_allocations.filter(
                payment__payment_date__gte=start_boundary,
            )
            payments_without_allocations = payments_without_allocations.filter(
                payment_date__gte=start_boundary,
            )
        if end_boundary:
            payment_allocations = payment_allocations.filter(
                payment__payment_date__lte=end_boundary,
            )
            payments_without_allocations = payments_without_allocations.filter(
                payment_date__lte=end_boundary,
            )
        total_received = (
            payment_allocations.aggregate(total=Sum('amount'))['total'] or 0
        ) + (
            payments_without_allocations.aggregate(total=Sum('amount'))['total'] or 0
        )
        outstanding_balance = sum(
            (
                max(
                    sale_net_amounts[row['id']] - Decimal(row['amount_paid']),
                    Decimal('0.00'),
                )
                for row in sale_rows
            ),
            Decimal('0.00'),
        )
        total_customers = sales_queryset.values('customer').distinct().count()
        product_queryset = tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            request.user,
        )
        if product_id:
            product_queryset = product_queryset.filter(id=product_id)
        if category_id:
            product_queryset = product_queryset.filter(category_id=category_id)
        total_products = product_queryset.count()

        product_sales = SaleItem.objects.filter(sale_id__in=sale_ids)
        if product_id:
            product_sales = product_sales.filter(product_id=product_id)
        if product_search:
            product_sales = product_sales.filter(
                Q(product__name__icontains=product_search)
                | Q(product__sku__icontains=product_search)
            )
        if category_id:
            product_sales = product_sales.filter(product__category_id=category_id)
        if category_search:
            product_sales = product_sales.filter(
                product__category__name__icontains=category_search,
            )
        return_items = SaleReturnItem.objects.filter(sale_item__sale_id__in=sale_ids)
        if product_id:
            return_items = return_items.filter(sale_item__product_id=product_id)
        if product_search:
            return_items = return_items.filter(
                Q(sale_item__product__name__icontains=product_search)
                | Q(sale_item__product__sku__icontains=product_search)
            )
        if category_id:
            return_items = return_items.filter(sale_item__product__category_id=category_id)
        if category_search:
            return_items = return_items.filter(
                sale_item__product__category__name__icontains=category_search,
            )
        returned_product_totals = {
            row['sale_item__product_id']: row
            for row in return_items.values('sale_item__product_id').annotate(
                quantity=Sum('quantity'),
                gross_revenue=Sum('gross_revenue_total'),
            )
        }
        base_quantity_sold = product_sales.aggregate(
            quantity=Sum('quantity'),
        )['quantity'] or 0
        returned_quantity_sold = sum(
            row['quantity'] or 0 for row in returned_product_totals.values()
        )
        total_quantity_sold = base_quantity_sold - returned_quantity_sold
        product_sales = list(
            product_sales.values(
                'product_id',
                'product__name',
                'product__sku',
                'product__quantity',
                'product__selling_price',
            )
            .annotate(
                quantity_sold=Sum('quantity'),
                revenue=Sum(ExpressionWrapper(
                    F('quantity') * F('unit_price'),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )),
            )
            .order_by('-revenue')
        )
        for item in product_sales:
            returned_product = returned_product_totals.get(item['product_id'], {})
            item['quantity_sold'] -= returned_product.get('quantity') or 0
            item['revenue'] -= returned_product.get('gross_revenue') or Decimal('0.00')
        product_sales = sorted(
            (item for item in product_sales if item['quantity_sold'] > 0),
            key=lambda item: item['revenue'],
            reverse=True,
        )[:5]
        top_products = [
            {
                'id': item['product_id'],
                'name': item['product__name'],
                'sku': item['product__sku'],
                'quantity': item['product__quantity'],
                'selling_price': item['product__selling_price'],
                'quantity_sold': item['quantity_sold'],
                'revenue': item['revenue'],
            }
            for item in product_sales
        ]

        def breakdown(fields):
            groups = {}
            for sale_row in sale_rows:
                key = tuple(sale_row[field] for field in fields)
                if key not in groups:
                    groups[key] = {
                        **{field: sale_row[field] for field in fields},
                        'sale_count': 0,
                        'total_sales': Decimal('0.00'),
                    }
                groups[key]['sale_count'] += 1
                groups[key]['total_sales'] += sale_net_amounts[sale_row['id']]
            return sorted(
                groups.values(),
                key=lambda entry: entry['total_sales'],
                reverse=True,
            )

        customer_breakdown = breakdown(['customer_id', 'customer__full_name'])[:10]
        seller_breakdown = breakdown([
            'seller_id',
            'seller__first_name',
            'seller__last_name',
            'seller__username',
        ])[:20]
        for seller in seller_breakdown:
            first_name = seller.pop('seller__first_name') or ''
            last_name = seller.pop('seller__last_name') or ''
            username = seller.pop('seller__username') or ''
            seller['seller_name'] = f'{first_name} {last_name}'.strip() or username
            seller['total_sales'] = float(seller['total_sales'] or 0)
        location_breakdown = breakdown([
            'location_id',
            'location__name',
            'location__location_type',
        ])
        for location in location_breakdown:
            location['location_name'] = location.pop('location__name')
            location['location_type'] = location.pop('location__location_type')
            location['total_sales'] = float(location['total_sales'] or 0)
        sales_by_payment_method = breakdown(['payment_method'])
        for entry in sales_by_payment_method:
            entry['total_sales'] = float(entry['total_sales'] or 0)
        sales_by_status = breakdown(['status'])
        for entry in sales_by_status:
            entry['total_sales'] = float(entry['total_sales'] or 0)
        for customer in customer_breakdown:
            customer['total_sales'] = float(customer['total_sales'] or 0)

        inventory_status = _inventory_health_metrics(
            product_queryset,
            include_financials=can_view_financial_costs,
            stock_locations=(
                accessible_locations(request.user).filter(
                    is_active=True,
                    location_type='shop',
                )
                if is_sales_user else None
            ),
        )

        trend_start = start_boundary or (
            end_boundary - timedelta(days=365) if end_boundary else timezone.now() - timedelta(days=365)
        )
        trend_sales_queryset = Sale.objects.filter(id__in=sale_ids, sale_date__gte=trend_start)
        trend_allocations_queryset = payment_allocations.filter(
            payment__payment_date__gte=trend_start,
        )
        trend_unallocated_payments = payments_without_allocations.filter(
            payment_date__gte=trend_start,
        )
        sales_trend = {
            entry['period']: {
                'period': entry['period'].isoformat(),
                'sales': float(entry['sales'] or 0),
                'sales_count': entry['sales_count'],
                'received': 0.0,
            }
            for entry in trend_sales_queryset.annotate(
                period=period_function('sale_date', tzinfo=timezone.get_current_timezone()),
            ).values('period').annotate(
                sales=Sum('total_amount'),
                sales_count=Count('id'),
            ).order_by('period')
        }
        for entry in trend_sales_queryset.annotate(
            period=period_function('sale_date', tzinfo=timezone.get_current_timezone()),
        ).values('id', 'period'):
            if entry['period'] in sales_trend:
                sales_trend[entry['period']]['sales'] -= float(
                    returned_by_sale.get(entry['id'], {}).get('returned_amount') or 0
                )
        for entry in trend_allocations_queryset.annotate(
            period=period_function(
                'payment__payment_date',
                tzinfo=timezone.get_current_timezone(),
            ),
        ).values('period').annotate(
            received=Sum('amount'),
        ).order_by('period'):
            period_key = entry['period']
            sales_trend.setdefault(period_key, {
                'period': period_key.isoformat(),
                'sales': 0.0,
                'sales_count': 0,
                'received': 0.0,
            })
            sales_trend[period_key]['received'] = float(entry['received'] or 0)
        for entry in trend_unallocated_payments.annotate(
            period=period_function('payment_date', tzinfo=timezone.get_current_timezone()),
        ).values('period').annotate(
            received=Sum('amount'),
        ).order_by('period'):
            period_key = entry['period']
            sales_trend.setdefault(period_key, {
                'period': period_key.isoformat(),
                'sales': 0.0,
                'sales_count': 0,
                'received': 0.0,
            })
            sales_trend[period_key]['received'] += float(entry['received'] or 0)
        sales_trend = sorted(sales_trend.values(), key=lambda entry: entry['period'])

        summary = {
            'total_sales': float(total_sales),
            'total_received': float(total_received),
            'outstanding_balance': float(outstanding_balance),
            'returned_amount': float(total_returned_amount),
            'returned_quantity': total_returned_quantity,
            'sales_count': sales_aggregates['sale_count'],
            'total_quantity_sold': total_quantity_sold,
            'average_basket': (
                float(total_sales / sales_aggregates['sale_count'])
                if sales_aggregates['sale_count'] else 0
            ),
            'total_discount': float(sales_aggregates['total_discount'] or 0),
            'total_customers': total_customers,
            'total_products': total_products,
        }
        if can_view_financial_costs:
            cost_summary = SaleItem.objects.filter(
                sale_id__in=sale_ids,
            ).aggregate(
                total_cost=Sum('cost_total'),
                item_count=Count('id'),
                items_without_cost=Count('id', filter=Q(cost_total__isnull=True)),
            )
            returned_cost_summary = SaleReturnItem.objects.filter(
                sale_item__sale_id__in=sale_ids,
            ).aggregate(
                total_cost=Sum('cost_total'),
                items_without_cost=Count('id', filter=Q(cost_total__isnull=True)),
            )
            profitability_available = (
                cost_summary['item_count'] > 0
                and cost_summary['items_without_cost'] == 0
                and returned_cost_summary['items_without_cost'] == 0
            )
            total_cost = (
                cost_summary['total_cost'] or Decimal('0')
            ) - (
                returned_cost_summary['total_cost'] or Decimal('0')
            )
            gross_margin = Decimal(str(total_sales)) - total_cost
            summary['total_cost'] = float(total_cost) if profitability_available else None
            summary['gross_margin'] = float(gross_margin) if profitability_available else None
            summary['gross_margin_percent'] = (
                float(gross_margin / Decimal(str(total_sales)) * Decimal('100'))
                if profitability_available and total_sales else 0
            )
            summary['profitability'] = {
                'available': profitability_available,
                'reason': '' if profitability_available else (
                    'Le coût FIFO n’est pas disponible pour toutes les unités vendues '
                    'sur cette période.'
                ),
            }

        sales_by_period = [
            {'period': 'total_sales', 'value': float(total_sales)},
            {'period': 'received', 'value': float(total_received)},
            {'period': 'customers', 'value': float(total_customers)},
            {'period': 'products', 'value': float(total_products)},
        ]

        payload = {
            'summary': summary,
            'top_products': top_products,
            'sales_by_period': sales_by_period,
            'sales_trend': sales_trend,
            'trend_period': period,
            'sales_by_seller': seller_breakdown,
            'sales_by_location': location_breakdown,
            'sales_by_payment_method': sales_by_payment_method,
            'sales_by_status': sales_by_status,
            'customer_breakdown': customer_breakdown,
            'inventory_status': inventory_status,
        }
        return Response(payload, status=status.HTTP_200_OK)


class CoreReportingView(AdvancedReportingView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('core'),
    ]


class InventoryReportingView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
    ]

    def get(self, request, *args, **kwargs):
        from inventory.views import accessible_locations

        locations = accessible_locations(request.user)
        location_id = _get_integer_parameter(request, 'location')
        product_search = request.query_params.get('product_search', '').strip()
        category_search = request.query_params.get('category_search', '').strip()
        if location_id:
            locations = locations.filter(id=location_id)

        start_boundary, end_boundary = _get_date_range(request)
        period_days = _get_integer_parameter(request, 'period_days', default=90, maximum=365)
        period_end = end_boundary or timezone.now()
        period_start = start_boundary or period_end - timedelta(days=period_days - 1)
        effective_period_days = max(1, (period_end.date() - period_start.date()).days + 1)
        authorized_location_ids = list(locations.values_list('pk', flat=True))
        stock_items = tenant_scoped_queryset(
            StockItem.objects.filter(
                location_id__in=authorized_location_ids,
                product__is_active=True,
            ),
            request.user,
            tenant_field='product__tenant',
        ).select_related('product', 'location').order_by('product__name', 'location__name')
        if product_search:
            stock_items = stock_items.filter(
                Q(product__name__icontains=product_search)
                | Q(product__sku__icontains=product_search)
            )
        if category_search:
            stock_items = stock_items.filter(
                product__category__name__icontains=category_search,
            )
        stock_by_product = {}
        stock_by_location = {}
        total_units = 0
        for item in stock_items:
            product = item.product
            product_stock = stock_by_product.setdefault(product.id, {
                'product_id': product.id,
                'name': product.name,
                'sku': product.sku,
                'quantity': 0,
                'alert_threshold': product.alert_threshold,
                'locations': [],
            })
            product_stock['quantity'] += item.quantity
            product_stock['locations'].append({
                'location_id': item.location.pk,
                'location': item.location.name,
                'quantity': item.quantity,
            })
            location_stock = stock_by_location.setdefault(item.location.pk, {
                'location_id': item.location.pk,
                'location': item.location.name,
                'total_units': 0,
                'products': 0,
            })
            location_stock['total_units'] += item.quantity
            location_stock['products'] += 1
            total_units += item.quantity

        products = list(stock_by_product.values())
        products_in_scope = tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            request.user,
        )
        if product_search:
            products_in_scope = products_in_scope.filter(
                Q(name__icontains=product_search) | Q(sku__icontains=product_search)
            )
        if category_search:
            products_in_scope = products_in_scope.filter(
                category__name__icontains=category_search,
            )
        untracked_products_in_scope = products_in_scope.exclude(
            stock_items__location_id__in=authorized_location_ids,
        ).distinct().count()
        low_stock_products = [
            product for product in products
            if product['quantity'] <= product['alert_threshold']
        ]
        sold_items = SaleItem.objects.filter(
            sale__status__in=['paid', 'partial'],
            sale__sale_date__gte=period_start,
            sale__sale_date__lte=period_end,
            sale__location_id__in=authorized_location_ids,
            product__is_active=True,
        ).values('product_id').annotate(quantity_sold=Sum('quantity'))
        if product_search:
            sold_items = sold_items.filter(
                Q(product__name__icontains=product_search)
                | Q(product__sku__icontains=product_search)
            )
        if category_search:
            sold_items = sold_items.filter(
                product__category__name__icontains=category_search,
            )
        sales_by_product = {
            item['product_id']: item['quantity_sold'] or 0
            for item in sold_items
        }
        returned_items = SaleReturnItem.objects.filter(
            sale_item__sale__status__in=['paid', 'partial'],
            sale_item__sale__sale_date__gte=period_start,
            sale_item__sale__sale_date__lte=period_end,
            sale_item__sale__location_id__in=authorized_location_ids,
            sale_item__product__is_active=True,
        )
        if product_search:
            returned_items = returned_items.filter(
                Q(sale_item__product__name__icontains=product_search)
                | Q(sale_item__product__sku__icontains=product_search)
            )
        if category_search:
            returned_items = returned_items.filter(
                sale_item__product__category__name__icontains=category_search,
            )
        for returned in returned_items.values(
            'sale_item__product_id',
        ).annotate(quantity_returned=Sum('quantity')):
            product_id = returned['sale_item__product_id']
            sales_by_product[product_id] = max(
                sales_by_product.get(product_id, 0) - returned['quantity_returned'],
                0,
            )
        inventory_turnover = []
        for product in products:
            quantity_sold = sales_by_product.get(product['product_id'], 0)
            average_daily_sales = quantity_sold / effective_period_days
            days_of_stock = (
                round(product['quantity'] / average_daily_sales, 2)
                if average_daily_sales > 0 else None
            )
            if quantity_sold <= 0:
                rotation_status = 'dormant'
            elif average_daily_sales >= 1:
                rotation_status = 'fast'
            else:
                rotation_status = 'slow'
            inventory_turnover.append({
                'product_id': product['product_id'],
                'name': product['name'],
                'sku': product['sku'],
                'quantity_on_hand': product['quantity'],
                'quantity_sold': quantity_sold,
                'average_daily_sales': round(average_daily_sales, 4),
                'days_of_stock': days_of_stock,
                'rotation_status': rotation_status,
                'reorder_signal': (
                    product['quantity'] <= product['alert_threshold']
                    or days_of_stock is not None and days_of_stock <= 7
                ),
            })
        inventory_turnover.sort(
            key=lambda item: (
                item['rotation_status'] == 'dormant',
                -(item['average_daily_sales']),
            ),
        )
        movement_queryset = StockMovement.objects.filter(
            location_id__in=authorized_location_ids,
            created_at__gte=period_start,
            created_at__lte=period_end,
        )
        movement_summary = {
            entry['movement_type']: {
                'count': entry['movement_count'],
                'quantity': entry['total_quantity'] or 0,
            }
            for entry in movement_queryset.values('movement_type').annotate(
                movement_count=Count('id'),
                total_quantity=Sum('quantity'),
            )
        }
        return Response({
            'summary': {
                'total_stock_units': total_units,
                'tracked_products': len(products),
                'low_stock_products': len(low_stock_products),
                'out_of_stock_products': sum(
                    product['quantity'] <= 0 for product in products
                ),
                'untracked_products_in_scope': untracked_products_in_scope,
            },
            'stock_by_location': list(stock_by_location.values()),
            'low_stock': low_stock_products[:20],
            'inventory': products[:100],
            'inventory_truncated': len(products) > 100,
            'low_stock_truncated': len(low_stock_products) > 20,
            'rotation': {
                'period_start': period_start.date().isoformat(),
                'period_end': period_end.date().isoformat(),
                'period_days': effective_period_days,
                'fast_moving_threshold_units_per_day': 1,
                'low_cover_threshold_days': 7,
                'returns_separately_tracked': True,
                'products': inventory_turnover[:100],
                'truncated': len(inventory_turnover) > 100,
            },
            'movement_summary': movement_summary,
            'inventory_scope': {
                'source': 'StockItem',
                'location_filter_applied': bool(location_id),
                'sales_scope': 'authorized_locations_only',
                'products_without_stock_item_excluded': True,
                'costs_included': False,
            },
        }, status=status.HTTP_200_OK)


class PurchaseReportingView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('purchases'),
    ]

    def get(self, request, *args, **kwargs):
        start_boundary, end_boundary = _get_date_range(request)
        supplier_id = _get_integer_parameter(request, 'supplier')
        location_id = _get_integer_parameter(request, 'location')
        supplier_search = request.query_params.get('supplier_search', '').strip()
        location_search = request.query_params.get('location_search', '').strip()

        orders = tenant_scoped_queryset(
            PurchaseOrder.objects.filter(
                status__in=['approved', 'partial_received', 'received', 'closed'],
            ),
            request.user,
        )
        receipts = tenant_scoped_queryset(
            PurchaseReceipt.objects.filter(status='received'),
            request.user,
            tenant_field='purchase_order__tenant',
        )
        if start_boundary:
            orders = orders.filter(order_date__gte=start_boundary)
            receipts = receipts.filter(received_date__gte=start_boundary)
        if end_boundary:
            orders = orders.filter(order_date__lte=end_boundary)
            receipts = receipts.filter(received_date__lte=end_boundary)
        if supplier_id:
            orders = orders.filter(supplier_id=supplier_id)
            receipts = receipts.filter(purchase_order__supplier_id=supplier_id)
        if supplier_search:
            orders = orders.filter(supplier__name__icontains=supplier_search)
            receipts = receipts.filter(
                purchase_order__supplier__name__icontains=supplier_search,
            )
        if location_id:
            receipts = receipts.filter(location_id=location_id)
            orders = orders.filter(pk__in=receipts.values('purchase_order_id'))
        if location_search:
            receipts = receipts.filter(location__name__icontains=location_search)
            orders = orders.filter(pk__in=receipts.values('purchase_order_id'))

        external_purchases = tenant_scoped_queryset(
            ExternalPurchase.objects.filter(status='confirmed'),
            request.user,
        )
        if start_boundary:
            external_purchases = external_purchases.filter(
                purchase_date__gte=start_boundary,
            )
        if end_boundary:
            external_purchases = external_purchases.filter(
                purchase_date__lte=end_boundary,
            )
        if supplier_id:
            external_purchases = external_purchases.filter(supplier_id=supplier_id)
        if supplier_search:
            external_purchases = external_purchases.filter(
                supplier__name__icontains=supplier_search,
            )
        if location_id:
            external_purchases = external_purchases.filter(
                movements__location_id=location_id,
            ).distinct()
        if location_search:
            external_purchases = external_purchases.filter(
                movements__location__name__icontains=location_search,
            ).distinct()

        external_values = list(
            external_purchases.values('supplier_id', 'supplier__name').annotate(
                external_purchase_count=Count('id', distinct=True),
                external_purchase_quantity=Sum('quantity'),
                external_purchase_amount=Sum(ExpressionWrapper(
                    F('quantity') * F('unit_cost') + F('additional_cost'),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )),
            )
        )
        external_paid_values = list(
            ExternalPurchasePaymentAllocation.objects.filter(
                purchase__in=external_purchases,
                payment__financial_transaction__status='validated',
            ).values('purchase__supplier_id').annotate(
                external_paid_amount=Sum('amount'),
            )
        )

        order_values = list(
            orders.values(
                'supplier_id',
                'supplier__name',
            ).annotate(
                order_count=Count('id', distinct=True),
                ordered_quantity=Sum('items__quantity'),
                ordered_amount=Sum(ExpressionWrapper(
                    F('items__quantity') * F('items__unit_cost') * F('exchange_rate'),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                )),
            )
        )
        receipt_values = list(
            receipts.values(
                'purchase_order__supplier_id',
                'purchase_order__supplier__name',
            ).annotate(
                receipt_count=Count('id', distinct=True),
                acquisition_costs=Sum(
                    (F('transport_cost') + F('customs_cost') + F('handling_cost')
                    + F('insurance_cost') + F('other_cost')) * F('exchange_rate'),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                ),
            )
        )
        received_items = list(
            PurchaseReceiptItem.objects.filter(
                purchase_receipt__in=receipts,
            ).values(
                'purchase_receipt__purchase_order__supplier_id',
            ).annotate(
                received_quantity=Sum('quantity_received'),
                accepted_quantity=Sum('quantity_accepted'),
                quarantined_quantity=Sum('quantity_quarantined'),
                received_subtotal=Sum(ExpressionWrapper(
                    F('quantity_received')
                    * F('unit_cost')
                    * F('purchase_receipt__exchange_rate'),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                )),
            )
        )

        supplier_metrics = {}
        for entry in order_values:
            supplier_metrics[entry['supplier_id']] = {
                'supplier_id': entry['supplier_id'],
                'supplier': entry['supplier__name'],
                'order_count': entry['order_count'],
                'ordered_quantity': entry['ordered_quantity'] or 0,
                'ordered_amount': float(entry['ordered_amount'] or 0),
                'receipt_count': 0,
                'received_quantity': 0,
                'received_subtotal': 0.0,
                'acquisition_costs': 0.0,
            }
        for entry in receipt_values:
            supplier_id_for_entry = entry['purchase_order__supplier_id']
            supplier_metrics.setdefault(supplier_id_for_entry, {
                'supplier_id': supplier_id_for_entry,
                'supplier': entry['purchase_order__supplier__name'],
                'order_count': 0,
                'ordered_quantity': 0,
                'ordered_amount': 0.0,
                'receipt_count': 0,
                'received_quantity': 0,
                'received_subtotal': 0.0,
                'acquisition_costs': 0.0,
            })
            supplier_metrics[supplier_id_for_entry]['receipt_count'] = entry['receipt_count']
            supplier_metrics[supplier_id_for_entry]['acquisition_costs'] = float(
                entry['acquisition_costs'] or 0,
            )
        for entry in received_items:
            supplier_metrics[entry['purchase_receipt__purchase_order__supplier_id']][
                'received_quantity'
            ] += entry['received_quantity'] or 0
            supplier_metrics[entry['purchase_receipt__purchase_order__supplier_id']][
                'received_subtotal'
            ] += float(entry['received_subtotal'] or 0)
        for entry in external_values:
            supplier_metrics.setdefault(entry['supplier_id'], {
                'supplier_id': entry['supplier_id'],
                'supplier': entry['supplier__name'],
                'order_count': 0,
                'ordered_quantity': 0,
                'ordered_amount': 0.0,
                'receipt_count': 0,
                'received_quantity': 0,
                'received_subtotal': 0.0,
                'acquisition_costs': 0.0,
            })
            supplier = supplier_metrics[entry['supplier_id']]
            supplier['external_purchase_count'] = entry['external_purchase_count']
            supplier['external_purchase_quantity'] = entry['external_purchase_quantity'] or 0
            supplier['external_purchase_amount'] = float(
                entry['external_purchase_amount'] or 0,
            )
        for entry in external_paid_values:
            supplier = supplier_metrics[entry['purchase__supplier_id']]
            supplier['external_paid_amount'] = float(entry['external_paid_amount'] or 0)

        suppliers = list(supplier_metrics.values())
        for supplier in suppliers:
            supplier.setdefault('external_purchase_count', 0)
            supplier.setdefault('external_purchase_quantity', 0)
            supplier.setdefault('external_purchase_amount', 0.0)
            supplier.setdefault('external_paid_amount', 0.0)
            supplier['external_balance_due'] = max(
                supplier['external_purchase_amount'] - supplier['external_paid_amount'],
                0,
            )
            supplier['received_amount_before_allocated_costs'] = supplier.pop('received_subtotal')
            supplier['received_amount'] = (
                supplier['received_amount_before_allocated_costs']
                + supplier['acquisition_costs']
            )
            supplier['currency_comparison_available'] = False

        order_count = sum(item['order_count'] for item in suppliers)
        receipt_count = sum(item['receipt_count'] for item in suppliers)
        ordered_amount = sum(item['ordered_amount'] for item in suppliers)
        received_amount = sum(item['received_amount'] for item in suppliers)
        received_quantity = sum(item['received_quantity'] for item in suppliers)

        return Response({
            'summary': {
                'order_count': order_count,
                'ordered_amount': ordered_amount,
                'receipt_count': receipt_count,
                'received_quantity': received_quantity,
                'received_amount': received_amount,
                'supplier_count': len(suppliers),
                'acquisition_costs': sum(item['acquisition_costs'] for item in suppliers),
                'external_purchase_count': sum(
                    item['external_purchase_count'] for item in suppliers
                ),
                'external_purchase_quantity': sum(
                    item['external_purchase_quantity'] for item in suppliers
                ),
                'external_purchase_amount': sum(
                    item['external_purchase_amount'] for item in suppliers
                ),
                'external_paid_amount': sum(
                    item['external_paid_amount'] for item in suppliers
                ),
                'external_balance_due': sum(
                    item['external_balance_due'] for item in suppliers
                ),
                'ordered_amount_is_not_stock': True,
                'external_purchases_are_not_stock': True,
            },
            'suppliers': sorted(
                suppliers,
                key=lambda item: item['received_amount'],
                reverse=True,
            )[:20],
            'suppliers_truncated': len(suppliers) > 20,
            'data_quality': {
                'received_values_source': 'validated_received_receipts_only',
                'draft_and_cancelled_receipts_excluded': True,
                'ordered_amount_scope': (
                    'whole_orders_with_matching_validated_receipts'
                    if location_id else 'matching_orders'
                ),
                'currency_comparison_available': False,
                'currency_comparison_reason': (
                    'La devise n’est pas enregistrée sur les commandes ou les réceptions; '
                    'les montants ne sont donc pas comparables entre devises.'
                ),
                'acquisition_costs_are_receipt_level': True,
            },
        }, status=status.HTTP_200_OK)


class CreditReportingView(AdvancedReportingView):
    permission_classes = [permissions.IsAuthenticated, role_permission('payments')]


def _tenant_cash_payments(request):
    queryset = tenant_scoped_queryset(
        Payment.objects.all(),
        request.user,
        tenant_field='customer__tenant',
    )
    tenant = tenant_for_user(request.user)
    sale_scope = Q(sale__isnull=True) | Q(sale__tenant=tenant)
    if request.user.tenant_id is None:
        sale_scope |= Q(sale__tenant__isnull=True)
    return _apply_date_range(
        queryset.filter(sale_scope),
        request,
        'payment_date',
    )


class CashflowSummaryView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('core'),
    ]

    def get(self, request, *args, **kwargs):
        payments_queryset = _tenant_cash_payments(request)
        expenses_queryset = _apply_date_range(
            tenant_scoped_queryset(Expense.objects.all(), request.user),
            request,
            'expense_date',
        )

        cash_in = payments_queryset.aggregate(total=Sum('amount'))['total'] or 0
        cash_out = expenses_queryset.aggregate(total=Sum('amount'))['total'] or 0
        net_cash = float(cash_in) - float(cash_out)

        return Response({
            'cash_in': float(cash_in),
            'cash_out': float(cash_out),
            'net_cash': net_cash,
        }, status=status.HTTP_200_OK)


class CashView(CashflowSummaryView):
    pass


class CashTransactionsView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('core'),
    ]

    def get(self, request, *args, **kwargs):
        payments_queryset = _tenant_cash_payments(request)
        expenses_queryset = _apply_date_range(
            tenant_scoped_queryset(Expense.objects.all(), request.user),
            request,
            'expense_date',
        )

        payments = [
            {
                'type': 'in',
                'id': payment.id,
                'reference': payment.reference,
                'amount': float(payment.amount),
                'date': payment.payment_date,
                'description': f'Paiement {payment.reference or payment.id}',
            }
            for payment in payments_queryset.all()
        ]
        expenses = [
            {
                'type': 'out',
                'id': expense.id,
                'reference': expense.reference,
                'amount': float(expense.amount),
                'date': expense.expense_date,
                'description': expense.title,
            }
            for expense in expenses_queryset.all()
        ]
        transactions = sorted(payments + expenses, key=lambda item: item['date'], reverse=True)
        return Response(transactions, status=status.HTTP_200_OK)


class FinancialSummaryView(CashflowSummaryView):
    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        sales_queryset = _apply_date_range(
            tenant_scoped_queryset(Sale.objects.all(), request.user),
            request,
            'sale_date',
        )
        payments_queryset = _tenant_cash_payments(request)
        total_sales = sales_queryset.aggregate(total=Sum('total_amount'))['total'] or 0
        total_received = payments_queryset.aggregate(total=Sum('amount'))['total'] or 0
        response.data['outstanding_balance'] = float(total_sales - total_received)
        return response


class FinanceReportingView(FinancialSummaryView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('finance'),
    ]

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        open_credit_sales = tenant_scoped_queryset(
            Sale.objects.filter(
                payment_method='credit',
                total_amount__gt=F('amount_paid'),
            ).exclude(status__in=['draft', 'cancelled']),
            request.user,
        )
        outstanding_balance = open_credit_sales.aggregate(
            total=Sum(ExpressionWrapper(
                F('total_amount') - F('amount_paid'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )),
        )['total'] or 0
        external_purchases = tenant_scoped_queryset(
            ExternalPurchase.objects.filter(status='confirmed'),
            request.user,
        )
        external_purchase_total = external_purchases.aggregate(
            total=Sum(ExpressionWrapper(
                F('quantity') * F('unit_cost') + F('additional_cost'),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )),
        )['total'] or Decimal('0')
        external_paid_total = ExternalPurchasePaymentAllocation.objects.filter(
            purchase__in=external_purchases,
            payment__financial_transaction__status='validated',
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        response.data['outstanding_balance'] = float(outstanding_balance)
        response.data['outstanding_balance_scope'] = 'current_open_credit_sales'
        response.data['external_supplier_payables'] = float(
            max(external_purchase_total - external_paid_total, Decimal('0')),
        )
        response.data['external_supplier_payables_scope'] = (
            'confirmed_external_purchases_after_validated_payments'
        )
        response.data['as_of'] = timezone.localdate().isoformat()
        return response


class GlobalSearchView(generics.GenericAPIView):
    serializer_class = JsonResponseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('core'),
    ]

    def get(self, request, *args, **kwargs):
        query = (request.query_params.get('q') or request.query_params.get('query') or '').strip()
        if not query:
            return Response({
                'query': '',
                'total': 0,
                'products': [],
                'customers': [],
                'suppliers': [],
                'invoices': [],
                'cartons': [],
                'sales': [],
                'payments': [],
            }, status=status.HTTP_200_OK)

        q_filter = Q(name__icontains=query) | Q(sku__icontains=query)
        products = list(
            tenant_scoped_queryset(
                Product.objects.filter(q_filter),
                request.user,
            ).values('id', 'sku', 'name', 'brand', 'quantity', 'selling_price')[:10]
        )

        customer_filter = Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query) | Q(company_name__icontains=query)
        customers = list(
            tenant_scoped_queryset(
                Customer.objects.filter(customer_filter),
                request.user,
            ).values('id', 'full_name', 'phone', 'email', 'company_name')[:10]
        )

        supplier_filter = Q(name__icontains=query) | Q(contact_name__icontains=query) | Q(company_name__icontains=query) | Q(phone__icontains=query)
        suppliers = list(
            tenant_scoped_queryset(
                Supplier.objects.filter(supplier_filter),
                request.user,
            ).values('id', 'name', 'contact_name', 'company_name', 'phone', 'email')[:10]
        )

        invoice_filter = Q(invoice_number__icontains=query) | Q(sale__customer__full_name__icontains=query)
        invoices = list(
            tenant_scoped_queryset(
                Invoice.objects.filter(invoice_filter),
                request.user,
                tenant_field='sale__tenant',
            ).select_related('sale__customer').values(
                'id',
                'invoice_number',
                'total_amount',
                'paid_amount',
                'sale__customer__full_name',
            )[:10]
        )

        payment_filter = Q(reference__icontains=query) | Q(customer__full_name__icontains=query) | Q(customer__phone__icontains=query)
        payments = list(
            _tenant_cash_payments(request).filter(
                payment_filter,
            ).select_related('customer').values(
                'id',
                'reference',
                'amount',
                'payment_method',
                'customer__full_name',
            )[:10]
        )

        carton_filter = Q(reference__icontains=query) | Q(product__name__icontains=query)
        cartons = list(
            tenant_scoped_queryset(
                Carton.objects.filter(carton_filter),
                request.user,
                tenant_field='product__tenant',
            ).select_related('product', 'location').values(
                'id', 'reference', 'quantity', 'product__name', 'location__name',
            )[:10]
        )

        sale_filter = Q(notes__icontains=query) | Q(external_reference__icontains=query) | Q(customer__full_name__icontains=query)
        if query.isdigit():
            sale_filter |= Q(id=int(query))
        sales = list(
            tenant_scoped_queryset(
                Sale.objects.filter(sale_filter),
                request.user,
            ).values(
                'id',
                'status',
                'total_amount',
                'amount_paid',
                'customer__full_name',
            )[:10]
        )

        payload = {
            'query': query,
            'total': len(products) + len(customers) + len(suppliers) + len(invoices) + len(cartons) + len(sales) + len(payments),
            'products': products,
            'customers': customers,
            'suppliers': suppliers,
            'invoices': invoices,
            'cartons': cartons,
            'sales': sales,
            'payments': payments,
        }
        return Response(payload, status=status.HTTP_200_OK)
