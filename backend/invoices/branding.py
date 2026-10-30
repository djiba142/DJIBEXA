from django.conf import settings

from core.models import Company
from .models import InvoiceBranding


def get_tenant_invoice_branding(tenant):
    if tenant is None:
        return None
    return InvoiceBranding.objects.filter(tenant=tenant).first()


def get_tenant_invoice_company_name(tenant, branding=None, fallback_name=''):
    if tenant is None:
        return fallback_name or settings.INVOICE_COMPANY_NAME

    branding = branding or get_tenant_invoice_branding(tenant)
    if branding and branding.company_name:
        return branding.company_name

    company = Company.objects.filter(tenant=tenant).only('name').first()
    return company.name if company else tenant.name
