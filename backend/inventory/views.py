from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from core.models import AuditLog
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from inventory.access import accessible_locations
from inventory.costing import consume_fifo_cartons, consume_fifo_cost, record_cost_layer
from inventory.labels import ensure_carton_units
from notifications.models import Notification
from products.models import Product
from users.permissions import (
    CartonAccessPermission,
    InventoryLocationPermission,
    InventoryCountAccessPermission,
    IsAdminUser,
    IsTenantAssignedUser,
    StockOperationsMutationPermission,
    StockMovementAccessPermission,
    StockReplenishmentRequestAccessPermission,
    StockTransferAccessPermission,
    role_permission,
)
from .models import (
    Carton,
    InventoryCount,
    InventoryLocation,
    SampleCarton,
    StockItem,
    StockMovement,
    StockReplenishmentRequest,
    StockTransfer,
    StockUnit,
)
from .serializers import (
    CartonSerializer,
    InventoryCountSerializer,
    InventoryLocationSerializer,
    SampleCartonSerializer,
    StockItemSerializer,
    StockMovementSerializer,
    StockReplenishmentRequestSerializer,
    StockTransferSerializer,
    StockUnitInitializationSerializer,
    StockUnitSerializer,
    transition_stock_transfer,
)


class InventoryLocationListCreateView(generics.ListCreateAPIView):
    queryset = InventoryLocation.objects.all()
    serializer_class = InventoryLocationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
        InventoryLocationPermission,
    ]

    def get_queryset(self):
        return accessible_locations(self.request.user)

    def perform_create(self, serializer):
        location = serializer.save(tenant=tenant_for_user(self.request.user))
        if not self.request.user.has_role('admin'):
            location.authorized_users.add(self.request.user)
        AuditLog.objects.create(
            user=self.request.user,
            action='stock',
            model_name='InventoryLocation',
            record_id=location.id,
            details=f'Emplacement créé: {location.name} ({location.code}).',
        )


class InventoryLocationDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = InventoryLocation.objects.all()
    serializer_class = InventoryLocationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
        StockOperationsMutationPermission,
        InventoryLocationPermission,
    ]

    def get_queryset(self):
        return accessible_locations(self.request.user)

    def perform_update(self, serializer):
        if (
            self.request.user.has_role('stock')
            and not self.request.user.has_role('admin')
            and 'authorized_users' in serializer.validated_data
        ):
            raise PermissionDenied('Seul un administrateur peut modifier les utilisateurs autorisés.')
        location = serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            action='stock',
            model_name='InventoryLocation',
            record_id=location.id,
            details=f'Emplacement mis à jour: {location.name} ({location.code}).',
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'La suppression physique d’un emplacement est interdite.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class StockItemListView(generics.ListAPIView):
    queryset = StockItem.objects.select_related('product', 'location').all()
    serializer_class = StockItemSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
    ]

    def get_queryset(self):
        return stock_items_with_sample_counts(
            StockItem.objects.select_related('product', 'location').filter(
                location__in=accessible_locations(self.request.user),
            )
        )


def stock_items_with_sample_counts(queryset):
    return queryset.annotate(
        sample_quantity=Count(
            'location__stock_units',
            filter=Q(
                location__stock_units__carton__product_id=F('product_id'),
                location__stock_units__status='sample',
            ),
            distinct=True,
        ),
    ).order_by('product__name', 'location__name', 'pk')


class InventoryLocationStockView(generics.GenericAPIView):
    serializer_class = StockItemSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
    ]

    def get(self, request, pk):
        location = accessible_locations(request.user).filter(pk=pk).first()
        if location is None:
            return Response({'detail': 'Emplacement introuvable ou non autorisé.'}, status=status.HTTP_404_NOT_FOUND)
        items = list(stock_items_with_sample_counts(
            StockItem.objects.filter(location=location).select_related('product')
        ))
        return Response({
            'location': location.id,
            'location_name': location.name,
            'total_quantity': sum(item.quantity for item in items),
            'physical_quantity': sum(item.quantity + item.sample_quantity for item in items),
            'items': [
                {
                    'product': item.product_id,
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'sample_quantity': item.sample_quantity,
                    'physical_quantity': item.quantity + item.sample_quantity,
                }
                for item in items
            ],
        }, status=status.HTTP_200_OK)


class StockMovementListCreateView(generics.ListCreateAPIView):
    queryset = StockMovement.objects.select_related('product', 'location', 'created_by').all()
    serializer_class = StockMovementSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockMovementAccessPermission,
    ]

    def get_queryset(self):
        return StockMovement.objects.select_related('product', 'location', 'created_by').filter(
            location__in=accessible_locations(self.request.user),
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except ValidationError as exc:
            return Response({'quantity': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        movement = serializer.instance
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='StockMovement',
            record_id=movement.id,
            details=f"Mouvement de stock {movement.movement_type}: {movement.reference}",
        )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class StockMovementDetailView(generics.RetrieveAPIView):
    queryset = StockMovement.objects.select_related('product', 'location', 'created_by').all()
    serializer_class = StockMovementSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockMovementAccessPermission,
    ]

    def get_queryset(self):
        return self.queryset.filter(location__in=accessible_locations(self.request.user))


class StockTransferListCreateView(generics.ListCreateAPIView):
    queryset = StockTransfer.objects.select_related('product', 'from_location', 'to_location', 'created_by').all()
    serializer_class = StockTransferSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockTransferAccessPermission,
    ]

    def get_queryset(self):
        locations = accessible_locations(self.request.user)
        return StockTransfer.objects.select_related('product', 'from_location', 'to_location', 'created_by').filter(
            from_location__in=locations,
            to_location__in=locations,
        )

    def perform_create(self, serializer):
        transfer = serializer.validated_data
        allowed = accessible_locations(self.request.user)
        if not allowed.filter(pk=transfer['from_location'].pk).exists() or not allowed.filter(
            pk=transfer['to_location'].pk,
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Vous ne pouvez transférer qu’entre vos emplacements autorisés.')
        instance = serializer.save(created_by=self.request.user)
        AuditLog.objects.create(
            user=self.request.user,
            action='stock',
            model_name='StockTransfer',
            record_id=instance.id,
            details=(
                f'Transfert demandé: {instance.reference}, {instance.quantity} unité(s), '
                f'{instance.from_location.name} → {instance.to_location.name}. Motif: {instance.notes}'
            ),
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except ValidationError as exc:
            return Response({'quantity': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class StockTransferDetailView(generics.RetrieveAPIView):
    queryset = StockTransfer.objects.select_related('product', 'from_location', 'to_location', 'created_by').all()
    serializer_class = StockTransferSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockTransferAccessPermission,
    ]

    def get_queryset(self):
        locations = accessible_locations(self.request.user)
        return self.queryset.filter(from_location__in=locations, to_location__in=locations)


class StockTransferActionView(generics.GenericAPIView):
    queryset = StockTransfer.objects.select_related('product', 'from_location', 'to_location').all()
    serializer_class = StockTransferSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockTransferAccessPermission,
    ]

    def get_queryset(self):
        locations = accessible_locations(self.request.user)
        return self.queryset.filter(from_location__in=locations, to_location__in=locations)

    @extend_schema(operation_id='stock_transfer_action')
    @transaction.atomic
    def post(self, request, action, *args, **kwargs):
        transfer = self.get_object()
        target_status = {'validate': 'validated', 'ship': 'shipped', 'receive': 'received'}.get(action)
        if target_status is None:
            return Response({'detail': 'Action de transfert inconnue.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            quantity_received = None
            variance_reason = ''
            if action == 'receive':
                try:
                    quantity_received = int(request.data.get('quantity_received', transfer.quantity_shipped))
                except (TypeError, ValueError):
                    return Response(
                        {'quantity_received': 'La quantité doit être un nombre entier.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                variance_reason = str(request.data.get('variance_reason', '')).strip()
            transfer = transition_stock_transfer(
                transfer,
                target_status,
                request.user,
                quantity_received=quantity_received,
                variance_reason=variance_reason,
            )
        except ValidationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)

        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='StockTransfer',
            record_id=transfer.id,
            details=f"Transfert de stock {action}: {transfer.reference}",
        )
        if action == 'receive':
            update_replenishment_request_status(transfer.replenishment_request_id)
        return Response(self.get_serializer(transfer).data, status=status.HTTP_200_OK)


def replenishment_requests_for_user(user):
    requests = StockReplenishmentRequest.objects.select_related(
        'product', 'shop', 'requested_by', 'reviewed_by',
    ).prefetch_related('transfers')
    requests = tenant_scoped_queryset(
        requests,
        user,
        tenant_field='shop__tenant',
    )
    if user.has_role('admin') or getattr(user, 'is_superuser', False):
        return requests
    if user.has_role('stock'):
        return requests.filter(shop__in=accessible_locations(user))
    if user.has_role('sales'):
        return requests.filter(requested_by=user)
    return requests.none()


def update_replenishment_request_status(request_id):
    if request_id is None:
        return
    replenishment = StockReplenishmentRequest.objects.select_for_update().get(pk=request_id)
    transfers = replenishment.transfers.all()
    received_quantity = transfers.filter(status='received').aggregate(
        total=Sum('quantity_received'),
    )['total'] or 0
    transfer_in_progress = transfers.filter(
        status__in=['requested', 'validated', 'shipped'],
    ).exists()

    if replenishment.approved_quantity and received_quantity >= replenishment.approved_quantity:
        replenishment.status = 'completed'
        replenishment.completed_at = timezone.now()
    elif transfer_in_progress:
        replenishment.status = 'accepted'
    elif received_quantity:
        replenishment.status = 'partially_received'
        replenishment.completed_at = None
    else:
        replenishment.status = 'accepted'
    replenishment.save(update_fields=['status', 'completed_at', 'updated_at'])


class StockReplenishmentRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = StockReplenishmentRequestSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockReplenishmentRequestAccessPermission,
    ]

    def get_queryset(self):
        return replenishment_requests_for_user(self.request.user)

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {'detail': 'Une demande ouverte existe déjà pour ce produit dans cette boutique.'},
                status=status.HTTP_409_CONFLICT,
            )

    def perform_create(self, serializer):
        user = self.request.user
        shop = serializer.validated_data['shop']
        if user.has_role('sales') and not (
            user.has_role('admin') or user.has_role('stock') or getattr(user, 'is_superuser', False)
        ):
            from sales.utils import sales_locations_for_user

            allowed = sales_locations_for_user(user)
        else:
            allowed = accessible_locations(user)
        if not allowed.filter(pk=shop.pk).exists():
            raise PermissionDenied('Vous ne pouvez demander un ravitaillement que pour une boutique autorisée.')

        replenishment = serializer.save(requested_by=user)
        User = get_user_model()
        tenant = tenant_for_user(user)
        authorized_ids = set(shop.authorized_users.values_list('pk', flat=True))
        recipients = []
        for candidate in User.objects.filter(is_active=True):
            if tenant_for_user(candidate) != tenant:
                continue
            if candidate.has_role('admin') or getattr(candidate, 'is_superuser', False):
                recipients.append(candidate)
            elif candidate.has_role('stock') and (
                not authorized_ids or candidate.pk in authorized_ids
            ):
                recipients.append(candidate)

        Notification.objects.bulk_create([
            Notification(
                recipient_user=recipient,
                channel='internal',
                event_type='stock_replenishment_requested',
                message=(
                    f'{replenishment.reference} : {replenishment.requested_quantity} unité(s) de '
                    f'{replenishment.product.name} demandée(s) pour {shop.name}.'
                ),
            )
            for recipient in recipients
        ])
        AuditLog.objects.create(
            user=user,
            action='stock',
            model_name='StockReplenishmentRequest',
            record_id=replenishment.id,
            details=(
                f'Demande {replenishment.reference}: {replenishment.requested_quantity} unité(s) '
                f'de {replenishment.product.name} pour {shop.name}.'
            ),
        )


class StockReplenishmentRequestActionView(generics.GenericAPIView):
    serializer_class = StockReplenishmentRequestSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        StockReplenishmentRequestAccessPermission,
    ]

    def get_queryset(self):
        return replenishment_requests_for_user(self.request.user)

    @transaction.atomic
    def post(self, request, pk, action, *args, **kwargs):
        replenishment = self.get_object()
        replenishment = StockReplenishmentRequest.objects.select_for_update().get(
            pk=replenishment.pk,
        )
        if action == 'reject':
            if replenishment.status != 'requested':
                return Response(
                    {'detail': 'Seule une demande en attente peut être refusée.'},
                    status=status.HTTP_409_CONFLICT,
                )
            reason = str(request.data.get('reason', '')).strip()
            if not reason:
                return Response(
                    {'reason': 'Un motif est obligatoire pour refuser la demande.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            replenishment.status = 'rejected'
            replenishment.refusal_reason = reason
            replenishment.reviewed_by = request.user
            replenishment.reviewed_at = timezone.now()
            replenishment.save(update_fields=[
                'status', 'refusal_reason', 'reviewed_by', 'reviewed_at', 'updated_at',
            ])
            AuditLog.objects.create(
                user=request.user,
                action='stock',
                model_name='StockReplenishmentRequest',
                record_id=replenishment.id,
                details=f'Demande {replenishment.reference} refusée. Motif: {reason}',
            )
            return Response(self.get_serializer(replenishment).data, status=status.HTTP_200_OK)

        if action != 'accept':
            return Response({'detail': 'Action de ravitaillement inconnue.'}, status=status.HTTP_404_NOT_FOUND)
        if replenishment.status not in {'requested', 'partially_received'}:
            return Response(
                {'detail': 'Cette demande ne peut plus être acceptée.'},
                status=status.HTTP_409_CONFLICT,
            )

        received_quantity = replenishment.transfers.filter(status='received').aggregate(
            total=Sum('quantity_received'),
        )['total'] or 0
        committed_quantity = replenishment.transfers.filter(
            status__in=['requested', 'validated', 'shipped'],
        ).aggregate(total=Sum('quantity'))['total'] or 0
        remaining_quantity = replenishment.requested_quantity - received_quantity - committed_quantity
        if remaining_quantity <= 0:
            return Response(
                {'detail': 'La quantité demandée est déjà réceptionnée ou en cours de transfert.'},
                status=status.HTTP_409_CONFLICT,
            )

        allocations = request.data.get('allocations')
        if not isinstance(allocations, list) or not allocations:
            return Response(
                {'allocations': 'Sélectionnez au moins un emplacement source.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed_locations = accessible_locations(request.user)
        seen_sources = set()
        parsed_allocations = []
        allocation_total = 0
        for allocation in allocations:
            if not isinstance(allocation, dict):
                return Response(
                    {'allocations': 'Chaque source doit préciser un emplacement et une quantité.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                source_value = Decimal(str(allocation.get('location')))
                quantity_value = Decimal(str(allocation.get('quantity')))
                if (
                    not source_value.is_finite()
                    or not quantity_value.is_finite()
                    or source_value != source_value.to_integral_value()
                    or quantity_value != quantity_value.to_integral_value()
                ):
                    raise InvalidOperation
                source_id = int(source_value)
                quantity = int(quantity_value)
            except (InvalidOperation, TypeError, ValueError):
                return Response(
                    {'allocations': 'Les emplacements et quantités doivent être valides.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if source_id in seen_sources or quantity <= 0:
                return Response(
                    {'allocations': 'Chaque source doit être unique et sa quantité positive.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            source = allowed_locations.filter(pk=source_id, is_active=True).first()
            if source is None or source.pk == replenishment.shop_id:
                raise PermissionDenied('Vous ne pouvez pas utiliser cet emplacement comme source.')
            stock_item = StockItem.objects.select_for_update().filter(
                product=replenishment.product,
                location=source,
            ).first()
            current_stock = stock_item.quantity if stock_item else 0
            already_committed = StockTransfer.objects.filter(
                product=replenishment.product,
                from_location=source,
                status__in=['requested', 'validated'],
            ).aggregate(total=Sum('quantity'))['total'] or 0
            if quantity > current_stock - already_committed:
                return Response(
                    {'allocations': f'Stock disponible insuffisant à {source.name}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen_sources.add(source_id)
            parsed_allocations.append((source, quantity))
            allocation_total += quantity

        if allocation_total != remaining_quantity:
            return Response(
                {'allocations': f'Répartissez exactement les {remaining_quantity} unité(s) restantes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_admin = request.user.has_role('admin') or getattr(request.user, 'is_superuser', False)
        transfer_offset = replenishment.transfers.count()
        for index, (source, quantity) in enumerate(parsed_allocations, start=1):
            StockTransfer.objects.create(
                product=replenishment.product,
                from_location=source,
                to_location=replenishment.shop,
                replenishment_request=replenishment,
                quantity=quantity,
                reference=f'TR-{replenishment.reference}-{transfer_offset + index}',
                status='validated' if is_admin else 'requested',
                approved_by=request.user if is_admin else None,
                notes=f'Demande de ravitaillement {replenishment.reference}. {replenishment.request_reason}'.strip(),
                created_by=request.user,
            )

        replenishment.approved_quantity = replenishment.requested_quantity
        replenishment.status = 'accepted'
        replenishment.reviewed_by = request.user
        replenishment.reviewed_at = timezone.now()
        replenishment.save(update_fields=[
            'approved_quantity', 'status', 'reviewed_by', 'reviewed_at', 'updated_at',
        ])
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='StockReplenishmentRequest',
            record_id=replenishment.id,
            details=(
                f'Demande {replenishment.reference} acceptée, {allocation_total} unité(s) '
                f'allouée(s) depuis {len(parsed_allocations)} emplacement(s).'
            ),
        )
        return Response(self.get_serializer(replenishment).data, status=status.HTTP_200_OK)


class CartonListCreateView(generics.ListCreateAPIView):
    queryset = Carton.objects.select_related('product', 'location').all()
    serializer_class = CartonSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        CartonAccessPermission,
    ]

    def get_queryset(self):
        return Carton.objects.select_related('product', 'location').filter(
            location__in=accessible_locations(self.request.user),
        )

    def perform_create(self, serializer):
        location = serializer.validated_data['location']
        if not accessible_locations(self.request.user).filter(pk=location.pk).exists():
            raise PermissionDenied('Vous ne pouvez gérer que les cartons de vos emplacements autorisés.')
        carton = serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            action='stock',
            model_name='Carton',
            record_id=carton.id,
            details=f'Carton créé: {carton.reference}, {carton.quantity} unité(s), {carton.location.name}.',
        )


class SampleCartonListCreateView(generics.ListAPIView):
    queryset = SampleCarton.objects.select_related('product', 'location').all()
    serializer_class = SampleCartonSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
    ]

    def get_queryset(self):
        return self.queryset.filter(location__in=accessible_locations(self.request.user))


class CartonDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Carton.objects.select_related('product', 'location').all()
    serializer_class = CartonSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        CartonAccessPermission,
        StockOperationsMutationPermission,
    ]

    def get_queryset(self):
        return Carton.objects.select_related('product', 'location').filter(
            location__in=accessible_locations(self.request.user),
        )

    def perform_update(self, serializer):
        location = serializer.validated_data.get('location', serializer.instance.location)
        if not accessible_locations(self.request.user).filter(pk=location.pk).exists():
            raise PermissionDenied('Vous ne pouvez déplacer un carton que vers un emplacement autorisé.')
        carton = serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            action='stock',
            model_name='Carton',
            record_id=carton.id,
            details=f'Carton mis à jour: {carton.reference}, {carton.location.name}.',
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'La suppression physique d’un carton est interdite.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class CartonMovementHistoryView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        CartonAccessPermission,
    ]

    def get(self, request, pk, *args, **kwargs):
        carton = (
            Carton.objects.select_related('purchase_receipt', 'location')
            .filter(pk=pk, location__in=accessible_locations(request.user))
            .first()
        )
        if carton is None:
            raise NotFound('Carton introuvable ou non autorisé.')

        movements = []
        if carton.purchase_receipt_id:
            movements.append({
                'type': 'receipt',
                'reference': carton.purchase_receipt.reference,
                'quantity': carton.initial_quantity,
                'from_location': None,
                'to_location': carton.purchase_receipt.location.name
                if carton.purchase_receipt.location_id else carton.location.name,
                'status': carton.purchase_receipt.status,
                'created_at': carton.purchase_receipt.created_at,
            })
        else:
            movements.append({
                'type': 'registration',
                'reference': carton.reference,
                'quantity': carton.initial_quantity,
                'from_location': None,
                'to_location': carton.location.name,
                'status': 'tracked',
                'created_at': carton.created_at,
            })
        for allocation in carton.transfer_allocations.select_related(
            'transfer__from_location',
            'transfer__to_location',
        ).all():
            transfer = allocation.transfer
            movements.append({
                'type': 'transfer',
                'reference': transfer.reference,
                'quantity': allocation.quantity_shipped,
                'quantity_received': allocation.quantity_received,
                'from_location': transfer.from_location.name,
                'to_location': transfer.to_location.name,
                'status': transfer.status,
                'created_at': transfer.created_at,
            })
        for origin in carton.sale_origins.select_related(
            'sale_item__sale',
            'location',
        ).all():
            sale = origin.sale_item.sale
            movements.append({
                'type': 'sale',
                'reference': f'SALE-{sale.pk}',
                'quantity': origin.quantity,
                'from_location': origin.location.name if origin.location_id else None,
                'to_location': None,
                'status': sale.status,
                'created_at': origin.created_at,
            })

        unit_references = carton.units.values('reference')
        unit_movements = StockMovement.objects.filter(
            reference__in=unit_references,
        ).select_related('location')
        movements.extend(
            {
                'type': (
                    'sample' if movement.movement_type == 'out' else 'sample_return'
                ),
                'reference': movement.reference,
                'quantity': movement.quantity,
                'from_location': (
                    movement.location.name if movement.movement_type == 'out' else None
                ),
                'to_location': (
                    movement.location.name if movement.movement_type == 'in' else None
                ),
                'status': movement.movement_type,
                'created_at': movement.created_at,
            }
            for movement in unit_movements
        )
        movements.sort(key=lambda movement: movement['created_at'])
        return Response({
            'carton': carton.reference,
            'product': carton.product_id,
            'location': carton.location.name,
            'quantity': carton.quantity,
            'initial_quantity': carton.initial_quantity,
            'movements': movements,
        })


class StockUnitStatusView(generics.GenericAPIView):
    queryset = StockUnit.objects.select_related(
        'location',
        'carton__product',
        'carton__location',
    ).all()
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        CartonAccessPermission,
        StockOperationsMutationPermission,
    ]

    def get_queryset(self):
        return self.queryset.filter(location__in=accessible_locations(self.request.user))

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        unit_ref = StockUnit.objects.filter(
            pk=kwargs['pk'],
            location__in=accessible_locations(request.user),
        ).values('carton__product_id').first()
        if unit_ref is None:
            return Response({'detail': 'Pièce introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        product = Product.objects.select_for_update().get(pk=unit_ref['carton__product_id'])
        unit = StockUnit.objects.select_for_update().select_related(
            'location',
            'carton__product',
            'carton__location',
        ).filter(
            pk=kwargs['pk'],
            location__in=accessible_locations(request.user),
        ).first()
        if unit is None:
            return Response({'detail': 'Pièce introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        target_status = request.data.get('status')
        if target_status not in {'available', 'sample'}:
            return Response(
                {'status': 'Le statut doit être disponible ou échantillon.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if unit.status not in {'available', 'sample'}:
            return Response(
                {'detail': 'Le statut de cette pièce ne peut plus être modifié.'},
                status=status.HTTP_409_CONFLICT,
            )
        if unit.status == target_status:
            return Response({'detail': 'Cette pièce possède déjà ce statut.'}, status=status.HTTP_409_CONFLICT)

        carton = Carton.objects.select_for_update().get(pk=unit.carton_id)
        stock_item, _ = StockItem.objects.select_for_update().get_or_create(
            product_id=carton.product_id,
            location_id=unit.location_id,
        )
        if target_status == 'sample':
            if (
                stock_item.quantity <= 0
                or (carton.location_id == unit.location_id and carton.quantity <= 0)
                or (product.quantity or 0) <= 0
            ):
                return Response(
                    {'detail': 'La pièce ne peut pas devenir un échantillon car le stock est insuffisant.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if carton.location_id == unit.location_id:
                carton.quantity -= 1
            stock_item.quantity -= 1
            product.quantity -= 1
            movement_type = 'out'
            notes = f'Échantillon individuel: {unit.reference}'
        else:
            if carton.location_id == unit.location_id:
                carton.quantity += 1
            stock_item.quantity += 1
            product.quantity = (product.quantity or 0) + 1
            movement_type = 'in'
            notes = f'Pièce d’échantillon remise en stock: {unit.reference}'

        if carton.location_id == unit.location_id:
            carton.save(update_fields=['quantity', 'updated_at'])
        stock_item.save(update_fields=['quantity', 'updated_at'])
        product.save(update_fields=['quantity', 'updated_at'])
        unit.status = target_status
        unit.save(update_fields=['status', 'updated_at'])
        StockMovement.objects.create(
            product=product,
            location=unit.location,
            movement_type=movement_type,
            quantity=1,
            reference=unit.reference,
            notes=notes,
            created_by=request.user,
        )
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='StockUnit',
            record_id=unit.id,
            details=f'Statut de la pièce {unit.reference}: {target_status}.',
        )
        return Response({
            'id': unit.id,
            'reference': unit.reference,
            'status': unit.status,
            'location': unit.location_id,
            'location_name': unit.location.name,
        }, status=status.HTTP_200_OK)


class StockUnitListView(generics.ListAPIView):
    serializer_class = StockUnitSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
    ]

    def list(self, request, *args, **kwargs):
        if not request.query_params.get('product') or not request.query_params.get('location'):
            return Response(
                {'detail': 'Le produit et l’emplacement sont obligatoires.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            product_id = int(request.query_params['product'])
            location_id = int(request.query_params['location'])
        except (TypeError, ValueError):
            return Response(
                {'detail': 'Le produit et l’emplacement doivent être valides.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if product_id <= 0 or location_id <= 0:
            return Response(
                {'detail': 'Le produit et l’emplacement doivent être valides.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not accessible_locations(request.user).filter(pk=location_id).exists():
            raise NotFound('Emplacement introuvable ou non autorisé.')
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        return StockUnit.objects.select_related(
            'location',
            'carton__product',
        ).filter(
            location_id=self.request.query_params.get('location'),
            carton__product_id=self.request.query_params.get('product'),
        ).order_by('carton__created_at', 'carton_id', 'unit_number')


class StockUnitInitializeView(generics.GenericAPIView):
    serializer_class = StockUnitInitializationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('inventory'),
        StockOperationsMutationPermission,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = Product.objects.select_for_update().get(
            pk=serializer.validated_data['product'].pk,
        )
        location = accessible_locations(request.user).filter(
            pk=serializer.validated_data['location'].pk,
            is_active=True,
        ).first()
        if location is None:
            raise NotFound('Emplacement introuvable ou non autorisé.')

        unit_filter = {'carton__product': product, 'location': location}
        tracked_before = StockUnit.objects.filter(**unit_filter).count()
        cartons = Carton.objects.select_for_update().filter(
            product=product,
            location=location,
            quantity__gt=0,
        ).order_by('id')
        for carton in cartons:
            ensure_carton_units(carton)

        tracked_units = StockUnit.objects.filter(**unit_filter)
        tracked_count = tracked_units.count()
        stock_item = StockItem.objects.filter(product=product, location=location).first()
        saleable_quantity = stock_item.quantity if stock_item else 0
        sample_quantity = tracked_units.filter(status='sample').count()
        tracked_available_quantity = tracked_units.filter(status='available').count()
        created_count = max(tracked_count - tracked_before, 0)
        untracked_quantity = max(saleable_quantity - tracked_available_quantity, 0)
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='StockUnitInitialization',
            record_id=location.pk,
            details=(
                f'Traçabilité préparée pour {product.sku} à {location.name}: '
                f'{created_count} unité(s) ajoutée(s).'
            ),
        )
        return Response({
            'product': product.pk,
            'location': location.pk,
            'created_count': created_count,
            'saleable_quantity': saleable_quantity,
            'sample_quantity': sample_quantity,
            'physical_quantity': saleable_quantity + sample_quantity,
            'tracked_available_quantity': tracked_available_quantity,
            'untracked_saleable_quantity': untracked_quantity,
        }, status=status.HTTP_200_OK)


class InventoryCountListCreateView(generics.ListCreateAPIView):
    queryset = InventoryCount.objects.select_related('location').prefetch_related('items__product').all()
    serializer_class = InventoryCountSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        InventoryCountAccessPermission,
    ]

    def get_queryset(self):
        return self.queryset.filter(location__in=accessible_locations(self.request.user))

    def perform_create(self, serializer):
        location = serializer.validated_data['location']
        if not accessible_locations(self.request.user).filter(pk=location.pk).exists():
            raise PermissionDenied('Vous ne pouvez inventorier que vos emplacements autorisés.')
        serializer.save(created_by=self.request.user)


class InventoryCountDetailView(generics.RetrieveUpdateAPIView):
    queryset = InventoryCount.objects.select_related('location').prefetch_related('items__product').all()
    serializer_class = InventoryCountSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        InventoryCountAccessPermission,
    ]

    def get_queryset(self):
        return self.queryset.filter(location__in=accessible_locations(self.request.user))


class InventoryCountValidateView(generics.GenericAPIView):
    queryset = InventoryCount.objects.select_related('location').prefetch_related('items__product').all()
    serializer_class = InventoryCountSerializer
    action = 'validate'
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsAdminUser,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        count = InventoryCount.objects.select_for_update().filter(
            pk=kwargs['pk'],
            location__in=accessible_locations(request.user),
        ).first()
        if count is None:
            return Response({'detail': 'Inventaire introuvable ou non autorisé.'}, status=status.HTTP_404_NOT_FOUND)
        if count.status != 'submitted':
            return Response(
                {'detail': 'L’inventaire doit être soumis avant sa validation.'},
                status=status.HTTP_409_CONFLICT,
            )

        for line in count.items.select_related('product').order_by('product_id', 'id'):
            product = Product.objects.select_for_update().get(pk=line.product_id)
            line.product = product
            stock, _ = StockItem.objects.select_for_update().get_or_create(
                product=product,
                location=count.location,
            )
            difference = line.counted_quantity - stock.quantity
            if difference == 0:
                continue
            if difference > 0:
                record_cost_layer(
                    product=product,
                    location=count.location,
                    quantity=difference,
                    unit_cost=(
                        line.product.cost_price
                        if line.product.cost_price > 0 else None
                    ),
                    source='adjustment',
                    reference=count.number,
                )
            else:
                consumed_cartons = consume_fifo_cartons(
                    product=product,
                    quantity=abs(difference),
                    location=count.location,
                    unit_status='written_off',
                )
                consume_fifo_cost(
                    product=line.product,
                    quantity=abs(difference),
                    location=count.location,
                )
            stock.quantity = line.counted_quantity
            stock.save(update_fields=['quantity', 'updated_at'])
            product.quantity = (
                StockItem.objects.filter(product=product).aggregate(total=Sum('quantity'))['total'] or 0
            )
            product.save(update_fields=['quantity', 'updated_at'])
            StockMovement.objects.create(
                product=product,
                location=count.location,
                movement_type='adjustment',
                quantity=line.counted_quantity,
                reference=count.number,
                notes=(
                    f'{count.number}: {count.notes}'
                    + (
                        ' Cartons réduits FIFO: '
                        + ', '.join(
                            f'{carton.reference} x {quantity}'
                            for carton, quantity in consumed_cartons
                        )
                        + '.'
                        if difference < 0 and consumed_cartons
                        else (
                            f' Écart positif de {difference} unité(s) laissé non affecté à un carton.'
                            if difference > 0
                            else ''
                        )
                    )
                ),
                created_by=request.user,
            )

        count.status = 'validated'
        count.validated_at = timezone.now()
        count.save(update_fields=['status', 'validated_at'])
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='InventoryCount',
            record_id=count.id,
            details=(
                f'Inventaire validé: {count.number}. '
                f'Soumis par {count.submitted_by_id or "inconnu"} le {count.submitted_at}. '
                f'Motif: {count.notes}'
            ),
        )
        return Response(self.get_serializer(count).data, status=status.HTTP_200_OK)


class InventoryCountSubmitView(generics.GenericAPIView):
    queryset = InventoryCount.objects.select_related('location').prefetch_related('items__product').all()
    serializer_class = InventoryCountSerializer
    action = 'submit'
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        InventoryCountAccessPermission,
    ]

    def get_queryset(self):
        return self.queryset.filter(location__in=accessible_locations(self.request.user))

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        count = self.get_object()
        if count.status != 'draft':
            return Response({'detail': 'Seul un brouillon peut être soumis.'}, status=status.HTTP_409_CONFLICT)
        if not count.notes.strip():
            return Response(
                {'notes': ['Veuillez indiquer le motif ou les observations avant la soumission.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        count.status = 'submitted'
        count.submitted_by = request.user
        count.submitted_at = timezone.now()
        count.save(update_fields=['status', 'submitted_by', 'submitted_at'])
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='InventoryCount',
            record_id=count.id,
            details=f'Inventaire soumis pour validation: {count.number}. Motif: {count.notes}',
        )
        return Response(self.get_serializer(count).data, status=status.HTTP_200_OK)
