import hashlib
from collections import defaultdict

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AuditLog
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from products.catalog_imports import normalize_header, read_catalog_file
from products.models import Product
from users.permissions import InventoryCountAccessPermission, IsTenantAssignedUser

from .access import accessible_locations
from .models import (
    InventoryCount,
    InventoryCountItem,
    StockFileImport,
    StockItem,
)

FIELD_ALIASES = {
    'reference': {'reference', 'sku', 'référence', 'code produit'},
    'physical_quantity': {
        'physical quantity',
        'physical stock',
        'quantity',
        'quantité physique',
        'stock physique',
        'quantité',
    },
    'location': {'location', 'emplacement', 'entrepôt', 'warehouse', 'boutique'},
}
INITIAL_IMPORT_MARKER = 'NEXORA-STOCK-IMPORT-INITIAL:'


def stock_import_preview(record, user):
    mapped_headers = defaultdict(list)
    for header in record.headers:
        normalized = normalize_header(header)
        for field, aliases in FIELD_ALIASES.items():
            if normalized in {normalize_header(alias) for alias in aliases}:
                mapped_headers[field].append(header)

    required = {'reference', 'physical_quantity', 'location'}
    missing = required - set(mapped_headers)
    if missing:
        raise ValidationError({
            'file': (
                'Le fichier doit contenir les colonnes référence, quantité physique '
                'et emplacement.'
            ),
        })
    if any(len(mapped_headers[field]) != 1 for field in required):
        raise ValidationError({
            'file': 'Le fichier doit avoir une seule colonne pour chaque champ obligatoire.',
        })

    products_by_reference = {
        product.sku.casefold(): product
        for product in tenant_scoped_queryset(
            Product.objects.filter(is_active=True),
            user,
        )
    }
    locations = list(accessible_locations(user).filter(is_active=True))
    locations_by_identifier = defaultdict(list)
    for location in locations:
        locations_by_identifier[location.name.casefold()].append(location)
        locations_by_identifier[location.code.casefold()].append(location)

    pending_initial_pairs = set()
    if record.mode == 'initial':
        pending_counts = InventoryCount.objects.filter(
            status__in=['draft', 'submitted'],
            notes__startswith=INITIAL_IMPORT_MARKER,
        )
        pending_initial_pairs = set(
            InventoryCountItem.objects.filter(
                inventory_count__in=pending_counts,
            ).values_list('inventory_count__location_id', 'product_id')
        )

    seen_pairs = {}
    rows = []
    for line_number, raw_row in enumerate(record.rows, start=2):
        reference = str(raw_row.get(mapped_headers['reference'][0]) or '').strip()
        raw_quantity = str(raw_row.get(mapped_headers['physical_quantity'][0]) or '').strip()
        raw_location = str(raw_row.get(mapped_headers['location'][0]) or '').strip()
        errors = []

        product = products_by_reference.get(reference.casefold())
        if not reference:
            errors.append('Référence manquante.')
        elif product is None:
            errors.append('Référence inconnue dans le catalogue actif de cette entreprise.')

        quantity = None
        if not raw_quantity:
            errors.append('Quantité physique manquante.')
        else:
            try:
                quantity = int(raw_quantity)
                if quantity < 0 or str(quantity) != raw_quantity:
                    raise ValueError
            except ValueError:
                errors.append('La quantité doit être un entier positif ou nul.')
                quantity = None

        location = None
        matches = locations_by_identifier.get(raw_location.casefold(), [])
        unique_locations = {item.pk: item for item in matches}
        if not raw_location:
            errors.append('Emplacement manquant.')
        elif len(unique_locations) == 0:
            errors.append('Emplacement inexistant, inactif ou non autorisé.')
        elif len(unique_locations) > 1:
            errors.append('Emplacement ambigu : utilisez son code unique.')
        else:
            location = next(iter(unique_locations.values()))

        if product is not None and location is not None:
            pair = (location.pk, product.pk)
            previous_line = seen_pairs.get(pair)
            if previous_line is not None:
                errors.append(f'Référence et emplacement en double (ligne {previous_line}).')
            else:
                seen_pairs[pair] = line_number

            current_quantity = StockItem.objects.filter(
                product=product,
                location=location,
            ).values_list('quantity', flat=True).first() or 0
            if record.mode == 'initial':
                if current_quantity > 0:
                    errors.append('Ce produit a déjà du stock dans cet emplacement.')
                if pair in pending_initial_pairs:
                    errors.append('Une initialisation est déjà en attente de validation ici.')

        rows.append({
            'line': line_number,
            'reference': reference,
            'product_name': product.name if product else '',
            'quantity': quantity,
            'location_id': location.pk if location else None,
            'location': location.name if location else raw_location,
            'errors': errors,
        })

    return {
        'id': record.pk,
        'mode': record.mode,
        'source_name': record.source_name,
        'reason': record.reason,
        'status': record.status,
        'rows': rows,
        'total_rows': len(rows),
        'valid_rows': sum(not row['errors'] for row in rows),
        'error_rows': sum(bool(row['errors']) for row in rows),
    }


class StockFileImportTemplateView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        InventoryCountAccessPermission,
    ]

    def get(self, request):
        response = HttpResponse(
            'reference,physical_quantity,location\r\n',
            content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = 'attachment; filename="modele-stock-djibexa.csv"'
        return response


class StockFileImportPreviewView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        InventoryCountAccessPermission,
    ]

    def post(self, request):
        mode = request.data.get('mode')
        if mode not in {'initial', 'inventory'}:
            raise ValidationError({'mode': 'Choisissez le stock initial ou l’inventaire physique.'})
        reason = str(request.data.get('reason') or '').strip()
        if not reason:
            raise ValidationError({'reason': 'Indiquez le motif de l’importation.'})
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            raise ValidationError({'file': 'Sélectionnez un fichier CSV ou Excel .xlsx.'})
        content, headers, rows = read_catalog_file(uploaded_file)
        if not headers or not rows:
            raise ValidationError({'file': 'Le fichier ne contient aucune ligne exploitable.'})

        tenant = tenant_for_user(request.user)
        if tenant is None:
            raise ValidationError({'detail': 'Aucune entreprise n’est associée à cette session.'})
        digest = hashlib.sha256(content).hexdigest()
        record = StockFileImport.objects.filter(
            tenant=tenant,
            mode=mode,
            source_sha256=digest,
        ).first()
        if record:
            if not request.user.has_role('admin') and record.created_by_id != request.user.id:
                raise ValidationError({'file': 'Ce fichier est déjà en cours de traitement.'})
            if record.status != 'preview':
                return Response(
                    {'detail': 'Ce fichier a déjà été soumis comme inventaire.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if record.reason != reason:
                record.reason = reason
                record.save(update_fields=['reason'])
        else:
            try:
                record = StockFileImport.objects.create(
                    tenant=tenant,
                    mode=mode,
                    source_name=uploaded_file.name,
                    source_sha256=digest,
                    headers=headers,
                    rows=rows,
                    reason=reason,
                    created_by=request.user,
                )
            except IntegrityError as exc:
                raise ValidationError({'file': 'Ce fichier a déjà été importé dans ce mode.'}) from exc
        return Response(stock_import_preview(record, request.user), status=status.HTTP_201_CREATED)


class StockFileImportConfirmView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        InventoryCountAccessPermission,
    ]

    @transaction.atomic
    def post(self, request, pk):
        tenant = tenant_for_user(request.user)
        record = StockFileImport.objects.select_for_update().filter(
            pk=pk,
            tenant=tenant,
        ).first()
        if record is None or (
            not request.user.has_role('admin') and record.created_by_id != request.user.id
        ):
            raise NotFound('Import introuvable.')
        if record.status != 'preview':
            return Response(
                {'detail': 'Cet import a déjà été soumis.'},
                status=status.HTTP_409_CONFLICT,
            )

        preview = stock_import_preview(record, request.user)
        if not preview['total_rows'] or preview['error_rows']:
            raise ValidationError({
                'rows': [
                    {'line': row['line'], 'errors': row['errors']}
                    for row in preview['rows']
                    if row['errors']
                ],
            })

        products = {
            product.sku.casefold(): product
            for product in tenant_scoped_queryset(
                Product.objects.filter(is_active=True),
                request.user,
            )
        }
        accessible = {
            location.pk: location
            for location in accessible_locations(request.user).filter(is_active=True)
        }
        location_by_id = {}
        grouped_rows = defaultdict(list)
        for row in preview['rows']:
            product = products[row['reference'].casefold()]
            location = accessible[row['location_id']]
            location_by_id[location.pk] = location
            grouped_rows[location.pk].append((product, row['quantity']))

        now = timezone.now()
        count_ids = []
        for location_id, items in grouped_rows.items():
            marker = (
                f'{INITIAL_IMPORT_MARKER}{record.pk}'
                if record.mode == 'initial'
                else f'NEXORA-STOCK-IMPORT-INVENTORY:{record.pk}'
            )
            count = InventoryCount.objects.create(
                number=f'STF-{record.pk}-{location_id}',
                period_type='journalier',
                location=location_by_id[location_id],
                status='submitted',
                notes=f'{marker} — {record.reason}',
                created_by=request.user,
                submitted_by=request.user,
                submitted_at=now,
            )
            stock_by_product = {
                item.product_id: item.quantity
                for item in StockItem.objects.filter(
                    location_id=location_id,
                    product_id__in=[product.pk for product, _ in items],
                )
            }
            InventoryCountItem.objects.bulk_create([
                InventoryCountItem(
                    inventory_count=count,
                    product=product,
                    theoretical_quantity=stock_by_product.get(product.pk, 0),
                    counted_quantity=quantity,
                )
                for product, quantity in items
            ])
            count_ids.append(count.pk)

        record.status = 'submitted'
        record.count_ids = count_ids
        record.submitted_at = now
        record.summary = {
            'locations': len(count_ids),
            'rows': preview['total_rows'],
            'inventory_counts': count_ids,
        }
        record.save(update_fields=['status', 'count_ids', 'submitted_at', 'summary'])
        AuditLog.objects.create(
            user=request.user,
            action='stock',
            model_name='StockFileImport',
            record_id=record.pk,
            details=(
                f'Import stock {record.mode}: {record.source_name}, '
                f'{preview["total_rows"]} ligne(s), {len(count_ids)} inventaire(s) soumis. '
                'Aucun achat ni réception fournisseur créé.'
            ),
        )
        return Response({
            'id': record.pk,
            'mode': record.mode,
            'summary': record.summary,
        }, status=status.HTTP_200_OK)
