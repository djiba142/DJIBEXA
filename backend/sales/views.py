from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.db import transaction
from django.db.models import F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.pagination import VersionedApiPagination
from core.tenancy import tenant_scoped_queryset
from users.permissions import (
    IsTenantAssignedUser,
    SensitiveMutationPermission,
    role_permission,
)
from core.models import AuditLog
from inventory.models import Carton, InventoryCostLayer, InventoryLocation, StockItem, StockMovement
from products.models import Product
from suppliers.models import Supplier
from core.idempotency import execute_idempotent_request
from .models import (
    CustomerOrder,
    CustomerOrderItem,
    Sale,
    SaleItemTrackedUnit,
    SaleReturnCostAllocation,
    SaleReturnQuarantine,
)
from .serializers import (
    SaleCatalogSerializer,
    CustomerOrderSerializer,
    SaleLocationSerializer,
    SaleExternalSupplierSerializer,
    SaleReturnQuarantineSerializer,
    SaleReturnSerializer,
    SaleReturnQuarantineReleaseSerializer,
    SaleSerializer,
)
from .utils import sales_locations_for_user
from .reservations import reserved_quantity


class RejectSaleDeletionPermission(SensitiveMutationPermission):
    def has_permission(self, request, view):
        if request.method == 'DELETE':
            return True
        return super().has_permission(request, view)

class SaleCatalogView(generics.ListAPIView):
    serializer_class = SaleCatalogSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]
    pagination_class = VersionedApiPagination

    def get_queryset(self):
        locations = sales_locations_for_user(self.request.user)
        queryset = tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            self.request.user,
        )
        search = self.request.query_params.get('search', '').strip()
        if not search:
            return queryset.none()
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(sku__icontains=search)
            | Q(alternative_references__icontains=search)
            | Q(brand__icontains=search)
            | Q(vehicle__icontains=search)
            | Q(barcode__icontains=search)
        )
        category = self.request.query_params.get('category')
        if category and category.isdigit():
            queryset = queryset.filter(category_id=int(category))
        available = self.request.query_params.get('available')
        if available == 'true':
            reservations = tenant_scoped_queryset(
                CustomerOrderItem.objects.filter(
                    product_id=OuterRef('pk'),
                    order__location_id=OuterRef('stock_items__location_id'),
                    order__status='confirmed',
                ),
                self.request.user,
                tenant_field='order__tenant',
            ).order_by().values('product_id').annotate(
                quantity=Sum('quantity'),
            ).values('quantity')[:1]
            queryset = queryset.filter(
                stock_items__location__in=locations,
            ).annotate(
                sale_available_quantity=F('stock_items__quantity') - Coalesce(
                    Subquery(reservations, output_field=IntegerField()),
                    Value(0),
                ),
            ).filter(sale_available_quantity__gt=0).distinct()
        return (
            queryset
            .select_related('category')
            .prefetch_related(
                Prefetch(
                    'stock_items',
                    queryset=StockItem.objects.filter(location__in=locations).select_related('location'),
                    to_attr='sale_catalog_stock_items',
                )
            )
            .order_by('name', 'id')
        )


class SaleLocationListView(generics.ListAPIView):
    serializer_class = SaleLocationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]
    pagination_class = None

    def get_queryset(self):
        return sales_locations_for_user(self.request.user)


class SaleExternalSupplierListView(generics.ListAPIView):
    serializer_class = SaleExternalSupplierSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]
    pagination_class = None

    def get_queryset(self):
        return tenant_scoped_queryset(
            Supplier.objects.all(),
            self.request.user,
        )


class CustomerOrderListCreateView(generics.ListCreateAPIView):
    serializer_class = CustomerOrderSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            CustomerOrder.objects.select_related(
                'customer',
                'location',
                'created_by',
                'sale',
            ).prefetch_related(
                'items__product',
            ),
            self.request.user,
        )
        status_filter = self.request.query_params.get('status')
        if status_filter:
            if status_filter not in dict(CustomerOrder.STATUS_CHOICES):
                raise ValidationError({
                    'status': 'Valeur invalide. Choisissez quote, confirmed, delivered ou cancelled.',
                })
            queryset = queryset.filter(status=status_filter)
        if self.request.user.has_role('sales') and not self.request.user.has_role('admin'):
            return queryset.filter(created_by=self.request.user)
        return queryset


class CustomerOrderDetailView(generics.RetrieveAPIView):
    serializer_class = CustomerOrderSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            CustomerOrder.objects.select_related(
                'customer',
                'location',
                'created_by',
                'sale',
            ).prefetch_related('items__product'),
            self.request.user,
        )
        if self.request.user.has_role('sales') and not self.request.user.has_role('admin'):
            return queryset.filter(created_by=self.request.user)
        return queryset


class CustomerOrderActionView(generics.GenericAPIView):
    serializer_class = CustomerOrderSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_order(self, pk):
        queryset = tenant_scoped_queryset(
            CustomerOrder.objects.select_for_update().select_related(
                'customer',
                'location',
            ).prefetch_related('items__product'),
            self.request.user,
        )
        if self.request.user.has_role('sales') and not self.request.user.has_role('admin'):
            queryset = queryset.filter(created_by=self.request.user)
        order = queryset.filter(pk=pk).first()
        if order is None:
            from rest_framework.exceptions import NotFound

            raise NotFound('Devis ou commande introuvable.')
        return order

    @transaction.atomic
    def post(self, request, pk, action, *args, **kwargs):
        order = self.get_order(pk)
        if action == 'confirm':
            if order.status != 'quote':
                raise ValidationError({'status': 'Seul un devis peut être confirmé.'})
            if request.user.has_role('sales') and not request.user.has_role('admin') and not sales_locations_for_user(
                request.user,
            ).filter(pk=order.location_id).exists():
                raise ValidationError({'location': 'Vous ne pouvez plus réserver de stock dans cette boutique.'})
            products = list(
                tenant_scoped_queryset(
                    Product.objects.select_for_update().filter(
                        pk__in=order.items.values_list('product_id', flat=True),
                    ),
                    request.user,
                ).order_by('pk')
            )
            if len(products) != order.items.values('product_id').distinct().count():
                raise ValidationError({
                    'items': 'Cette commande contient un produit hors de votre entreprise.',
                })
            for product in products:
                item = order.items.get(product=product)
                stock_item = StockItem.objects.select_for_update().filter(
                    product=product,
                    location=order.location,
                ).first()
                available = (
                    stock_item.quantity - reserved_quantity(
                        product_id=product.pk,
                        location_id=order.location_id,
                    )
                    if stock_item else 0
                )
                if available < item.quantity:
                    raise ValidationError({
                        'items': (
                            f'Stock disponible insuffisant pour {product.name} : '
                            f'{available} unité(s) disponible(s).'
                        ),
                    })
            order.status = 'confirmed'
            order.save(update_fields=['status', 'updated_at'])
            AuditLog.objects.create(
                user=request.user,
                action='customer_order',
                model_name='CustomerOrder',
                record_id=order.id,
                details=f'Devis {order.reference} confirmé ; {order.items.count()} ligne(s) réservée(s).',
            )
        elif action == 'deliver':
            if order.status != 'confirmed':
                raise ValidationError({'status': 'Seule une commande confirmée peut être livrée.'})
            delivery = request.data if isinstance(request.data, dict) else {}
            sale_status = delivery.get('sale_status', 'draft')
            if sale_status not in {'draft', 'paid', 'partial'}:
                raise ValidationError({
                    'sale_status': 'La vente issue de la livraison doit être en brouillon, payée ou partielle.',
                })
            sale_data = {
                'customer': order.customer_id,
                'location': order.location_id,
                'status': sale_status,
                'payment_method': delivery.get('payment_method', 'cash'),
                'financial_account': delivery.get('financial_account'),
                'amount_paid': delivery.get('amount_paid', '0'),
                'discount': order.discount,
                'notes': order.notes,
                'items': [
                    {
                        'product': item.product_id,
                        'quantity': item.quantity,
                        'unit_price': item.unit_price,
                    }
                    for item in order.items.all()
                ],
            }
            sale_serializer = SaleSerializer(
                data=sale_data,
                context={
                    **self.get_serializer_context(),
                    'customer_order_id': order.id,
                },
            )
            sale_serializer.is_valid(raise_exception=True)
            sale = sale_serializer.save()
            order.status = 'delivered'
            order.sale = sale
            order.save(update_fields=['status', 'sale', 'updated_at'])
            AuditLog.objects.create(
                user=request.user,
                action='customer_order',
                model_name='CustomerOrder',
                record_id=order.id,
                details=f'Commande {order.reference} livrée via vente {sale.id}.',
            )
        elif action == 'cancel':
            if order.status not in {'quote', 'confirmed'}:
                raise ValidationError({'status': 'Seul un devis ou une commande ouverte peut être annulé.'})
            order.status = 'cancelled'
            order.save(update_fields=['status', 'updated_at'])
            AuditLog.objects.create(
                user=request.user,
                action='customer_order',
                model_name='CustomerOrder',
                record_id=order.id,
                details=f'Devis/commande {order.reference} annulé ; réservation libérée.',
            )
        else:
            raise ValidationError({'action': 'Action inconnue.'})

        return Response(self.get_serializer(order).data, status=status.HTTP_200_OK)


class SaleListCreateView(generics.ListCreateAPIView):
    queryset = Sale.objects.select_related(
        'customer',
        'external_supplier',
    ).prefetch_related(
        'items__product',
        'items__stock_origins__carton',
        'items__stock_origins__location',
        'items__tracked_unit_allocations__stock_unit__carton',
    ).all()
    serializer_class = SaleSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
        )
        if self.request.user.has_role('sales') and not self.request.user.has_role('admin'):
            return queryset.filter(seller=self.request.user)
        return queryset

    def create(self, request, *args, **kwargs):
        endpoint = request.path

        def create_sale():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return execute_idempotent_request(request, endpoint, create_sale)


class SaleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Sale.objects.select_related(
        'customer',
        'external_supplier',
    ).prefetch_related(
        'items__product',
        'items__stock_origins__carton',
        'items__stock_origins__location',
        'items__tracked_unit_allocations__stock_unit__carton',
    ).all()
    serializer_class = SaleSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
        RejectSaleDeletionPermission,
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
        )
        if self.request.user.has_role('sales') and not self.request.user.has_role('admin'):
            return queryset.filter(seller=self.request.user)
        return queryset

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'La suppression physique d’une vente est interdite.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class SaleReturnCreateView(generics.GenericAPIView):
    queryset = Sale.objects.all()
    serializer_class = SaleReturnSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SensitiveMutationPermission,
    ]

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        sale = tenant_scoped_queryset(
            Sale.objects.select_for_update(),
            request.user,
        ).filter(pk=pk).first()
        if sale is None:
            return Response({'detail': 'Vente introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), 'sale': sale},
        )
        serializer.is_valid(raise_exception=True)
        return_record = serializer.save()
        return Response(self.get_serializer(return_record).data, status=status.HTTP_201_CREATED)


class SaleReturnQuarantineReleaseView(generics.GenericAPIView):
    serializer_class = SaleReturnQuarantineReleaseSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('admin'),
    ]

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        quarantine = (
            tenant_scoped_queryset(
                SaleReturnQuarantine.objects.select_for_update()
                .select_related('return_item__sale_return', 'return_item__sale_item'),
                request.user,
                tenant_field='return_item__sale_return__sale__tenant',
            ).filter(pk=pk)
            .first()
        )
        if quarantine is None:
            return Response({'detail': 'Dossier de quarantaine introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data['quantity']
        reason = serializer.validated_data['reason']
        if quantity > quarantine.quantity_remaining:
            raise ValidationError({
                'quantity': 'La quantité dépasse le solde encore en quarantaine.',
            })

        sale_item = quarantine.return_item.sale_item
        product = Product.objects.select_for_update().get(pk=sale_item.product_id)
        remaining_to_release = quantity
        allocations = (
            SaleReturnCostAllocation.objects.select_for_update()
            .filter(return_item=quarantine.return_item, quantity_quarantined_remaining__gt=0)
            .order_by('id')
        )
        for allocation in allocations:
            released = min(remaining_to_release, allocation.quantity_quarantined_remaining)
            if not released:
                continue
            original_id = allocation.original_allocation_id or 'UNKNOWN'
            quarantined_layer = (
                InventoryCostLayer.objects.select_for_update()
                .filter(
                    product=product,
                    location=quarantine.location,
                    source='return',
                    reference=f'RETURN-{quarantine.return_item.sale_return_id}-Q-{original_id}',
                    is_available=False,
                )
                .first()
            )
            if quarantined_layer is None or quarantined_layer.quantity_remaining < released:
                raise ValidationError({
                    'quantity': 'Les couches de coût en quarantaine sont incohérentes; aucune remise en stock effectuée.',
                })
            quarantined_layer.quantity_remaining -= released
            quarantined_layer.save(update_fields=['quantity_remaining'])
            allocation.quantity_quarantined_remaining -= released
            allocation.save(update_fields=['quantity_quarantined_remaining'])
            InventoryCostLayer.objects.create(
                product=product,
                location=quarantine.location,
                source='return',
                reference=f'RETURN-Q-{quarantine.id}-RELEASE',
                quantity_received=released,
                quantity_remaining=released,
                unit_cost=allocation.unit_cost,
                is_available=True,
            )
            remaining_to_release -= released
            if not remaining_to_release:
                break

        if remaining_to_release:
            raise ValidationError({
                'quantity': 'Les quantités de coût disponibles ne couvrent pas la demande.',
            })

        stock_item, _ = StockItem.objects.select_for_update().get_or_create(
            product=product,
            location=quarantine.location,
        )
        stock_item.quantity += quantity
        stock_item.save(update_fields=['quantity', 'updated_at'])
        product.quantity = (product.quantity or 0) + quantity
        product.save(update_fields=['quantity', 'updated_at'])
        unit_links = list(
            SaleItemTrackedUnit.objects.select_for_update()
            .select_related('stock_unit__carton')
            .filter(
                sale_return_item=quarantine.return_item,
                stock_unit__status='quarantined',
            )
            .order_by('id')[:quantity]
        )
        carton_additions = {}
        for link in unit_links:
            unit = link.stock_unit
            unit.location = quarantine.location
            unit.status = 'available'
            unit.save(update_fields=['location', 'status', 'updated_at'])
            if unit.carton.location_id == quarantine.location_id:
                carton_additions[unit.carton_id] = carton_additions.get(unit.carton_id, 0) + 1
        for carton_id, restored_quantity in carton_additions.items():
            carton = Carton.objects.select_for_update().get(pk=carton_id)
            carton.quantity += restored_quantity
            carton.save(update_fields=['quantity', 'updated_at'])
        quarantine.quantity_remaining -= quantity
        quarantine.reviewed_by = request.user
        quarantine.status = 'resolved' if quarantine.quantity_remaining == 0 else 'pending'
        if quarantine.status == 'resolved':
            quarantine.resolved_at = timezone.now()
        quarantine.save(update_fields=[
            'quantity_remaining',
            'reviewed_by',
            'status',
            'resolved_at',
        ])
        StockMovement.objects.create(
            product=product,
            location=quarantine.location,
            movement_type='quarantine_out',
            quantity=quantity,
            reference=f'RETURN-Q-{quarantine.id}',
            notes=reason,
            created_by=request.user,
        )
        StockMovement.objects.create(
            product=product,
            location=quarantine.location,
            movement_type='in',
            quantity=quantity,
            reference=f'RETURN-Q-{quarantine.id}-RELEASE',
            notes=reason,
            created_by=request.user,
        )
        AuditLog.objects.create(
            user=request.user,
            action='sale_return_quarantine_release',
            model_name='SaleReturnQuarantine',
            record_id=quarantine.id,
            details=f'{quantity} unité(s) remises en stock. Motif: {reason}',
        )
        return Response({
            'id': quarantine.id,
            'quantity': quarantine.quantity,
            'quantity_remaining': quarantine.quantity_remaining,
            'status': quarantine.status,
        })


class SaleReturnQuarantineListView(generics.ListAPIView):
    serializer_class = SaleReturnQuarantineSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('admin'),
    ]
    pagination_class = None

    def get_queryset(self):
        return (
            tenant_scoped_queryset(
                SaleReturnQuarantine.objects.filter(
                    return_item__sale_return__sale_id=self.kwargs['pk'],
                    quantity_remaining__gt=0,
                ),
                self.request.user,
                tenant_field='return_item__sale_return__sale__tenant',
            ).select_related(
                'return_item__sale_item__product',
                'location',
            ).order_by('created_at', 'id')
        )


class ExternalSaleListCreateView(SaleListCreateView):
    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['is_external'] = True
        endpoint = request.path

        def create_external_sale():
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return execute_idempotent_request(request, endpoint, create_external_sale)
