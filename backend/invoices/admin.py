from django.contrib import admin

from invoices.models import InvoiceBranding
from sales.models import Invoice, InvoiceDocumentAttempt


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
	list_display = ('invoice_number', 'status', 'document_status', 'document_pages', 'signed_at')
	readonly_fields = (
		'invoice_number', 'verification_token', 'document_snapshot', 'document_sha256',
		'document_pages', 'signed_at', 'signature_error',
	)


@admin.register(InvoiceDocumentAttempt)
class InvoiceDocumentAttemptAdmin(admin.ModelAdmin):
	list_display = ('invoice', 'status', 'initiated_by', 'started_at', 'finished_at')
	readonly_fields = (
		'invoice', 'initiated_by', 'status', 'error', 'document_sha256',
		'document_pages', 'started_at', 'finished_at',
	)


@admin.register(InvoiceBranding)
class InvoiceBrandingAdmin(admin.ModelAdmin):
	list_display = ('tenant', 'company_name', 'email', 'updated_by', 'updated_at')
	readonly_fields = ('updated_by', 'updated_at')
