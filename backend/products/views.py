from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from core.models import AuditLog
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from inventory.models import InventoryLocation, StockItem
from users.permissions import (
    IsAdminUser,
    ProductCatalogPermission,
    role_permission,
)
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


def stock_accessible_locations(user):
    locations = tenant_scoped_queryset(InventoryLocation.objects.all(), user)
    if locations.filter(authorized_users__isnull=False).exists():
        locations = locations.filter(authorized_users=user)
    return locations


def annotate_accessible_stock(queryset, user):
    if user.has_role('stock') and not user.has_role('admin'):
        return queryset.annotate(
            accessible_quantity=Sum(
                'stock_items__quantity',
                filter=Q(stock_items__location__in=stock_accessible_locations(user)),
            )
        )
    return queryset


class CategoryListCreateView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]

    def get_queryset(self):
        return tenant_scoped_queryset(
            Category.objects.all(),
            self.request.user,
        ).order_by('name', 'pk')

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for_user(self.request.user))


class ProductListCreateView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]
    pagination_class = None

    def get_queryset(self):
        queryset = annotate_accessible_stock(
            tenant_scoped_queryset(
                Product.objects.select_related('category').all(),
                self.request.user,
            ),
            self.request.user,
        )
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(manufacturer_reference__icontains=search) |
                Q(brand__icontains=search) |
                Q(alternative_references__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for_user(self.request.user))


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]

    def get_queryset(self):
        return annotate_accessible_stock(
            tenant_scoped_queryset(Product.objects.all(), self.request.user),
            self.request.user,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'La suppression physique d’un produit est interdite. Utilisez l’archivage.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class ProductArchiveView(generics.GenericAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]

    def get_queryset(self):
        return tenant_scoped_queryset(Product.objects.all(), self.request.user)

    def post(self, request, *args, **kwargs):
        product = self.get_object()
        if product.is_active:
            product.is_active = False
            product.save(update_fields=['is_active', 'updated_at'])
            AuditLog.objects.create(
                user=request.user,
                action='stock',
                model_name='Product',
                record_id=product.id,
                details=f'Produit archivé: {product.sku}',
            )
        return Response(self.get_serializer(product).data, status=status.HTTP_200_OK)


class ProductPricingView(generics.GenericAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return tenant_scoped_queryset(Product.objects.all(), self.request.user)

    def _build_response(self, product, margin_percent, recommended_selling_price):
        cost_price = Decimal(str(product.cost_price or 0))
        margin_amount = recommended_selling_price - cost_price
        return {
            'id': product.id,
            'sku': product.sku,
            'name': product.name,
            'cost_price': str(cost_price.quantize(Decimal('0.01'))),
            'current_selling_price': str(Decimal(str(product.selling_price or 0)).quantize(Decimal('0.01'))),
            'margin_amount': str(margin_amount.quantize(Decimal('0.01'))),
            'margin_percent': str(margin_percent.quantize(Decimal('0.01'))),
            'recommended_selling_price': str(recommended_selling_price.quantize(Decimal('0.01'))),
        }

    def _parse_margin(self, raw_margin):
        try:
            margin_percent = Decimal(raw_margin) if raw_margin else Decimal('0')
        except InvalidOperation as exc:
            raise ValueError('Le pourcentage de marge doit être un nombre valide.') from exc
        return margin_percent

    def get(self, request, *args, **kwargs):
        product = self.get_object()
        raw_margin = (request.query_params.get('margin_percent') or '').strip()

        try:
            margin_percent = self._parse_margin(raw_margin)
        except ValueError as exc:
            return Response({'margin_percent': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        cost_price = Decimal(str(product.cost_price or 0))
        recommended_selling_price = cost_price * (Decimal('1') + margin_percent / Decimal('100')) if cost_price else Decimal('0')
        return Response(self._build_response(product, margin_percent, recommended_selling_price), status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        product = self.get_object()
        payload = request.data if isinstance(request.data, dict) else {}
        raw_margin = (payload.get('margin_percent') or request.query_params.get('margin_percent') or '').strip()

        try:
            margin_percent = self._parse_margin(raw_margin)
        except ValueError as exc:
            return Response({'margin_percent': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        cost_price = Decimal(str(product.cost_price or 0))
        recommended_selling_price = cost_price * (Decimal('1') + margin_percent / Decimal('100')) if cost_price else Decimal('0')

        product.selling_price = recommended_selling_price
        product.save(update_fields=['selling_price', 'updated_at'])

        return Response(self._build_response(product, margin_percent, recommended_selling_price), status=status.HTTP_200_OK)


class ProductStockView(generics.GenericAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, role_permission('products')]

    def get_queryset(self):
        return tenant_scoped_queryset(Product.objects.all(), self.request.user)

    def get(self, request, *args, **kwargs):
        product = self.get_object()
        stock_items = StockItem.objects.filter(
            product=product,
            location__in=stock_accessible_locations(request.user),
        ).select_related('location')
        return Response({
            'product': product.id,
            'quantity': sum(item.quantity for item in stock_items),
            'locations': [
                {
                    'location': item.location_id,
                    'location_name': item.location.name,
                    'quantity': item.quantity,
                }
                for item in stock_items
            ],
        }, status=status.HTTP_200_OK)
