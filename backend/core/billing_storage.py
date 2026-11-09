from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateBillingStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_INVOICE_ROOT, base_url=None)


private_billing_storage = PrivateBillingStorage()


def billing_proof_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f'tenants/{instance.tenant_id}/billing-proofs/{uuid4().hex}{extension}'
