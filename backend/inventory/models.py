from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import Tenant


def generate_replenishment_reference():
    return f'RAV-{uuid4().hex[:12].upper()}'


class InventoryLocation(models.Model):
    LOCATION_TYPES = [
        ('warehouse', 'Warehouse'),
        ('shop', 'Shop'),
        ('storage', 'Storage'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_locations',
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=80, unique=True)
    location_type = models.CharField(max_length=40, choices=LOCATION_TYPES, default='warehouse')
    address = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    authorized_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='authorized_inventory_locations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class StockItem(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='stock_items')
    location = models.ForeignKey(InventoryLocation, on_delete=models.CASCADE, related_name='stock_items')
    quantity = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'location')
        ordering = ['product__name', 'location__name']

    def __str__(self):
        return f'{self.product.name} @ {self.location.name}: {self.quantity}'

    def add_quantity(self, value):
        self.quantity = max(0, self.quantity + value)
        self.save(update_fields=['quantity', 'updated_at'])

    def remove_quantity(self, value):
        if self.quantity - value < 0:
            raise ValidationError('La quantité en stock ne peut pas devenir négative.')
        self.quantity -= value
        self.save(update_fields=['quantity', 'updated_at'])


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('in', 'Entrée'),
        ('out', 'Sortie'),
        ('adjustment', 'Ajustement'),
        ('quarantine_in', 'Mise en quarantaine'),
        ('quarantine_out', 'Sortie de quarantaine'),
    ]

    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='stock_movements')
    location = models.ForeignKey(InventoryLocation, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField(default=0)
    reference = models.CharField(max_length=120, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_movement_type_display()} - {self.product.name} ({self.quantity})'


class StockTransfer(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('requested', 'Demandé'),
        ('validated', 'Validé'),
        ('shipped', 'Expédié'),
        ('received', 'Reçu'),
        ('cancelled', 'Annulé'),
    ]

    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='stock_transfers')
    from_location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT, related_name='outgoing_transfers')
    to_location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT, related_name='incoming_transfers')
    replenishment_request = models.ForeignKey(
        'StockReplenishmentRequest',
        on_delete=models.SET_NULL,
        related_name='transfers',
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=0)
    quantity_shipped = models.PositiveIntegerField(default=0)
    quantity_received = models.PositiveIntegerField(null=True, blank=True)
    variance_reason = models.TextField(blank=True, default='')
    reference = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='validated')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transfers')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_transfers_approved',
    )
    shipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_transfers_shipped',
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_transfers_received',
    )
    shipped_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.product.name}'

    def clean(self):
        if self.from_location_id == self.to_location_id:
            raise ValidationError('La source et la destination d’un transfert doivent être différentes.')
        if self.quantity <= 0:
            raise ValidationError('La quantité du transfert doit être positive.')
        if self.status in {'requested', 'validated'}:
            source_item = StockItem.objects.filter(
                product=self.product,
                location=self.from_location,
            ).first()
            if source_item and source_item.quantity < self.quantity:
                raise ValidationError(
                    'La quantité demandée dépasse le stock disponible dans l’emplacement source.'
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class StockReplenishmentRequest(models.Model):
    STATUS_CHOICES = [
        ('requested', 'Demandée'),
        ('accepted', 'Acceptée'),
        ('partially_received', 'Partiellement réceptionnée'),
        ('rejected', 'Refusée'),
        ('completed', 'Terminée'),
    ]

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='replenishment_requests',
    )
    shop = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='replenishment_requests',
    )
    reference = models.CharField(
        max_length=16,
        unique=True,
        default=generate_replenishment_reference,
    )
    requested_quantity = models.PositiveIntegerField()
    approved_quantity = models.PositiveIntegerField(null=True, blank=True)
    request_reason = models.TextField(blank=True, default='')
    refusal_reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='requested')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_replenishment_requests',
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_replenishment_requests_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'shop'],
                condition=models.Q(status__in=['requested', 'accepted', 'partially_received']),
                name='unique_open_stock_replenishment',
            ),
        ]

    def __str__(self):
        return f'{self.reference} - {self.product.name} @ {self.shop.name}'


class InventoryCostLayer(models.Model):
    SOURCE_CHOICES = [
        ('opening', 'Opening balance'),
        ('receipt', 'Purchase receipt'),
        ('movement', 'Stock movement'),
        ('adjustment', 'Stock adjustment'),
        ('transfer', 'Stock transfer'),
        ('return', 'Sales return'),
    ]

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='cost_layers',
    )
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='cost_layers',
        null=True,
        blank=True,
    )
    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.PROTECT,
        related_name='cost_layers',
        null=True,
        blank=True,
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    reference = models.CharField(max_length=120, blank=True, default='')
    received_at = models.DateTimeField(default=timezone.now)
    quantity_received = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['received_at', 'id']
        indexes = [
            models.Index(
                fields=['product', 'location', 'is_available', 'received_at'],
                name='inv_cost_fifo_idx',
            ),
        ]

    def __str__(self):
        return f'{self.product_id} x {self.quantity_remaining} @ {self.unit_cost}'


class Carton(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='cartons')
    location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT, related_name='cartons')
    purchase_receipt = models.ForeignKey(
        'purchases.PurchaseReceipt',
        on_delete=models.PROTECT,
        related_name='cartons',
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=120, unique=True)
    quantity = models.PositiveIntegerField(default=0)
    initial_quantity = models.PositiveIntegerField(default=0)
    items_per_carton = models.PositiveIntegerField(default=1)
    supplier_reference = models.CharField(max_length=120, blank=True, default='')
    supplier_barcode = models.CharField(max_length=120, blank=True, default='')
    qr_code = models.CharField(max_length=200, blank=True, default='', unique=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.product.name}'

    def generate_qr_code(self):
        if self.qr_code:
            return self.qr_code
        self.qr_code = f'KAP-CTN-{self.pk:06d}' if self.pk else ''
        return self.qr_code

    def save(self, *args, **kwargs):
        if not self.initial_quantity:
            self.initial_quantity = self.quantity
        super().save(*args, **kwargs)
        if not self.qr_code:
            self.qr_code = self.generate_qr_code()
            super().save(update_fields=['qr_code'])


class StockUnit(models.Model):
    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('sample', 'Échantillon'),
        ('in_transit', 'En transit'),
        ('quarantined', 'En quarantaine'),
        ('sold', 'Vendu'),
        ('written_off', 'Sorti du stock'),
        ('historical_unknown', 'Historique antérieur non tracé'),
    ]

    carton = models.ForeignKey(Carton, on_delete=models.PROTECT, related_name='units')
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='stock_units',
    )
    transfer = models.ForeignKey(
        'StockTransfer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='units_in_transit',
    )
    is_separated = models.BooleanField(default=False)
    unit_number = models.PositiveIntegerField()
    reference = models.CharField(max_length=120, unique=True)
    qr_code = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='available')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['carton_id', 'unit_number']
        constraints = [
            models.UniqueConstraint(
                fields=['carton', 'unit_number'],
                name='unique_unit_number_per_carton',
            ),
        ]

    def __str__(self):
        return f'{self.reference} — {self.carton.reference}'


class LabelPrintJob(models.Model):
    LABEL_TYPES = [
        ('carton', 'Cartons'),
        ('unit', 'Pièces individuelles'),
        ('both', 'Cartons et pièces'),
    ]

    purchase_receipt = models.ForeignKey(
        'purchases.PurchaseReceipt',
        on_delete=models.PROTECT,
        related_name='label_print_jobs',
    )
    label_type = models.CharField(max_length=12, choices=LABEL_TYPES)
    label_references = models.JSONField(default=list)
    label_count = models.PositiveIntegerField()
    reason = models.CharField(max_length=240, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_label_print_jobs',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class SampleCarton(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='sample_cartons')
    location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT, related_name='sample_cartons')
    reference = models.CharField(max_length=120, unique=True)
    sample_count = models.PositiveIntegerField()
    qr_code = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.product.name}'

    def save(self, *args, **kwargs):
        if not self.reference or not self.qr_code:
            token = uuid4().hex[:12].upper()
            self.reference = self.reference or f'SMP-CTN-{token}'
            self.qr_code = self.qr_code or f'KAP-SMP-CTN-{token}'
        super().save(*args, **kwargs)


class StockTransferCarton(models.Model):
    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name='carton_allocations',
    )
    carton = models.ForeignKey(
        Carton,
        on_delete=models.PROTECT,
        related_name='transfer_allocations',
    )
    quantity_shipped = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(null=True, blank=True)
    is_partial = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['transfer', 'carton'],
                name='unique_carton_per_stock_transfer',
            ),
        ]


class InventoryCount(models.Model):
    PERIOD_TYPES = [
        ('journalier', 'Journalier'),
        ('mensuel', 'Mensuel'),
        ('trimestriel', 'Trimestriel'),
        ('annuel', 'Annuel'),
    ]
    STATUS_CHOICES = [
        ('draft', 'En cours'),
        ('submitted', 'Soumis pour validation'),
        ('validated', 'Validé'),
    ]

    number = models.CharField(max_length=120, unique=True)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES, default='journalier')
    location = models.ForeignKey(InventoryLocation, on_delete=models.PROTECT, related_name='inventory_counts')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_counts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submitted_inventory_counts',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.number


class InventoryCountItem(models.Model):
    inventory_count = models.ForeignKey(InventoryCount, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='inventory_count_items')
    theoretical_quantity = models.IntegerField(default=0)
    counted_quantity = models.IntegerField(default=0)

    class Meta:
        unique_together = ('inventory_count', 'product')
        ordering = ['product__name']


class StockFileImport(models.Model):
    MODE_CHOICES = [
        ('initial', 'Stock initial'),
        ('inventory', 'Inventaire physique'),
    ]
    STATUS_CHOICES = [
        ('preview', 'Aperçu'),
        ('submitted', 'Inventaires soumis'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='stock_file_imports',
    )
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    source_name = models.CharField(max_length=255)
    source_sha256 = models.CharField(max_length=64)
    headers = models.JSONField(default=list)
    rows = models.JSONField(default=list)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preview')
    count_ids = models.JSONField(default=list, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='stock_file_imports',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'mode', 'source_sha256'],
                name='unique_stock_file_import_per_mode',
            ),
        ]
