from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorefrontStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_STOREFRONT_ROOT, base_url=None)


private_storefront_storage = PrivateStorefrontStorage()


def storefront_logo_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f'{instance.tenant.slug}/logo/{uuid4().hex}{extension}'


def storefront_cover_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f'{instance.tenant.slug}/cover/{uuid4().hex}{extension}'
