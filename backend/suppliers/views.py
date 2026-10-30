import csv
import hashlib
import io
import mimetypes
import os
import re
import zipfile
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from openpyxl.utils.exceptions import InvalidFileException
from pypdf.errors import PdfReadError
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from xlrd.biffh import XLRDError

from core.models import AuditLog
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from products.models import Product
from purchases.models import PurchaseOrder, PurchaseOrderItem
from users.permissions import (
    IsTenantAssignedUser,
    SupplierWorkflowPermission,
    role_permission,
)

from .models import ExchangeRate, Supplier, SupplierImport, SupplierImportRow
from .serializers import (
    ExchangeRateSerializer,
    SupplierImportRequestSerializer,
    SupplierImportSerializer,
    SupplierSerializer,
)

FIELD_ALIASES = {
    'reference': [
        'reference', 'supplier_reference', 'supplierreference', 'product_code', 'productcode', 'code', 'sku', 'ref',
        'article', 'article_code', 'articlecode', 'reference_fournisseur', 'referencefournisseur'
    ],
    'name': [
        'name', 'product', 'description', 'designation', 'product_name', 'productname', 'item_name', 'itemname', 'title',
        'produit', 'designation_produit', 'description_produit'
    ],
    'quantity': ['quantity', 'qty', 'qte', 'quantite', 'count'],
    'unit_price': ['unit_price', 'unitprice', 'price', 'prix', 'prix_unitaire', 'unitcost', 'unit_cost'],
    'currency': ['currency', 'devise', 'monnaie'],
    'brand': ['brand', 'marque'],
    'image': ['image', 'image_url', 'imageurl', 'photo', 'picture'],
}


def _normalize_header(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def _scalar_from_row(row, aliases):
    for alias in aliases:
        normalized_alias = _normalize_header(alias)
        for key, value in row.items():
            if _normalize_header(key) == normalized_alias:
                if value is None:
                    return ''
                return str(value).strip()
    return ''


def _parse_quantity(value):
    if value in (None, ''):
        return None
    try:
        quantity = Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not quantity.is_finite() or quantity <= 0 or quantity != quantity.to_integral_value():
        return None
    return int(quantity)


def _parse_price(value):
    if value in (None, ''):
        return None
    cleaned = re.sub(r'\s|€|\$|GNF', '', str(value).strip(), flags=re.IGNORECASE)
    if ',' in cleaned and '.' in cleaned:
        decimal_separator = ',' if cleaned.rfind(',') > cleaned.rfind('.') else '.'
        grouping_separator = '.' if decimal_separator == ',' else ','
        cleaned = cleaned.replace(grouping_separator, '').replace(decimal_separator, '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    try:
        price = Decimal(cleaned)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not price.is_finite() or price <= 0:
        return None
    return price


def _row_validation_errors(quantity, unit_price, currency):
    errors = []
    if _parse_quantity(quantity) is None:
        errors.append('La quantité doit être un entier positif.')
    if _parse_price(unit_price) is None:
        errors.append('Le prix unitaire doit être strictement positif.')
    if not re.fullmatch(r'[A-Z]{3}', str(currency or '').upper()):
        errors.append('La devise doit être indiquée avec un code ISO de trois lettres.')
    return errors


def _extract_pdf_rows(file_bytes):
    from pypdf import PdfReader

    text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(file_bytes)).pages)
    if not text.strip():
        raise ValueError(
            'Aucun texte exploitable dans le PDF. Les PDF scannés et images nécessitent une saisie manuelle.'
        )

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    separator = '\t' if any('\t' in line for line in lines) else r'\s{2,}'
    split_line = (lambda line: [part.strip() for part in line.split('\t')]) if separator == '\t' else (
        lambda line: [part.strip() for part in re.split(separator, line)]
    )
    header_index = next(
        (
            index for index, line in enumerate(lines)
            if any(_normalize_header(alias) in {_normalize_header(cell) for cell in split_line(line)}
                   for aliases in FIELD_ALIASES.values() for alias in aliases)
        ),
        None,
    )
    if header_index is None:
        raise ValueError('Le tableau du PDF n’a pas pu être identifié. Vérifiez le document ou saisissez les lignes manuellement.')
    headers = split_line(lines[header_index])
    return [
        dict(zip(headers, split_line(line)))
        for line in lines[header_index + 1:]
        if len(split_line(line)) == len(headers)
    ]


def _extract_rows_from_uploaded_file(file_obj, product_queryset):
    file_obj.seek(0)
    file_name = getattr(file_obj, 'name', '').lower()
    file_bytes = file_obj.read()

    try:
        if file_name.endswith('.csv'):
            content = file_bytes.decode('utf-8-sig')
            rows = list(csv.DictReader(io.StringIO(content)))
        elif file_name.endswith('.pdf'):
            rows = _extract_pdf_rows(file_bytes)
        else:
            engine = 'xlrd' if file_name.endswith('.xls') else 'openpyxl'
            dataframe = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
            rows = dataframe.where(pd.notna(dataframe), None).to_dict(orient='records')
    except (
        UnicodeDecodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        ValueError,
        OSError,
        zipfile.BadZipFile,
        InvalidFileException,
        PdfReadError,
        XLRDError,
        ImportError,
    ) as error:
        raise ValueError(f'Le fichier ne peut pas être analysé : {error}') from error

    parsed_rows = []
    for row in rows:
        if not row:
            continue
        reference = _scalar_from_row(row, FIELD_ALIASES['reference']) or _scalar_from_row(row, ['reference_fournisseur'])
        name = _scalar_from_row(row, FIELD_ALIASES['name']) or _scalar_from_row(row, ['produit', 'description'])
        raw_quantity = _scalar_from_row(row, FIELD_ALIASES['quantity'])
        quantity = _parse_quantity(raw_quantity)
        unit_price = _parse_price(_scalar_from_row(row, FIELD_ALIASES['unit_price']))
        currency = _scalar_from_row(row, FIELD_ALIASES['currency']).upper()

        if not reference and not name:
            continue

        validation_errors = _row_validation_errors(quantity, unit_price, currency)

        matched_product = None
        if reference:
            matched_product = product_queryset.filter(sku__iexact=reference).first()
        if matched_product is None and name:
            matched_product = product_queryset.filter(name__iexact=name).first()

        parsed_rows.append({
            'reference': reference,
            'name': name,
            'quantity': quantity or 0,
            'unit_price': unit_price or Decimal(0),
            'currency': currency,
            'matched_product': matched_product.name if matched_product else '',
            'product': matched_product,
            'validation_errors': validation_errors,
            'notes': 'Produit existant reconnu' if matched_product else 'Produit à rapprocher manuellement',
        })

    return parsed_rows


class SupplierListCreateView(generics.ListCreateAPIView):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SupplierWorkflowPermission,
    ]
    pagination_class = None

    def get_queryset(self):
        queryset = tenant_scoped_queryset(
            Supplier.objects.all(),
            self.request.user,
        )
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(contact_name__icontains=search) |
                Q(phone__icontains=search) |
                Q(company_name__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for_user(self.request.user))


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SupplierWorkflowPermission,
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            Supplier.objects.all(),
            self.request.user,
        )


class ExchangeRateListCreateView(generics.ListCreateAPIView):
    queryset = ExchangeRate.objects.select_related('created_by').all()
    serializer_class = ExchangeRateSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        source_currency = self.request.query_params.get('source_currency')
        target_currency = self.request.query_params.get('target_currency')
        if source_currency:
            queryset = queryset.filter(source_currency=source_currency.strip().upper())
        if target_currency:
            queryset = queryset.filter(target_currency=target_currency.strip().upper())
        return queryset

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            permission_classes = [permissions.IsAuthenticated, role_permission('purchases')]
        else:
            permission_classes = [permissions.IsAuthenticated, role_permission('suppliers')]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SupplierImportView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SupplierWorkflowPermission,
    ]

    @extend_schema(request=SupplierImportRequestSerializer, responses={201: SupplierImportSerializer})
    def post(self, request, *args, **kwargs):
        supplier_id = request.data.get('supplier') or request.POST.get('supplier')
        file_obj = request.FILES.get('file')

        if not supplier_id:
            return Response({'supplier': ['Le fournisseur est requis.']}, status=status.HTTP_400_BAD_REQUEST)
        if not file_obj:
            return Response({'file': ['Le fichier fournisseur est requis.']}, status=status.HTTP_400_BAD_REQUEST)

        supplier = tenant_scoped_queryset(
            Supplier.objects.all(),
            request.user,
        ).filter(pk=supplier_id).first()
        if supplier is None:
            return Response({'supplier': ['Fournisseur introuvable.']}, status=status.HTTP_404_NOT_FOUND)

        allowed_extensions = ('.csv', '.xlsx', '.xls', '.pdf')
        file_name = getattr(file_obj, 'name', '').lower()
        if not file_name.endswith(allowed_extensions):
            return Response({'file': ['Seuls les fichiers CSV, XLSX, XLS et PDF textuels sont acceptés.']}, status=status.HTTP_400_BAD_REQUEST)
        if file_obj.size > 10 * 1024 * 1024:
            return Response({'file': ['La taille maximale du fichier est de 10 Mo.']}, status=status.HTTP_400_BAD_REQUEST)

        file_obj.seek(0)
        file_bytes = file_obj.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        file_obj.seek(0)
        try:
            rows = _extract_rows_from_uploaded_file(
                file_obj,
                tenant_scoped_queryset(Product.objects.all(), request.user),
            )
        except (ValueError, OSError) as error:
            return Response({'file': [str(error)]}, status=status.HTTP_400_BAD_REQUEST)
        if not rows:
            return Response(
                {
                    'file': [
                        'Aucune ligne fournisseur exploitable n’a été détectée. '
                        'Vérifiez les colonnes ou choisissez le flux d’import adapté.'
                    ],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        file_obj.seek(0)

        import_record = SupplierImport.objects.create(
            supplier=supplier,
            file_name=getattr(file_obj, 'name', 'fichier.csv'),
            source_file=file_obj,
            file_sha256=file_hash,
            uploaded_by=request.user,
            possible_duplicate_of=SupplierImport.objects.filter(
                supplier=supplier,
                file_sha256=file_hash,
            ).order_by('created_at').first(),
            status='parsed',
            parsed_rows=len(rows),
        )

        for row in rows:
            SupplierImportRow.objects.create(supplier_import=import_record, **row)

        AuditLog.objects.create(
            user=request.user,
            action='create',
            model_name='SupplierImport',
            record_id=import_record.id,
            details=f'Document fournisseur importé: {import_record.file_name} ({file_hash})',
        )
        payload = SupplierImportSerializer(import_record).data
        return Response(payload, status=status.HTTP_201_CREATED)


class SupplierImportDocumentView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SupplierWorkflowPermission,
    ]

    def get(self, request, import_id, *args, **kwargs):
        import_record = get_object_or_404(
            tenant_scoped_queryset(
                SupplierImport.objects.all(),
                request.user,
                tenant_field='supplier__tenant',
            ),
            pk=import_id,
        )
        if not import_record.source_file:
            return Response({'detail': 'Le document original est introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(
            import_record.source_file.open('rb'),
            as_attachment=True,
            filename=os.path.basename(import_record.file_name),
            content_type=mimetypes.guess_type(import_record.file_name)[0] or 'application/octet-stream',
        )
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class SupplierImportConfirmView(generics.GenericAPIView):
    queryset = SupplierImport.objects.prefetch_related('rows').all()
    serializer_class = SupplierImportSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SupplierWorkflowPermission,
    ]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        import_record = get_object_or_404(
            tenant_scoped_queryset(
                SupplierImport.objects.select_for_update().prefetch_related('rows'),
                request.user,
                tenant_field='supplier__tenant',
            ),
            pk=kwargs['pk'],
        )
        if import_record.status != 'parsed':
            return Response(
                {'detail': 'Cet import a déjà été traité.'},
                status=status.HTTP_409_CONFLICT,
            )

        rows = list(import_record.rows.select_related('product').all())
        if not rows:
            return Response({'detail': 'Aucune ligne exploitable dans cet import.'}, status=status.HTTP_400_BAD_REQUEST)
        invalid_rows = [
            {'row': row.id, 'errors': row.validation_errors or ['Rapprochez cette ligne avec un produit existant.']}
            for row in rows
            if row.validation_errors or row.product_id is None
        ]
        if invalid_rows:
            return Response(
                {'detail': 'Corrigez les lignes signalées avant de créer la commande.', 'rows': invalid_rows},
                status=status.HTTP_400_BAD_REQUEST,
            )
        currencies = {row.currency for row in rows}
        if len(currencies) != 1:
            return Response({'detail': 'Un import ne peut pas mélanger plusieurs devises.'}, status=status.HTTP_400_BAD_REQUEST)
        currency = currencies.pop()
        exchange_rate = Decimal(1)
        exchange_rate_date = None
        if currency != 'GNF':
            rate = ExchangeRate.objects.filter(
                source_currency=currency,
                target_currency='GNF',
                effective_date__lte=timezone.localdate(),
            ).order_by('-effective_date', '-created_at').first()
            if rate is None:
                return Response(
                    {'detail': f'Aucun taux de change confirmé n’est enregistré pour {currency} vers GNF.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            exchange_rate = rate.rate
            exchange_rate_date = rate.effective_date

        order_reference = f"PO-{import_record.supplier.name[:3].upper()}-{import_record.pk:04d}"
        purchase_order = PurchaseOrder.objects.create(
            tenant=tenant_for_user(request.user),
            supplier=import_record.supplier,
            reference=order_reference,
            status='draft',
            currency=currency,
            exchange_rate=exchange_rate,
            exchange_rate_date=exchange_rate_date,
            reference_exchange_rate=exchange_rate if currency != 'GNF' else None,
            exchange_rate_applied_by=request.user if currency != 'GNF' else None,
            exchange_rate_applied_at=timezone.now() if currency != 'GNF' else None,
            created_by=request.user,
            notes=f"Commande créée depuis l’import fournisseur {import_record.file_name}",
        )

        for row in rows:
            PurchaseOrderItem.objects.create(
                purchase_order=purchase_order,
                product=row.product,
                quantity=row.quantity,
                unit_cost=row.unit_price,
            )

        import_record.status = 'validated'
        import_record.purchase_order = purchase_order
        import_record.save(update_fields=['status', 'purchase_order'])
        AuditLog.objects.create(
            user=request.user,
            action='create',
            model_name='PurchaseOrder',
            record_id=purchase_order.id,
            details=f'Brouillon {purchase_order.reference} créé depuis l’import {import_record.id}; le stock reste inchangé.',
        )

        payload = self.get_serializer(import_record).data
        return Response(payload, status=status.HTTP_200_OK)


class SupplierImportRowCorrectionView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SupplierWorkflowPermission,
    ]

    @transaction.atomic
    def patch(self, request, import_id, row_id, *args, **kwargs):
        import_record = tenant_scoped_queryset(
            SupplierImport.objects.select_for_update(),
            request.user,
            tenant_field='supplier__tenant',
        ).filter(pk=import_id, status='parsed').first()
        if import_record is None:
            return Response({'detail': 'Import introuvable ou déjà confirmé.'}, status=status.HTTP_404_NOT_FOUND)
        row = SupplierImportRow.objects.select_for_update().filter(
            pk=row_id,
            supplier_import=import_record,
        ).first()
        if row is None:
            return Response({'detail': 'Ligne d’import introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        quantity = _parse_quantity(request.data.get('quantity', row.quantity))
        unit_price = _parse_price(request.data.get('unit_price', row.unit_price))
        currency = str(request.data.get('currency', row.currency)).strip().upper()
        errors = _row_validation_errors(quantity, unit_price, currency)
        if errors:
            return Response(
                {'detail': 'Corrigez les valeurs de la ligne.', 'errors': errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        row.quantity = quantity
        row.unit_price = unit_price
        row.currency = currency
        row.validation_errors = []
        row.notes = 'Valeurs contrôlées manuellement.'
        row.save(update_fields=['quantity', 'unit_price', 'currency', 'validation_errors', 'notes'])
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='SupplierImportRow',
            record_id=row.id,
            details=f'Valeurs corrigées pour la ligne {row.id} de l’import {import_record.id}.',
        )
        import_record.refresh_from_db()
        return Response(SupplierImportSerializer(import_record).data, status=status.HTTP_200_OK)


class SupplierImportRowMatchView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        SupplierWorkflowPermission,
    ]

    @transaction.atomic
    def post(self, request, import_id, row_id, *args, **kwargs):
        import_record = tenant_scoped_queryset(
            SupplierImport.objects.select_for_update(),
            request.user,
            tenant_field='supplier__tenant',
        ).filter(pk=import_id, status='parsed').first()
        if import_record is None:
            return Response({'detail': 'Import introuvable ou déjà confirmé.'}, status=status.HTTP_404_NOT_FOUND)
        row = SupplierImportRow.objects.select_for_update().filter(
            pk=row_id,
            supplier_import=import_record,
        ).first()
        if row is None:
            return Response({'detail': 'Ligne d’import introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            product = tenant_scoped_queryset(
                Product.objects.all(),
                request.user,
            ).get(pk=request.data.get('product'))
        except (Product.DoesNotExist, TypeError, ValueError):
            return Response({'product': ['Sélectionnez un produit existant.']}, status=status.HTTP_400_BAD_REQUEST)
        row.product = product
        row.matched_product = product.name
        row.notes = f'Rapproché avec le produit existant {product.sku}.'
        row.save(update_fields=['product', 'matched_product', 'notes'])
        import_record.refresh_from_db()
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='SupplierImportRow',
            record_id=row.id,
            details=f'Ligne de l’import {import_record.id} rapprochée avec le produit {product.sku}.',
        )
        return Response(SupplierImportSerializer(import_record).data, status=status.HTTP_200_OK)
