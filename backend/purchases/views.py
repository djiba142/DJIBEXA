from smtplib import SMTPException
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.mailer import create_branded_email
from core.models import AuditLog
from core.tenancy import tenant_scoped_queryset
from inventory.access import accessible_locations
from inventory.costing import record_cost_layer
from inventory.models import Carton, InventoryLocation, StockItem, StockMovement, StockUnit
from products.models import Product
from users.permissions import (
    CartonAccessPermission,
    IsAdminUser,
    IsTenantAssignedUser,
    PurchaseOrderAccessPermission,
    PurchaseReceiptAccessPermission,
)

from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    ReceiptQuarantine,
)
from .receipt_imports import parse_receipt_import
from .serializers import (
    PurchaseOrderSerializer,
    PurchaseReceiptSerializer,
    ReceiptQuarantineSerializer,
    validate_purchase_receipt,
)


class PurchaseOrderListCreateView(generics.ListCreateAPIView):
    queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items__product').all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseOrderAccessPermission,
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
        )
        if self.request.user.has_role('stock') and not self.request.user.has_role('admin'):
            queryset = queryset.filter(
                Q(status__in=['approved', 'partial_received']) |
                Q(status__in=['draft', 'submitted'], created_by=self.request.user)
            )
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class PurchaseReplenishmentSuggestionsView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseOrderAccessPermission,
    ]

    def get(self, request, *args, **kwargs):
        products = tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            request.user,
        ).order_by('name')
        on_hand = {
            item['product_id']: item['quantity_total'] or 0
            for item in StockItem.objects.filter(
                product__in=products,
            ).values('product_id').annotate(quantity_total=Sum('quantity'))
        }
        open_ordered = {
            item['product_id']: item['quantity_total'] or 0
            for item in tenant_scoped_queryset(
                PurchaseOrderItem.objects.filter(
                purchase_order__status__in=['approved', 'partial_received'],
                ),
                request.user,
                tenant_field='purchase_order__tenant',
            ).filter(product__in=products).values('product_id').annotate(quantity_total=Sum('quantity'))
        }
        received = {
            item['product_id']: item['quantity_total'] or 0
            for item in tenant_scoped_queryset(
                PurchaseReceiptItem.objects.filter(
                    purchase_receipt__status='received',
                    purchase_receipt__purchase_order__status__in=['approved', 'partial_received'],
                ),
                request.user,
                tenant_field='purchase_receipt__purchase_order__tenant',
            ).filter(product__in=products).values('product_id').annotate(
                quantity_total=Sum('quantity_received'),
            )
        }

        suggestions = []
        for product in products:
            physical = on_hand.get(product.id, product.quantity)
            inbound = max(0, open_ordered.get(product.id, 0) - received.get(product.id, 0))
            suggested = max(0, product.alert_threshold - physical - inbound)
            if suggested:
                suggestions.append({
                    'product_id': product.id,
                    'name': product.name,
                    'reference': product.sku,
                    'physical_quantity': physical,
                    'alert_threshold': product.alert_threshold,
                    'open_order_quantity': inbound,
                    'suggested_quantity': suggested,
                })

        return Response({
            'suggestions': suggestions,
            'limitations': [
                'La suggestion utilise le stock physique accepté, le seuil minimum et les quantités restant sur les commandes approuvées.',
                'Les réservations, l’historique des ventes et les délais fournisseur ne sont pas disponibles dans les données actuelles.',
            ],
        })


class PurchaseOrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items__product').all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseOrderAccessPermission,
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
        )
        if self.request.user.has_role('stock') and not self.request.user.has_role('admin'):
            queryset = queryset.filter(
                Q(status__in=['approved', 'partial_received']) |
                Q(status__in=['draft', 'submitted'], created_by=self.request.user)
            )
        return queryset


class PurchaseOrderActionView(generics.GenericAPIView):
    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseOrderAccessPermission,
    ]

    @extend_schema(operation_id='purchase_order_action')
    @transaction.atomic
    def post(self, request, action, *args, **kwargs):
        order = tenant_scoped_queryset(
            PurchaseOrder.objects.select_for_update(),
            request.user,
        ).filter(pk=kwargs['pk']).first()
        if order is None:
            return Response({'detail': 'Commande introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, order)
        if (
            request.user.has_role('stock')
            and not request.user.has_role('admin')
            and action != 'send'
        ):
            raise PermissionDenied('Seule la soumission de son brouillon est autorisée au gestionnaire de stock.')
        transitions = {
            'send': ('draft', 'submitted'),
            'confirm': ('submitted', 'approved'),
            'close': ('received', 'closed'),
        }
        transition = transitions.get(action)
        if action == 'cancel':
            if order.status not in {'draft', 'submitted', 'approved'} or order.receipts.filter(
                status__in=['draft', 'submitted', 'changes_requested', 'on_hold', 'received'],
            ).exists():
                return Response(
                    {'detail': 'La commande ne peut pas être annulée pendant ou après une réception.'},
                    status=status.HTTP_409_CONFLICT,
                )
            reason = str(request.data.get('reason', '')).strip()
            if not reason:
                return Response(
                    {'reason': 'Un motif est obligatoire pour annuler la commande.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.status = 'cancelled'
            order.decision_reason = reason
            order.save(update_fields=['status', 'decision_reason', 'updated_at'])
            AuditLog.objects.create(
                user=request.user,
                action='purchase_order',
                model_name='PurchaseOrder',
                record_id=order.id,
                details=f'Commande annulée: {order.reference}. Motif: {reason}',
            )
            return Response(self.get_serializer(order).data, status=status.HTTP_200_OK)
        if transition is None:
            return Response({'detail': 'Action de commande inconnue.'}, status=status.HTTP_404_NOT_FOUND)

        expected, target = transition
        if order.status not in (expected if isinstance(expected, tuple) else (expected,)):
            return Response(
                {'detail': f'La commande ne peut pas passer à l’état {target} depuis {order.status}.'},
                status=status.HTTP_409_CONFLICT,
            )

        order.status = target
        order.save(update_fields=['status', 'updated_at'])
        AuditLog.objects.create(
            user=request.user,
            action='purchase_order',
            model_name='PurchaseOrder',
            record_id=order.id,
            details=f'Commande {order.reference}: {expected} → {target}',
        )
        return Response(self.get_serializer(order).data, status=status.HTTP_200_OK)


class PurchaseOrderEmailView(generics.GenericAPIView):
    action = 'email'
    queryset = PurchaseOrder.objects.select_related('supplier')
    serializer_class = PurchaseOrderSerializer
    parser_classes = [FormParser, MultiPartParser]
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseOrderAccessPermission,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        order = tenant_scoped_queryset(
            PurchaseOrder.objects.select_for_update().select_related('supplier'),
            request.user,
        ).filter(pk=kwargs['pk']).first()
        if order is None:
            return Response({'detail': 'Commande introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, order)
        if order.status != 'draft':
            return Response(
                {'detail': 'Seul un brouillon peut être envoyé par e-mail.'},
                status=status.HTTP_409_CONFLICT,
            )
        if not order.items.exists():
            return Response(
                {'detail': 'Ajoutez au moins un produit avant d’envoyer la commande.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recipient = order.supplier.email.strip()
        if not recipient:
            return Response(
                {'email': 'Aucune adresse e-mail fournisseur n’est enregistrée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if settings.EMAIL_BACKEND in {
            'django.core.mail.backends.console.EmailBackend',
            'django.core.mail.backends.dummy.EmailBackend',
            'django.core.mail.backends.filebased.EmailBackend',
            'django.core.mail.backends.locmem.EmailBackend',
        }:
            return Response(
                {'email': 'Un service d’e-mail réel n’est pas configuré pour l’envoi.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        uploaded_pdf = request.FILES.get('file')
        if uploaded_pdf is None:
            return Response(
                {'file': 'Générez et joignez le bon de commande PDF.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded_pdf.size > 10 * 1024 * 1024:
            return Response(
                {'file': 'Le PDF ne doit pas dépasser 10 Mo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        uploaded_pdf.seek(0)
        pdf_bytes = uploaded_pdf.read()
        if not pdf_bytes.startswith(b'%PDF-'):
            return Response(
                {'file': 'Le fichier joint n’est pas un PDF valide.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = create_branded_email(
            subject=f'Bon de commande fournisseur {order.reference}',
            message=(
                f"Bonjour {order.supplier.contact_name or order.supplier.name},\n\n"
                f"Veuillez trouver ci-joint notre bon de commande {order.reference}.\n\n"
                "Cordialement"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
        )
        message.attach(
            f'{order.reference}.pdf',
            pdf_bytes,
            'application/pdf',
        )
        try:
            sent_count = message.send(fail_silently=False)
        except (SMTPException, OSError) as error:
            return Response(
                {'email': f'L’envoi au fournisseur a échoué : {error}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if sent_count != 1:
            return Response(
                {'email': 'Le fournisseur n’a pas reçu le message : le service e-mail a refusé l’envoi.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        order.status = 'submitted'
        order.save(update_fields=['status', 'updated_at'])
        AuditLog.objects.create(
            user=request.user,
            action='purchase_order',
            model_name='PurchaseOrder',
            record_id=order.pk,
            details=f'Commande fournisseur {order.reference} envoyée par e-mail à {recipient}.',
        )
        return Response(
            {'detail': 'Bon de commande envoyé au fournisseur.', 'status': order.status},
            status=status.HTTP_200_OK,
        )


class PurchaseReceiptListCreateView(generics.ListCreateAPIView):
    queryset = PurchaseReceipt.objects.select_related('purchase_order__supplier').prefetch_related('items__product').all()
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseReceiptAccessPermission,
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='purchase_order__tenant',
        )
        user = self.request.user
        if not user.has_role('admin') and not getattr(user, 'is_superuser', False):
            if InventoryLocation.objects.filter(authorized_users__isnull=False).exists():
                queryset = queryset.filter(location__authorized_users=user)
        return queryset

    def perform_create(self, serializer):
        location = serializer.validated_data.get('location')
        user = self.request.user
        if (
            user.has_role('stock')
            and not user.has_role('admin')
            and InventoryLocation.objects.filter(authorized_users__isnull=False).exists()
            and (location is None or not location.authorized_users.filter(pk=user.pk).exists())
        ):
            raise PermissionDenied('Vous ne pouvez réceptionner que dans un emplacement autorisé.')
        serializer.save()


class PurchaseReceiptBatchCreateView(generics.GenericAPIView):
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseReceiptAccessPermission,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        receipts_data = request.data.get('receipts')
        if not isinstance(receipts_data, list) or not receipts_data:
            raise serializers.ValidationError({
                'receipts': 'Ajoutez au moins une réception avec un entrepôt et des lignes.',
            })

        user = request.user
        serializer_instances = []
        authorized_locations_exist = InventoryLocation.objects.filter(
            authorized_users__isnull=False,
        ).exists()
        references = set()
        for index, receipt_data in enumerate(receipts_data):
            if not isinstance(receipt_data, dict):
                raise serializers.ValidationError({
                    'receipts': f'La réception {index + 1} doit être un objet.',
                })
            reference = str(receipt_data.get('reference', '')).strip()
            if not reference or reference in references:
                raise serializers.ValidationError({
                    'receipts': f'La référence de la réception {index + 1} est absente ou dupliquée.',
                })
            references.add(reference)
            serializer = self.get_serializer(data=receipt_data)
            serializer.is_valid(raise_exception=True)
            location = serializer.validated_data.get('location')
            if (
                user.has_role('stock')
                and not user.has_role('admin')
                and authorized_locations_exist
                and (
                    location is None
                    or not location.authorized_users.filter(pk=user.pk).exists()
                )
            ):
                raise PermissionDenied(
                    f'Vous ne pouvez pas réceptionner dans l’emplacement de la réception {index + 1}.',
                )
            serializer_instances.append(serializer)

        order_ids = {
            serializer.validated_data['purchase_order'].pk
            for serializer in serializer_instances
        }
        if len(order_ids) != 1:
            raise serializers.ValidationError({
                'receipts': 'Toutes les lignes réparties doivent appartenir à la même commande.',
            })
        order = tenant_scoped_queryset(
            PurchaseOrder.objects.select_for_update(),
            user,
        ).filter(pk=order_ids.pop()).first()
        if order is None:
            return Response({'detail': 'Commande introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        ordered_quantities = {
            item.product_id: item.quantity
            for item in order.items.all()
        }
        existing_quantities = {
            row['product_id']: row['total']
            for row in PurchaseReceiptItem.objects.filter(
                purchase_receipt__purchase_order=order,
            ).exclude(
                purchase_receipt__status='cancelled',
            ).values('product_id').annotate(total=Sum('quantity_received'))
        }
        incoming_quantities = {}
        for serializer in serializer_instances:
            for item in serializer.validated_data['items']:
                product_id = item['product'].pk
                incoming_quantities[product_id] = (
                    incoming_quantities.get(product_id, 0) + item['quantity_received']
                )
        over_allocated = [
            product_id
            for product_id, quantity in incoming_quantities.items()
            if existing_quantities.get(product_id, 0) + quantity > ordered_quantities.get(product_id, 0)
        ]
        if over_allocated:
            raise serializers.ValidationError({
                'receipts': 'Les quantités réparties dépassent les quantités encore disponibles sur la commande.',
            })

        created = [serializer.save() for serializer in serializer_instances]
        return Response(
            self.get_serializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class PurchaseReceiptImportView(generics.GenericAPIView):
    serializer_class = PurchaseReceiptSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseReceiptAccessPermission,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get('file')
        if uploaded_file is None:
            raise serializers.ValidationError({'file': 'Sélectionnez un fichier de réception.'})

        order = tenant_scoped_queryset(
            PurchaseOrder.objects.select_related('supplier').prefetch_related('items__product'),
            request.user,
        ).filter(pk=request.data.get('purchase_order')).first()
        if order is None:
            raise serializers.ValidationError({'purchase_order': 'Commande introuvable.'})
        if order.status not in {'approved', 'partial_received'}:
            raise serializers.ValidationError({
                'purchase_order': 'La commande doit être approuvée avant sa réception.',
            })

        locations = list(accessible_locations(request.user).filter(is_active=True))
        default_location = next(
            (
                location for location in locations
                if str(location.pk) == str(request.data.get('location', ''))
            ),
            None,
        )
        preview = parse_receipt_import(
            uploaded_file,
            order,
            default_location,
            locations,
        )
        if not request.user.has_role('admin') and not getattr(request.user, 'is_superuser', False):
            for row in preview['rows']:
                row.pop('unit_cost', None)

        action = request.data.get('action', 'preview')
        if action == 'preview':
            return Response(preview, status=status.HTTP_200_OK)
        if action != 'confirm':
            raise serializers.ValidationError({'action': 'Action d’import inconnue.'})
        if preview['errors']:
            raise serializers.ValidationError({'errors': preview['errors']})

        grouped_rows = {}
        for row in preview['rows']:
            if row['quantity_received'] > 0:
                grouped_rows.setdefault(row['location'], []).append(row)
        if not grouped_rows:
            raise serializers.ValidationError({
                'file': 'Le fichier ne contient aucune quantité réellement reçue supérieure à zéro.',
            })

        receipt_reason = str(request.data.get('discrepancy_reason', '')).strip()
        receipt_notes = []
        if preview['source_reference']:
            receipt_notes.append(f"Référence du bon importé : {preview['source_reference']}")
        if preview['source_name']:
            receipt_notes.append(f"Fichier source : {preview['source_name']}")
        if request.data.get('notes'):
            receipt_notes.append(str(request.data['notes']).strip())
        receipt_notes = '\n'.join(note for note in receipt_notes if note)

        created = []
        for location_id, rows in grouped_rows.items():
            receipt_data = {
                'purchase_order': order.pk,
                'location': location_id,
                'reference': f"REC-IMP-{timezone.now():%Y%m%d%H%M%S}-{uuid4().hex[:8]}",
                'allocation_method': 'value',
                'notes': receipt_notes,
                'supplier_document_reference': preview['supplier_document_reference'],
                'discrepancy_reason': receipt_reason,
                'items': [
                    {
                        'product': row['product'],
                        'quantity_received': row['quantity_received'],
                        'quantity_accepted': row['quantity_accepted'],
                        'quantity_quarantined': row['quantity_quarantined'],
                        'discrepancy_reason': row['discrepancy_reason'],
                        'items_per_carton': row['items_per_carton'],
                        'supplier_reference': row['supplier_reference'],
                        'supplier_barcode': row['supplier_barcode'],
                        'supplier_lot_reference': row['supplier_lot_reference'],
                        'condition_status': row['condition_status'],
                        'packaging_condition': row['packaging_condition'],
                        'notes': row['notes'],
                        **({'unit_cost': row['unit_cost']} if row.get('unit_cost') is not None else {}),
                    }
                    for row in rows
                ],
            }
            if preview['received_date']:
                receipt_data['received_date'] = preview['received_date']
            serializer = self.get_serializer(data=receipt_data)
            serializer.is_valid(raise_exception=True)
            created.append(serializer.save())

        for receipt in created:
            AuditLog.objects.create(
                user=request.user,
                action='create',
                model_name='PurchaseReceipt',
                record_id=receipt.pk,
                details=f'Brouillon de réception créé par import: {receipt.reference}',
            )
        return Response(
            self.get_serializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class AcquisitionCostListView(generics.ListCreateAPIView):
    queryset = PurchaseReceipt.objects.select_related('purchase_order__supplier').prefetch_related('items__product').all()
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsAdminUser,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='purchase_order__tenant',
        )


class AcquisitionCostDetailView(generics.RetrieveUpdateAPIView):
    queryset = PurchaseReceipt.objects.select_related('purchase_order__supplier').prefetch_related('items__product').all()
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsAdminUser,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='purchase_order__tenant',
        )


class PurchaseReceiptDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PurchaseReceipt.objects.select_related('purchase_order__supplier').prefetch_related('items__product').all()
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseReceiptAccessPermission,
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='purchase_order__tenant',
        )
        user = self.request.user
        if not user.has_role('admin') and not getattr(user, 'is_superuser', False):
            if InventoryLocation.objects.filter(authorized_users__isnull=False).exists():
                queryset = queryset.filter(location__authorized_users=user)
        return queryset

    def perform_destroy(self, instance):
        raise PermissionDenied('La suppression physique d’une réception est interdite.')

    def perform_update(self, serializer):
        receipt = serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            action='stock',
            model_name='PurchaseReceipt',
            record_id=receipt.id,
            details=(
                f'Brouillon de réception modifié: {receipt.reference}, '
                f'version {receipt.version}, statut {receipt.status}.'
            ),
        )


class PurchaseReceiptSubmitView(generics.GenericAPIView):
    queryset = PurchaseReceipt.objects.select_related('purchase_order', 'location').prefetch_related('items')
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseReceiptAccessPermission,
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='purchase_order__tenant',
        )
        user = self.request.user
        if not user.has_role('admin') and not getattr(user, 'is_superuser', False):
            if InventoryLocation.objects.filter(authorized_users__isnull=False).exists():
                queryset = queryset.filter(location__authorized_users=user)
        return queryset

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        receipt = self.get_queryset().select_for_update(of=('self',)).filter(
            pk=kwargs['pk'],
        ).first()
        if receipt is None:
            return Response({'detail': 'Réception introuvable ou non autorisée.'}, status=status.HTTP_404_NOT_FOUND)
        if receipt.status not in {'draft', 'changes_requested'}:
            return Response(
                {'detail': 'Seul un brouillon ou une réception corrigée peut être soumis.'},
                status=status.HTTP_409_CONFLICT,
            )
        if not receipt.location_id:
            return Response(
                {'location': 'Choisissez un emplacement avant de soumettre la réception.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prior_receipts = PurchaseReceipt.objects.filter(
            purchase_order=receipt.purchase_order,
            status__in=['submitted', 'on_hold', 'received'],
        ).exclude(pk=receipt.pk).prefetch_related('items')
        accounted = {}
        for prior_receipt in prior_receipts:
            for line in prior_receipt.items.all():
                accounted[line.product_id] = accounted.get(line.product_id, 0) + line.quantity_received
        ordered = {
            line.product_id: line.quantity
            for line in receipt.purchase_order.items.all()
        }
        for line in receipt.items.all():
            remaining = max(
                ordered.get(line.product_id, 0) - accounted.get(line.product_id, 0),
                0,
            )
            has_variance = line.quantity_received != remaining
            has_quarantine = line.quantity_quarantined > 0
            if (has_variance or has_quarantine) and not (
                line.discrepancy_reason.strip() or receipt.discrepancy_reason.strip()
            ):
                return Response(
                    {
                        'discrepancy_reason': (
                            f"Un motif est obligatoire pour l'écart de "
                            f"{line.product.name} ou sa mise en quarantaine."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        receipt.status = 'submitted'
        receipt.submitted_by = request.user
        receipt.submitted_at = timezone.now()
        receipt.decision_reason = ''
        receipt.save(update_fields=[
            'status', 'submitted_by', 'submitted_at', 'decision_reason', 'updated_at',
        ])
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='PurchaseReceipt',
            record_id=receipt.id,
            details=f'Réception soumise au contrôle: {receipt.reference}',
        )
        return Response(self.get_serializer(receipt).data, status=status.HTTP_200_OK)


class PurchaseReceiptDecisionView(generics.GenericAPIView):
    queryset = PurchaseReceipt.objects.all()
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsAdminUser,
    ]

    @transaction.atomic
    def post(self, request, action, *args, **kwargs):
        receipt = tenant_scoped_queryset(
            PurchaseReceipt.objects.select_for_update(),
            request.user,
            tenant_field='purchase_order__tenant',
        ).filter(pk=kwargs['pk']).first()
        if receipt is None:
            return Response({'detail': 'Réception introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        if receipt.status != 'submitted' and not (
            action == 'resume' and receipt.status == 'on_hold'
        ):
            return Response(
                {'detail': 'Cette réception ne peut pas recevoir cette décision dans son état actuel.'},
                status=status.HTTP_409_CONFLICT,
            )
        reason = str(request.data.get('reason', '')).strip()
        if action not in {'reject', 'request-correction', 'hold', 'resume'}:
            return Response({'detail': 'Décision de réception inconnue.'}, status=status.HTTP_404_NOT_FOUND)
        if not reason:
            return Response(
                {'reason': 'Un motif est obligatoire pour cette décision.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        targets = {
            'reject': 'rejected',
            'request-correction': 'changes_requested',
            'hold': 'on_hold',
            'resume': 'submitted',
        }
        receipt.status = targets[action]
        receipt.decision_reason = reason
        receipt.reviewed_by = request.user
        receipt.reviewed_at = timezone.now()
        receipt.reviewed_version = receipt.version
        receipt.save(update_fields=[
            'status', 'decision_reason', 'reviewed_by', 'reviewed_at',
            'reviewed_version', 'updated_at',
        ])
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='PurchaseReceipt',
            record_id=receipt.id,
            details=f'Décision {action} pour la réception {receipt.reference}: {reason}',
        )
        return Response(self.get_serializer(receipt).data, status=status.HTTP_200_OK)


class PurchaseReceiptValidateView(generics.GenericAPIView):
    queryset = PurchaseReceipt.objects.select_related('purchase_order').prefetch_related('items__product').select_for_update()
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsAdminUser,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        receipt = tenant_scoped_queryset(
            PurchaseReceipt.objects.select_for_update(),
            request.user,
            tenant_field='purchase_order__tenant',
        ).filter(pk=kwargs['pk']).first()
        if receipt is None:
            return Response({'detail': 'Réception introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        if receipt.status != 'submitted':
            return Response(
                {'detail': 'La réception doit être soumise et en attente de validation.'},
                status=status.HTTP_409_CONFLICT,
            )
        if receipt.submitted_by_id == request.user.id:
            raise PermissionDenied('Vous ne pouvez pas valider une réception que vous avez soumise.')
        submitted_version = request.data.get('version')
        try:
            submitted_version = int(submitted_version)
            reviewed_ids = {int(item_id) for item_id in request.data.get('reviewed_item_ids', [])}
        except (TypeError, ValueError):
            return Response(
                {'detail': 'La version et la liste des lignes examinées sont obligatoires.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expected_ids = set(receipt.items.values_list('id', flat=True))
        if submitted_version != receipt.version:
            return Response(
                {'detail': 'La réception a changé depuis son ouverture. Rechargez le dossier avant validation.'},
                status=status.HTTP_409_CONFLICT,
            )
        if reviewed_ids != expected_ids:
            return Response(
                {'reviewed_item_ids': 'Examinez chaque ligne de la réception avant de la valider.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = PurchaseOrder.objects.select_for_update().get(pk=receipt.purchase_order_id)
        prior_quantities = {}
        prior_receipts = PurchaseReceipt.objects.filter(
            purchase_order=order,
            status='received',
        ).exclude(pk=receipt.pk).prefetch_related('items')
        for prior_receipt in prior_receipts:
            for line in prior_receipt.items.all():
                prior_quantities[line.product_id] = prior_quantities.get(line.product_id, 0) + line.quantity_received
        ordered_quantities = {
            line.product_id: line.quantity
            for line in order.items.all()
        }
        for line in receipt.items.select_related('product').all():
            if line.quantity_accepted + line.quantity_quarantined != line.quantity_received:
                return Response(
                    {'detail': f'Les quantités de {line.product.name} ne sont pas cohérentes.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            expected_remaining = max(
                ordered_quantities.get(line.product_id, 0) - prior_quantities.get(line.product_id, 0),
                0,
            )
            if (
                (line.quantity_received != expected_remaining or line.quantity_quarantined > 0)
                and not (line.discrepancy_reason.strip() or receipt.discrepancy_reason.strip())
            ):
                return Response(
                    {'detail': f"Le motif de l'écart pour {line.product.name} est obligatoire."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        validate_purchase_receipt(receipt, request.user)
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='PurchaseReceipt',
            record_id=receipt.id,
            details=f"Réception fournisseur validée: {receipt.reference}",
        )
        return Response(self.get_serializer(receipt).data, status=status.HTTP_200_OK)


class ReceiptQuarantineListView(generics.ListAPIView):
    queryset = ReceiptQuarantine.objects.select_related(
        'receipt_item__product',
        'receipt_item__purchase_receipt',
        'location',
        'resolved_by',
    ).all()
    serializer_class = ReceiptQuarantineSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        PurchaseReceiptAccessPermission,
    ]

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='receipt_item__purchase_receipt__purchase_order__tenant',
        )
        user = self.request.user
        if not user.has_role('admin') and not getattr(user, 'is_superuser', False):
            if InventoryLocation.objects.filter(authorized_users__isnull=False).exists():
                queryset = queryset.filter(location__authorized_users=user)
        return queryset


class ReceiptQuarantineResolutionView(generics.GenericAPIView):
    queryset = ReceiptQuarantine.objects.select_related('receipt_item__product', 'location').all()
    serializer_class = ReceiptQuarantineSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        IsAdminUser,
    ]

    @transaction.atomic
    def post(self, request, pk, action, *args, **kwargs):
        quarantine = tenant_scoped_queryset(
            ReceiptQuarantine.objects.select_for_update().select_related(
                'receipt_item__product',
                'location',
            ),
            request.user,
            tenant_field='receipt_item__purchase_receipt__purchase_order__tenant',
        ).filter(pk=pk).first()
        if quarantine is None:
            return Response({'detail': 'Dossier de quarantaine introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        if action not in {'release', 'write-off'}:
            return Response({'detail': 'Action de quarantaine inconnue.'}, status=status.HTTP_404_NOT_FOUND)
        reason = str(request.data.get('reason', '')).strip()
        if not reason:
            return Response({'reason': 'Un motif est obligatoire.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            quantity = int(request.data.get('quantity', quarantine.quantity_remaining))
        except (TypeError, ValueError):
            return Response({'quantity': 'La quantité doit être un nombre entier.'}, status=status.HTTP_400_BAD_REQUEST)
        if quantity <= 0 or quantity > quarantine.quantity_remaining:
            return Response(
                {'quantity': 'La quantité doit être positive et ne pas dépasser le reliquat en quarantaine.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == 'release':
            product = Product.objects.select_for_update().get(
                pk=quarantine.receipt_item.product_id,
            )
            stock, _ = StockItem.objects.select_for_update().get_or_create(
                product=product,
                location=quarantine.location,
            )
            stock.quantity += quantity
            stock.save(update_fields=['quantity', 'updated_at'])
            product.quantity = (product.quantity or 0) + quantity
            product.save(update_fields=['quantity', 'updated_at'])
            record_cost_layer(
                product=product,
                location=quarantine.location,
                quantity=quantity,
                unit_cost=quarantine.unit_cost,
                source='receipt',
                reference=f'{quarantine.receipt_item.purchase_receipt.reference}-Q{quarantine.pk}',
            )
            StockMovement.objects.create(
                product=product,
                location=quarantine.location,
                movement_type='in',
                quantity=quantity,
                reference=f'{quarantine.receipt_item.purchase_receipt.reference}-Q{quarantine.pk}',
                notes=f'Libération de quarantaine: {reason}',
                created_by=request.user,
            )
            quarantine.quantity_remaining -= quantity
            quarantine.status = 'released' if quarantine.quantity_remaining == 0 else 'partially_released'
        else:
            quarantine.quantity_remaining -= quantity
            quarantine.status = 'written_off' if quarantine.quantity_remaining == 0 else 'quarantined'
            StockMovement.objects.create(
                product=quarantine.receipt_item.product,
                location=quarantine.location,
                movement_type='quarantine_out',
                quantity=quantity,
                reference=f'{quarantine.receipt_item.purchase_receipt.reference}-Q{quarantine.pk}',
                notes=f'Retrait de quarantaine: {reason}',
                created_by=request.user,
            )

        quarantine.resolution_reason = reason
        quarantine.resolved_by = request.user
        quarantine.resolved_at = timezone.now()
        quarantine.save(update_fields=[
            'quantity_remaining', 'status', 'resolution_reason',
            'resolved_by', 'resolved_at', 'updated_at',
        ])
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='ReceiptQuarantine',
            record_id=quarantine.id,
            details=f'{action} de {quantity} unité(s): {reason}',
        )
        return Response(self.get_serializer(quarantine).data, status=status.HTTP_200_OK)
