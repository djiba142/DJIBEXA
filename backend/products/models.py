from django.conf import settings
from django.db import models

from core.models import Tenant


class Category(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='product_categories',
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='products',
    )
    sku = models.CharField(max_length=80, unique=True)
    manufacturer_reference = models.CharField(max_length=120, blank=True, default='')
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    brand = models.CharField(max_length=120, blank=True, default='')
    vehicle = models.CharField(max_length=200, blank=True, default='')
    alternative_references = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')
    unit = models.CharField(max_length=60, default='piece')
    package_unit = models.CharField(max_length=40, blank=True, default='')
    units_per_package = models.PositiveIntegerField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='GNF')
    quantity = models.IntegerField(default=0)
    alert_threshold = models.IntegerField(default=0)
    weight = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    volume = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    barcode = models.CharField(max_length=120, blank=True, default='')
    qr_code = models.CharField(max_length=200, blank=True, default='')
    sample_qr_code = models.CharField(max_length=120, blank=True, default='', unique=True)
    image = models.URLField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.sku})'

    def generate_qr_code(self):
        if self.qr_code:
            return self.qr_code

        identifier = self.sku or f'PRD-{self.pk or 0:06d}'
        self.qr_code = f'NEXORA-{identifier}'
        return self.qr_code

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = self.generate_qr_code()
        super().save(*args, **kwargs)
        if not self.sample_qr_code:
            self.sample_qr_code = f'KAP-SMP-{self.pk:06d}'
            super().save(update_fields=['sample_qr_code'])


class ProductCatalogImport(models.Model):
    STATUS_CHOICES = [
        ('preview', 'Aperçu'),
        ('confirmed', 'Confirmé'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='product_catalog_imports',
    )
    source_file = models.FileField(upload_to='product_catalog_imports/')
    source_name = models.CharField(max_length=255)
    source_sha256 = models.CharField(max_length=64)
    headers = models.JSONField(default=list)
    rows = models.JSONField(default=list)
    column_mapping = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preview')
    summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='product_catalog_imports',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.source_name} ({self.status})'
