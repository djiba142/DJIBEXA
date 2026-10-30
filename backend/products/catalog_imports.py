import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AuditLog
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from users.permissions import ProductCatalogPermission

from .models import Category, Product, ProductCatalogImport
from .serializers import ProductSerializer

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 1000
IMPORT_FIELDS = {
    'sku',
    'manufacturer_reference',
    'alternative_references',
    'name',
    'category',
    'brand',
    'vehicle',
    'description',
    'unit',
    'package_unit',
    'units_per_package',
    'purchase_price',
    'cost_price',
    'selling_price',
    'alert_threshold',
}
FIELD_ALIASES = {
    'sku': ('reference', 'reference interne', 'sku', 'code', 'code produit', 'référence interne'),
    'manufacturer_reference': (
        'référence constructeur',
        'reference constructeur',
        'oem',
        'manufacturer reference',
    ),
    'alternative_references': ('références alternatives', 'references alternatives'),
    'name': ('désignation', 'designation', 'nom', 'produit', 'description', 'name'),
    'category': ('catégorie', 'categorie', 'category'),
    'brand': ('marque', 'brand'),
    'vehicle': ('véhicule', 'vehicule', 'vehicle', 'application'),
    'description': ('description détaillée', 'description detaillee'),
    'unit': ('unité', 'unite', 'unit'),
    'package_unit': ('conditionnement', 'package unit'),
    'units_per_package': ('unités par conditionnement', 'unites par conditionnement'),
    'purchase_price': ('prix achat', 'prix d achat', 'purchase price'),
    'cost_price': ('prix de revient', 'cost price'),
    'selling_price': ('prix vente', 'prix de vente', 'selling price'),
    'alert_threshold': ('seuil alerte', 'stock minimum'),
}
REQUIRED_FIELDS = {'sku', 'name'}
DECIMAL_FIELDS = {'purchase_price', 'cost_price', 'selling_price'}
INTEGER_FIELDS = {'units_per_package', 'alert_threshold'}


def normalize_header(value):
    normalized = unicodedata.normalize('NFKD', str(value or '').strip().lower())
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r'[\s_-]+', ' ', normalized)


def suggest_mapping(headers):
    aliases = {
        normalize_header(alias): field
        for field, field_aliases in FIELD_ALIASES.items()
        for alias in field_aliases
    }
    return {
        str(header): aliases[normalize_header(header)]
        for header in headers
        if normalize_header(header) in aliases
    }


def read_catalog_file(uploaded_file):
    uploaded_file.seek(0)
    content = uploaded_file.read()
    filename = uploaded_file.name.lower()
    if len(content) > MAX_FILE_SIZE:
        raise ValidationError({'file': 'Le fichier ne doit pas dépasser 10 Mo.'})

    try:
        if filename.endswith('.csv'):
            text = content.decode('utf-8-sig')
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            headers = list(reader.fieldnames or [])
            rows = list(reader)
        elif filename.endswith('.xlsx'):
            frame = pd.read_excel(io.BytesIO(content), engine='openpyxl', dtype=object)
            headers = [str(column) for column in frame.columns]
            rows = frame.where(pd.notna(frame), None).to_dict(orient='records')
        else:
            raise ValidationError({'file': 'Utilisez un fichier CSV ou Excel .xlsx.'})
    except (UnicodeDecodeError, ValueError, OSError, zipfile.BadZipFile, pd.errors.ParserError) as exc:
        raise ValidationError({'file': f'Le fichier ne peut pas être analysé : {exc}'}) from exc

    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationError({'file': f'Le fichier dépasse la limite de {MAX_IMPORT_ROWS} lignes.'})

    cleaned_rows = []
    for row in rows:
        cleaned = {
            str(key): (None if pd.isna(value) else str(value).strip())
            for key, value in row.items()
            if key is not None
        }
        if any(value not in (None, '') for value in cleaned.values()):
            cleaned_rows.append(cleaned)
    return content, headers, cleaned_rows


def preview_import(import_record, user=None):
    mapping = import_record.column_mapping
    used_fields = [field for field in mapping.values() if field]
    if len(used_fields) != len(set(used_fields)):
        raise ValidationError({'mapping': 'Chaque champ DJIBEXA ne peut être associé qu’à une colonne.'})
    if any(field not in IMPORT_FIELDS for field in used_fields):
        raise ValidationError({'mapping': 'Le fichier contient une correspondance non autorisée.'})

    missing = REQUIRED_FIELDS - set(used_fields)
    if missing:
        raise ValidationError({'mapping': 'Associez une colonne à la référence interne et à la désignation.'})

    existing_products = Product.objects.filter(tenant_id=import_record.tenant_id)
    if user is not None:
        existing_products = tenant_scoped_queryset(Product.objects.all(), user)
    products_by_sku = {
        product.sku.casefold(): product
        for product in existing_products
    }
    seen_skus = set()
    result = []
    for index, raw_row in enumerate(import_record.rows, start=2):
        values = {
            field: raw_row.get(column)
            for column, field in mapping.items()
            if field
        }
        errors = []
        sku = str(values.get('sku') or '').strip()
        name = str(values.get('name') or '').strip()
        action = 'create'
        warnings = []
        if not sku:
            errors.append('Référence interne manquante.')
        elif sku.casefold() in seen_skus:
            errors.append('Référence en double dans ce fichier.')
        else:
            seen_skus.add(sku.casefold())
            action = 'update' if sku.casefold() in products_by_sku else 'create'
        if not name:
            errors.append('Désignation manquante.')

        if (
            user is not None
            and not user.has_role('admin')
            and not getattr(user, 'is_superuser', False)
            and any(values.get(field) not in (None, '') for field in DECIMAL_FIELDS)
        ):
            warnings.append('Les prix ne seront pas modifiés sans la permission administrateur.')

        for field in DECIMAL_FIELDS:
            raw_value = values.get(field)
            if raw_value not in (None, ''):
                try:
                    value = Decimal(str(raw_value).replace(',', '.'))
                    if not value.is_finite() or value < 0:
                        raise InvalidOperation
                    values[field] = str(value)
                except (InvalidOperation, ValueError):
                    errors.append(f'Valeur invalide pour {field}.')
        for field in INTEGER_FIELDS:
            raw_value = values.get(field)
            if raw_value not in (None, ''):
                try:
                    decimal_value = Decimal(str(raw_value).replace(',', '.'))
                    value = int(decimal_value)
                    if decimal_value != value or value < 0:
                        raise ValueError
                    values[field] = value
                except (InvalidOperation, ValueError):
                    errors.append(f'Valeur invalide pour {field}.')

        category_name = str(values.get('category') or '').strip()
        if category_name and not Category.objects.filter(
            tenant_id=import_record.tenant_id,
            name__iexact=category_name,
        ).exists():
            values['category_status'] = 'à créer ou corriger'
        else:
            values['category_status'] = 'existante' if category_name else 'non renseignée'
        result.append({
            'line': index,
            'action': action,
            'values': values,
            'warnings': warnings,
            'unknown_values': {
                column: value
                for column, value in raw_row.items()
                if not mapping.get(column)
            },
            'errors': errors,
        })
    return result


def import_payload(import_record, user=None):
    rows = preview_import(import_record, user)
    fields = sorted(IMPORT_FIELDS)
    return {
        'id': import_record.id,
        'source_name': import_record.source_name,
        'status': import_record.status,
        'headers': import_record.headers,
        'mapping': import_record.column_mapping,
        'fields': fields,
        'unknown_columns': [
            header for header in import_record.headers
            if not import_record.column_mapping.get(header)
        ],
        'rows': rows[:100],
        'total_rows': len(rows),
        'valid_rows': sum(not row['errors'] for row in rows),
        'error_rows': sum(bool(row['errors']) for row in rows),
        'category_review_rows': sum(
            row['values'].get('category_status') == 'à créer ou corriger'
            for row in rows
        ),
    }


def get_import_for_user(pk, user):
    tenant = tenant_for_user(user)
    if tenant is None:
        return None
    queryset = ProductCatalogImport.objects.filter(pk=pk, tenant=tenant)
    if not user.has_role('admin'):
        queryset = queryset.filter(created_by=user)
    return queryset.first()


class ProductCatalogImportTemplateView(APIView):
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]

    def get(self, request):
        response = HttpResponse(
            'reference,manufacturer_reference,alternative_references,name,category,brand,vehicle,description,unit,package_unit,units_per_package,purchase_price,cost_price,selling_price,alert_threshold\r\n',
            content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = 'attachment; filename="modele-produits-djibexa.csv"'
        return response


class ProductCatalogImportPreviewView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            raise ValidationError({'file': 'Sélectionnez un fichier CSV ou Excel.'})
        content, headers, rows = read_catalog_file(uploaded_file)
        if not headers:
            raise ValidationError({'file': 'Le fichier ne contient aucune colonne.'})
        uploaded_file.seek(0)
        record = ProductCatalogImport.objects.create(
            source_file=uploaded_file,
            source_name=uploaded_file.name,
            source_sha256=hashlib.sha256(content).hexdigest(),
            headers=headers,
            rows=rows,
            column_mapping={
                header: suggested
                for header, suggested in (
                    (header, suggest_mapping([header]).get(header, ''))
                    for header in headers
                )
            },
            created_by=request.user,
            tenant=tenant_for_user(request.user),
        )
        return Response(import_payload(record, request.user), status=status.HTTP_201_CREATED)


class ProductCatalogImportMappingView(APIView):
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]

    def post(self, request, pk):
        record = get_import_for_user(pk, request.user)
        if record is None:
            raise ValidationError({'detail': 'Import introuvable.'})
        if record.status != 'preview':
            return Response({'detail': 'Cet import a déjà été confirmé.'}, status=status.HTTP_409_CONFLICT)
        mapping = request.data.get('mapping')
        if not isinstance(mapping, dict):
            raise ValidationError({'mapping': 'Fournissez les correspondances de colonnes.'})
        if set(mapping) - set(record.headers):
            raise ValidationError({'mapping': 'Une colonne correspondante est absente du fichier.'})
        record.column_mapping = mapping
        record.save(update_fields=['column_mapping'])
        return Response(import_payload(record, request.user))


class ProductCatalogImportConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated, ProductCatalogPermission]

    @transaction.atomic
    def post(self, request, pk):
        tenant = tenant_for_user(request.user)
        record = ProductCatalogImport.objects.select_for_update().filter(
            pk=pk,
            tenant=tenant,
        ).first() if tenant is not None else None
        if record and not request.user.has_role('admin') and record.created_by_id != request.user.id:
            record = None
        if record is None:
            raise ValidationError({'detail': 'Import introuvable.'})
        if record.status != 'preview':
            return Response({'detail': 'Cet import a déjà été confirmé.'}, status=status.HTTP_409_CONFLICT)
        create_categories = request.data.get('create_categories') is True
        if create_categories and not (
            request.user.has_role('admin') or getattr(request.user, 'is_superuser', False)
        ):
            raise PermissionDenied('Seul un administrateur peut créer des catégories pendant un import.')

        rows = preview_import(record, request.user)
        if any(row['errors'] for row in rows):
            raise ValidationError({
                'rows': [
                    {'line': row['line'], 'errors': row['errors']}
                    for row in rows
                    if row['errors']
                ],
            })

        created = 0
        updated = 0
        skipped = 0
        error_lines = []
        mapping = record.column_mapping
        for row in rows:
            values = row['values']
            category_name = str(values.pop('category', '') or '').strip()
            category = None
            if category_name:
                category = tenant_scoped_queryset(
                    Category.objects.all(),
                    request.user,
                ).filter(name__iexact=category_name).first()
                if category is None and create_categories:
                    category = Category.objects.create(
                        name=category_name,
                        tenant=record.tenant,
                    )
                elif category is None:
                    error_lines.append({
                        'line': row['line'],
                        'error': f'La catégorie « {category_name} » doit être créée ou corrigée.',
                    })
                    continue
            payload = {
                field: value
                for field, value in values.items()
                if field in IMPORT_FIELDS and value not in (None, '') and field != 'category'
                and (
                    field not in DECIMAL_FIELDS
                    or request.user.has_role('admin')
                    or getattr(request.user, 'is_superuser', False)
                )
            }
            if 'category' in values and values.get('category') not in (None, ''):
                payload['category'] = category.pk if category else None
            existing = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            ).filter(sku__iexact=str(values['sku']).strip()).first()
            if existing is None:
                payload['category'] = category.pk if category else None
                payload['quantity'] = 0
            else:
                payload['sku'] = existing.sku
            serializer = ProductSerializer(
                instance=existing,
                data=payload,
                context={'request': request},
                partial=existing is not None,
            )
            if serializer.is_valid():
                serializer.save(**({'tenant': record.tenant} if existing is None else {}))
                if existing is None:
                    created += 1
                else:
                    updated += 1
            else:
                skipped += 1
                error_lines.append({
                    'line': row['line'],
                    'error': serializer.errors,
                })
        if error_lines:
            raise ValidationError({
                'detail': 'Aucun produit n’a été importé. Corrigez les lignes signalées puis réessayez.',
                'rows': error_lines,
            })

        record.status = 'confirmed'
        record.confirmed_at = timezone.now()
        record.summary = {'created': created, 'updated': updated, 'skipped': skipped, 'errors': 0}
        record.save(update_fields=['status', 'confirmed_at', 'summary'])
        AuditLog.objects.create(
            user=request.user,
            action='create',
            model_name='ProductCatalogImport',
            record_id=record.id,
            details=(
                f'Import catalogue {record.source_name}: {created} créé(s), {updated} mis à jour, '
                'sans modification du stock.'
            ),
        )
        return Response({
            'id': record.id,
            'summary': record.summary,
        }, status=status.HTTP_200_OK)
