from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateInvoiceStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_INVOICE_ROOT, base_url=None)


private_invoice_storage = PrivateInvoiceStorage()


def invoice_branding_asset_path(instance, filename):
    tenant_id = instance.tenant_id or 'legacy'
    extension = Path(filename).suffix.lower()
    return f'tenants/{tenant_id}/invoice-branding/{uuid4().hex}{extension}'