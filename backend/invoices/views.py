import hashlib
import mimetypes
from io import BytesIO
from urllib.parse import urlsplit

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.http import HttpResponse
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.models import AuditLog, Company
from core.tenancy import tenant_for_user, tenant_scoped_queryset
from sales.models import Invoice, InvoiceDocumentAttempt
from .branding import get_tenant_invoice_branding
from .models import InvoiceBranding
from users.permissions import (
    IsTenantAssignedUser,
    SensitiveMutationPermission,
    role_permission,
)

from .rendering import build_invoice_snapshot, render_invoice_pdf
from .serializers import InvoiceBrandingSerializer, InvoiceSerializer, invoice_verification_url
from .signing import InvoiceSigningError, sign_and_verify_pdf, verify_signed_pdf


def verification_payload(invoice):
    cancelled = invoice.sale.status == 'cancelled' or invoice.status == 'cancelled'
    signature_valid = False
    if not cancelled and invoice.document_status == 'signed' and invoice.signed_pdf:
        try:
            with invoice.signed_pdf.open('rb') as signed_file:
                signed_bytes = signed_file.read()
            signature_valid = (
                hashlib.sha256(signed_bytes).hexdigest() == invoice.document_sha256
                and verify_signed_pdf(signed_bytes)
            )
        except OSError:
            signature_valid = False
    return {
        'valid': signature_valid and not cancelled,
        'signature_valid': signature_valid,
        'signature_status': (
            'cancelled' if cancelled else
            'valid' if signature_valid else
            'failed' if invoice.document_status == 'signature_failed' else
            'unsigned'
        ),
        'status': 'cancelled' if cancelled else 'validated' if signature_valid else 'unsigned',
        'invoice_number': invoice.invoice_number,
        'issue_date': invoice.issue_date,
        'company_name': invoice.company_name,
        'total_amount': invoice.total_amount,
        'currency': 'GNF',
        'verification_url': invoice_verification_url(invoice),
        'kind': 'invoice',
        'items_count': invoice.sale.items.count(),
        'validation_reference': invoice.validation_reference,
        'document_pages': invoice.document_pages,
    }


class InvoiceListView(generics.ListAPIView):
    queryset = Invoice.objects.select_related('sale__customer').all()
    serializer_class = InvoiceSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='sale__tenant',
        )


class InvoiceBrandingView(generics.RetrieveUpdateAPIView):
    serializer_class = InvoiceBrandingSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
        SensitiveMutationPermission,
    ]

    def get_object(self):
        tenant = tenant_for_user(self.request.user)
        if tenant is None:
            raise PermissionDenied('Votre compte doit être rattaché à un espace d’entreprise.')

        branding = get_tenant_invoice_branding(tenant)
        if branding:
            return branding

        company = Company.objects.filter(tenant=tenant).first()
        defaults = {
            'company_name': company.name if company else tenant.name,
            'address': company.address if company else '',
            'phone_numbers': [company.phone] if company and company.phone else [],
            'email': company.email if company else '',
            'email_addresses': [company.email] if company and company.email else [],
        }
        if self.request.method in permissions.SAFE_METHODS:
            return InvoiceBranding(tenant=tenant, **defaults)

        branding, _ = InvoiceBranding.objects.get_or_create(
            tenant=tenant,
            defaults=defaults,
        )
        return branding

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        branding = serializer.save(updated_by=request.user)
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='InvoiceBranding',
            record_id=branding.pk,
            details=(
                f'Identité des factures mise à jour pour {branding.tenant.name}: '
                f'{branding.company_name}'
            ),
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class InvoiceBrandingAssetView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
        SensitiveMutationPermission,
    ]

    def get(self, request, asset, *args, **kwargs):
        field_name = {
            'logo': 'logo_image',
            'automotive': 'automotive_image',
            'watermark': 'watermark_image',
            'stamp': 'stamp_image',
            'signature': 'seller_signature_image',
        }.get(asset)
        if field_name is None:
            return Response({'detail': 'Image de configuration inconnue.'}, status=404)
        tenant = tenant_for_user(request.user)
        branding = get_tenant_invoice_branding(tenant)
        image = getattr(branding, field_name, None) if branding else None
        if not image:
            return Response({'detail': 'Image non configurée.'}, status=404)
        try:
            image.open('rb')
        except OSError:
            return Response({'detail': 'Image configurée indisponible.'}, status=404)
        content_type = mimetypes.guess_type(image.name)[0] or 'application/octet-stream'
        response = FileResponse(image, content_type=content_type)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    def delete(self, request, asset, *args, **kwargs):
        field_name = {
            'logo': 'logo_image',
            'automotive': 'automotive_image',
            'watermark': 'watermark_image',
            'stamp': 'stamp_image',
            'signature': 'seller_signature_image',
        }.get(asset)
        if field_name is None:
            return Response({'detail': 'Image de configuration inconnue.'}, status=404)
        tenant = tenant_for_user(request.user)
        branding = get_tenant_invoice_branding(tenant)
        if branding is None:
            return Response(status=204)
        getattr(branding, field_name).delete(save=False)
        branding.updated_by = request.user
        branding.save(update_fields=[field_name, 'updated_by', 'updated_at'])
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='InvoiceBranding',
            record_id=branding.pk,
            details=f'Image de facture supprimée: {asset}',
        )
        return Response(status=204)


class InvoiceDetailView(generics.RetrieveAPIView):
    queryset = Invoice.objects.select_related('sale__customer').all()
    serializer_class = InvoiceSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='sale__tenant',
        )


class InvoiceQrView(generics.GenericAPIView):
    queryset = Invoice.objects.select_related('sale__customer').all()
    serializer_class = InvoiceSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='sale__tenant',
        )

    def get(self, request, *args, **kwargs):
        invoice = self.get_object()
        return Response({
            'type': 'invoice',
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'qr_code': invoice.qr_code,
            'verification_url': invoice_verification_url(invoice),
        }, status=status.HTTP_200_OK)


class InvoiceQrImageView(generics.GenericAPIView):
    queryset = Invoice.objects.select_related('sale__customer').all()
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='sale__tenant',
        )

    def get(self, request, *args, **kwargs):
        invoice = self.get_object()
        qr = qrcode.make(invoice_verification_url(invoice))
        buffer = BytesIO()
        qr.save(buffer, format='PNG')
        return HttpResponse(buffer.getvalue(), content_type='image/png')


class InvoiceVerifyView(generics.GenericAPIView):
    queryset = Invoice.objects.select_related('sale__customer').all()
    permission_classes = [permissions.AllowAny]

    def get(self, request, token, *args, **kwargs):
        invoice = self.get_queryset().filter(verification_token=token).first()
        if invoice is None:
            return Response({'detail': 'Facture introuvable ou jeton invalide.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(verification_payload(invoice), status=status.HTTP_200_OK)


class InvoicePdfView(generics.GenericAPIView):
    queryset = Invoice.objects.select_related('sale__customer').all()
    serializer_class = InvoiceSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='sale__tenant',
        )

    def get(self, request, *args, **kwargs):
        invoice = self.get_object()
        if invoice.document_status != 'signed' or not invoice.signed_pdf:
            return Response(
                {'detail': 'Le PDF signé et vérifié n’est pas disponible.'},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            with invoice.signed_pdf.open('rb') as signed_file:
                signed_bytes = signed_file.read()
        except OSError:
            return Response(
                {'detail': 'Le document signé est introuvable.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if (
            hashlib.sha256(signed_bytes).hexdigest() != invoice.document_sha256
            or not verify_signed_pdf(signed_bytes)
        ):
            invoice.document_status = 'signature_failed'
            invoice.signature_error = 'Le contrôle du PDF stocké a échoué.'
            invoice.save(update_fields=['document_status', 'signature_error'])
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='Invoice',
                record_id=invoice.pk,
                details='Téléchargement bloqué : intégrité ou signature invalide.',
            )
            return Response(
                {'detail': 'Le contrôle cryptographique du document a échoué.'},
                status=status.HTTP_409_CONFLICT,
            )
        response = HttpResponse(signed_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        response['X-Document-SHA256'] = invoice.document_sha256
        return response


class InvoiceIssueView(generics.GenericAPIView):
    queryset = Invoice.objects.select_related('sale__customer', 'sale__seller').all()
    serializer_class = InvoiceSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsTenantAssignedUser,
        role_permission('sales'),
    ]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset().select_related(None),
            self.request.user,
            tenant_field='sale__tenant',
        )

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            invoice = self.get_queryset().select_for_update().filter(
                pk=kwargs['pk'],
            ).first()
            if invoice is None:
                return Response({'detail': 'Facture introuvable.'}, status=404)
            if invoice.document_status == 'signed' and invoice.signed_pdf:
                return Response({
                    'document_status': 'signed',
                    'invoice_number': invoice.invoice_number,
                    'document_sha256': invoice.document_sha256,
                    'document_pages': invoice.document_pages,
                })
            if invoice.sale.status == 'cancelled' or invoice.status == 'cancelled':
                return Response({'detail': 'Une facture annulée ne peut pas être émise.'}, status=409)
            if invoice.document_status == 'rendering':
                return Response({'detail': 'Une émission est déjà en cours.'}, status=409)
            if invoice.document_status == 'signature_failed' and request.data.get('retry') is not True:
                return Response(
                    {'detail': 'Une reprise explicite est nécessaire après l’échec de signature.'},
                    status=409,
                )
            if not invoice.document_snapshot:
                invoice.document_snapshot = build_invoice_snapshot(invoice)
            snapshot = invoice.document_snapshot
            invoice.document_status = 'rendering'
            invoice.signature_error = ''
            invoice.save(update_fields=['document_snapshot', 'document_status', 'signature_error'])
            attempt = InvoiceDocumentAttempt.objects.create(
                invoice=invoice,
                initiated_by=request.user,
            )

        try:
            if not settings.DEBUG and urlsplit(snapshot['verification_url']).scheme != 'https':
                raise InvoiceSigningError('L’URL de vérification doit utiliser HTTPS en production.')
            unsigned_pdf, page_count = render_invoice_pdf(snapshot)
            signed_pdf = sign_and_verify_pdf(unsigned_pdf)
            digest = hashlib.sha256(signed_pdf).hexdigest()
        except Exception as exc:
            error = str(exc) or 'Échec de génération ou de signature du document.'
            with transaction.atomic():
                invoice = self.get_queryset().select_for_update().filter(
                    pk=kwargs['pk'],
                ).first()
                if invoice is None:
                    return Response({'detail': 'Facture introuvable.'}, status=404)
                invoice.document_status = 'signature_failed'
                invoice.signature_error = error[:2000]
                invoice.save(update_fields=['document_status', 'signature_error'])
                attempt.status = 'failed'
                attempt.error = error[:2000]
                attempt.finished_at = timezone.now()
                attempt.save(update_fields=['status', 'error', 'finished_at'])
                AuditLog.objects.create(
                    user=request.user,
                    action='update',
                    model_name='Invoice',
                    record_id=invoice.pk,
                    details=f'Émission/signature échouée: {error[:500]}',
                )
            return Response(
                {
                    'detail': 'Émission impossible : le certificat ou la vérification de signature a échoué.',
                    'document_status': 'signature_failed',
                    'retry_required': True,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with transaction.atomic():
            invoice = self.get_queryset().select_for_update().filter(
                pk=kwargs['pk'],
            ).first()
            if invoice is None:
                return Response({'detail': 'Facture introuvable.'}, status=404)
            invoice.signed_pdf.save(
                f'{invoice.invoice_number}-v{invoice.document_version}.pdf',
                ContentFile(signed_pdf),
                save=False,
            )
            invoice.document_status = 'signed'
            invoice.document_sha256 = digest
            invoice.document_pages = page_count
            invoice.signed_at = timezone.now()
            invoice.signature_error = ''
            invoice.save(update_fields=[
                'signed_pdf', 'document_status', 'document_sha256',
                'document_pages', 'signed_at', 'signature_error',
            ])
            attempt.status = 'signed'
            attempt.document_sha256 = digest
            attempt.document_pages = page_count
            attempt.finished_at = timezone.now()
            attempt.save(update_fields=[
                'status', 'document_sha256', 'document_pages', 'finished_at',
            ])
            AuditLog.objects.create(
                user=request.user,
                action='create',
                model_name='InvoiceDocumentAttempt',
                record_id=attempt.pk,
                details=(
                    f'Facture {invoice.invoice_number} signée et vérifiée; '
                    f'pages={page_count}; sha256={digest}.'
                ),
            )
        return Response({
            'document_status': 'signed',
            'invoice_number': invoice.invoice_number,
            'document_sha256': digest,
            'document_pages': page_count,
        }, status=status.HTTP_201_CREATED)
