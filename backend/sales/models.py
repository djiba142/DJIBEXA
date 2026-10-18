from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid

from invoices.storage import private_invoice_storage

from core.models import Tenant
from customers.models import Customer
from suppliers.models import Supplier
from products.models import Product
from inventory.models import InventoryCostLayer, InventoryLocation
from finance.models import FinancialAccount


class Sale(models.Model):
    PAYMENT_CHOICES = [
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Transfert bancaire'),
        ('credit', 'Crédit'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('paid', 'Payée'),
        ('partial', 'Partielle'),
        ('cancelled', 'Annulée'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales')
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='sales',
        null=True,
        blank=True,
    )
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='sales_created', null=True, blank=True)
    location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT, related_name='sales', null=True, blank=True)
    sale_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_method = models.CharField(max_length=30, choices=PAYMENT_CHOICES, default='cash')
    financial_account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, null=True, blank=True, related_name='sales')
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_external = models.BooleanField(default=False)
    external_supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='external_sales', null=True, blank=True)
    external_reference = models.CharField(max_length=120, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-sale_date']

    def __str__(self):
        return f'Vente {self.id} - {self.customer.full_name}'


def generate_customer_order_reference():
    return f'CMD-{uuid.uuid4().hex[:12].upper()}'


class CustomerOrder(models.Model):
    STATUS_CHOICES = [
        ('quote', 'Devis'),
        ('confirmed', 'Confirmée et réservée'),
        ('delivered', 'Livrée'),
        ('cancelled', 'Annulée'),
    ]

    reference = models.CharField(
        max_length=16,
        unique=True,
        default=generate_customer_order_reference,
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='customer_orders',
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders')
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='customer_orders',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_orders_created',
    )
    sale = models.OneToOneField(
        Sale,
        on_delete=models.PROTECT,
        related_name='customer_order',
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='quote')
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.customer.full_name}'


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='sale_items',
        null=True,
        blank=True,
    )
    item_name = models.CharField(max_length=220, blank=True, default='')
    item_reference = models.CharField(max_length=120, blank=True, default='')
    tracked_units = models.ManyToManyField(
        'inventory.StockUnit',
        through='SaleItemTrackedUnit',
        related_name='sale_items',
        blank=True,
    )
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    class Meta:
        unique_together = ('sale', 'product')

    def __str__(self):
        return f'{self.product.name if self.product_id else self.item_name} x {self.quantity}'


class CustomerOrderItem(models.Model):
    order = models.ForeignKey(CustomerOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='customer_order_items',
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'product'],
                name='unique_product_per_customer_order',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='customer_order_item_quantity_positive',
            ),
        ]

    @property
    def total_price(self):
        return self.quantity * self.unit_price


class SaleItemStockOrigin(models.Model):
    SOURCE_CHOICES = [
        ('carton', 'Carton'),
        ('historical_unknown', 'Stock historique non tracé'),
        ('external_supplier', 'Fournisseur externe'),
    ]

    sale_item = models.ForeignKey(
        SaleItem,
        on_delete=models.PROTECT,
        related_name='stock_origins',
    )
    source_type = models.CharField(max_length=24, choices=SOURCE_CHOICES)
    carton = models.ForeignKey(
        'inventory.Carton',
        on_delete=models.PROTECT,
        related_name='sale_origins',
        null=True,
        blank=True,
    )
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='sale_stock_origins',
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='sale_stock_origin_quantity_positive',
            ),
        ]


class SaleItemCostAllocation(models.Model):
    sale_item = models.ForeignKey(
        SaleItem,
        on_delete=models.PROTECT,
        related_name='cost_allocations',
    )
    cost_layer = models.ForeignKey(
        InventoryCostLayer,
        on_delete=models.PROTECT,
        related_name='sale_allocations',
    )
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class SaleReturn(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    reason = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sales_returns_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.PROTECT, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name='returns')
    quantity = models.PositiveIntegerField()
    gross_revenue_total = models.DecimalField(max_digits=14, decimal_places=2)
    revenue_total = models.DecimalField(max_digits=14, decimal_places=2)
    cost_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)


class SaleItemTrackedUnit(models.Model):
    sale_item = models.ForeignKey(
        SaleItem,
        on_delete=models.PROTECT,
        related_name='tracked_unit_allocations',
    )
    stock_unit = models.ForeignKey(
        'inventory.StockUnit',
        on_delete=models.PROTECT,
        related_name='sale_allocations',
    )
    sale_return_item = models.ForeignKey(
        SaleReturnItem,
        on_delete=models.PROTECT,
        related_name='tracked_unit_allocations',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['sale_item', 'stock_unit'],
                name='unique_tracked_unit_per_sale_item',
            ),
        ]


class SaleReturnCostAllocation(models.Model):
    return_item = models.ForeignKey(
        SaleReturnItem,
        on_delete=models.PROTECT,
        related_name='cost_allocations',
    )
    original_allocation = models.ForeignKey(
        SaleItemCostAllocation,
        on_delete=models.PROTECT,
        related_name='return_allocations',
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    quantity_quarantined_remaining = models.PositiveIntegerField(default=0)


class SaleReturnQuarantine(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('resolved', 'Résolue'),
    ]

    return_item = models.OneToOneField(
        SaleReturnItem,
        on_delete=models.PROTECT,
        related_name='quarantine',
    )
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='sales_return_quarantines',
    )
    quantity = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sales_return_quarantines_reviewed',
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Invoice(models.Model):
    DOCUMENT_STATUS_CHOICES = [
        ('unissued', 'Non émise'),
        ('rendering', 'Génération en cours'),
        ('signature_failed', 'Signature échouée'),
        ('signed', 'Signée et vérifiée'),
        ('cancelled', 'Annulée'),
    ]

    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='invoice')
    company_name = models.CharField(max_length=200, default='KOUROUMA AUTO PARTS')
    invoice_number = models.CharField(max_length=80, unique=True, blank=True)
    verification_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    qr_code = models.CharField(max_length=200, blank=True, default='')
    issue_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('validated', 'Validée'), ('cancelled', 'Annulée')], default='validated')
    validation_reference = models.CharField(max_length=120, blank=True, default='')
    stamp_text = models.CharField(max_length=120, default='VALIDEE')
    print_mode = models.CharField(max_length=20, choices=[('a4', 'A4'), ('souche', 'Souche / copie carbone')], default='a4')
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='validated_invoices', null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    document_status = models.CharField(max_length=24, choices=DOCUMENT_STATUS_CHOICES, default='unissued')
    document_version = models.PositiveIntegerField(default=1)
    document_snapshot = models.JSONField(default=dict, blank=True)
    signed_pdf = models.FileField(
        upload_to='invoices/%Y/%m/',
        storage=private_invoice_storage,
        blank=True,
        default='',
    )
    document_sha256 = models.CharField(max_length=64, blank=True, default='')
    document_pages = models.PositiveSmallIntegerField(default=0)
    signed_at = models.DateTimeField(null=True, blank=True)
    signature_error = models.TextField(blank=True, default='')
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return self.invoice_number

    @classmethod
    def generate_invoice_number(cls):
        current_year = timezone.now().year
        prefix = f'FAC-{current_year}-'
        latest = (
            cls.objects.filter(invoice_number__startswith=prefix)
            .order_by('-invoice_number')
            .values_list('invoice_number', flat=True)
            .first()
        )
        next_sequence = 1
        if latest:
            try:
                next_sequence = int(latest.split('-')[-1]) + 1
            except ValueError:
                next_sequence = 1
        return f'{prefix}{next_sequence:06d}'

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

    @property
    def payment_status(self):
        if self.balance_due <= 0:
            return 'paid'
        if self.paid_amount > 0:
            return 'partial'
        return 'unpaid'

    @property
    def validation_stamp(self):
        return 'ANNULEE' if self.status == 'cancelled' else 'VALIDEE'

    def generate_qr_code(self):
        if self.qr_code:
            return self.qr_code
        self.qr_code = f'KAP-FAC-{self.invoice_number}-{str(self.verification_token).replace("-", "")[:8].upper()}'
        return self.qr_code

    def save(self, *args, **kwargs):
        if self.sale_id and self.sale.status == 'cancelled':
            self.status = 'cancelled'
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        if not self.validation_reference:
            self.validation_reference = f'VAL-{self.invoice_number}-{self.verification_token.hex[:8].upper()}'
        if self.status == 'cancelled':
            self.stamp_text = 'ANNULEE'
            self.validated_at = self.validated_at or timezone.now()
        else:
            self.stamp_text = 'VALIDEE'
            if self.validated_by and not self.validated_at:
                self.validated_at = timezone.now()
        if not self.qr_code:
            self.qr_code = self.generate_qr_code()
        super().save(*args, **kwargs)


class InvoiceDocumentAttempt(models.Model):
    STATUS_CHOICES = [
        ('processing', 'En cours'),
        ('signed', 'Signée et vérifiée'),
        ('failed', 'Échec'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='document_attempts')
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_document_attempts',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    error = models.TextField(blank=True, default='')
    document_sha256 = models.CharField(max_length=64, blank=True, default='')
    document_pages = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
