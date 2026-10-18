from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import Tenant
from finance.models import FinancialAccount, FinancialTransaction
from inventory.models import InventoryLocation, StockItem, StockMovement
from products.models import Product
from suppliers.models import Supplier


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('submitted', 'Soumise'),
        ('approved', 'Approuvée'),
        ('partial_received', 'Réception partielle'),
        ('received', 'Reçue'),
        ('closed', 'Clôturée'),
        ('rejected', 'Rejetée'),
        ('cancelled', 'Annulée'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_orders',
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    reference = models.CharField(max_length=120, unique=True)
    order_date = models.DateTimeField(auto_now_add=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    currency = models.CharField(max_length=10, default='GNF')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('1'))
    exchange_rate_date = models.DateField(null=True, blank=True)
    reference_exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    exchange_rate_reason = models.TextField(blank=True, default='')
    exchange_rate_applied_at = models.DateTimeField(null=True, blank=True)
    exchange_rate_applied_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_exchange_rates_applied',
    )
    notes = models.TextField(blank=True, default='')
    decision_reason = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_amount(self):
        return sum(item.total_price for item in self.items.all())

    class Meta:
        ordering = ['-order_date']

    def __str__(self):
        return f'{self.reference} - {self.supplier.name}'


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='purchase_order_items')
    quantity = models.IntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        return self.quantity * self.unit_cost

    class Meta:
        unique_together = ('purchase_order', 'product')

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'


class ExternalPurchase(models.Model):
    DELIVERY_MODES = [
        ('direct', 'Livraison directe au client'),
        ('warehouse', 'Passage par la boutique ou l’entrepôt'),
    ]
    STATUS_CHOICES = [
        ('confirmed', 'Confirmé'),
        ('cancelled', 'Annulé'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='external_purchases',
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='external_purchases',
    )
    sale = models.ForeignKey(
        'sales.Sale',
        on_delete=models.PROTECT,
        related_name='external_purchases',
    )
    sale_item = models.ForeignKey(
        'sales.SaleItem',
        on_delete=models.PROTECT,
        related_name='external_purchases',
    )
    reference = models.CharField(max_length=40, unique=True)
    item_name = models.CharField(max_length=220)
    item_reference = models.CharField(max_length=120, blank=True, default='')
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    additional_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    purchase_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    delivery_mode = models.CharField(max_length=20, choices=DELIVERY_MODES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    proof_reference = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='external_purchases_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-purchase_date', '-id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='external_purchase_quantity_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(unit_cost__gte=0),
                name='external_purchase_unit_cost_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(additional_cost__gte=0),
                name='external_purchase_additional_cost_nonnegative',
            ),
        ]

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost + self.additional_cost

    @property
    def total_paid(self):
        return self.payment_allocations.filter(
            payment__financial_transaction__status='validated',
        ).aggregate(total=models.Sum('amount'))['total'] or 0

    @property
    def balance_due(self):
        return max(self.total_cost - self.total_paid, 0)

    @property
    def payment_status(self):
        if self.balance_due == 0:
            return 'paid'
        return 'partial' if self.total_paid else 'unpaid'

    def __str__(self):
        return f'{self.reference} - {self.item_name}'


class ExternalPurchasePayment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Espèces'),
        ('mobile_money', 'Mobile money'),
        ('bank_transfer', 'Virement bancaire'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='external_purchase_payments',
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='external_purchase_payments',
    )
    financial_transaction = models.OneToOneField(
        FinancialTransaction,
        on_delete=models.PROTECT,
        related_name='external_purchase_payment',
    )
    financial_account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name='external_purchase_payments',
    )
    reference = models.CharField(max_length=40, unique=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES)
    payment_date = models.DateTimeField(default=timezone.now)
    proof_reference = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='external_purchase_payments_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='external_purchase_payment_amount_positive',
            ),
        ]

    def __str__(self):
        return f'{self.reference} - {self.amount}'


class ExternalPurchasePaymentAllocation(models.Model):
    payment = models.ForeignKey(
        ExternalPurchasePayment,
        on_delete=models.PROTECT,
        related_name='allocations',
    )
    purchase = models.ForeignKey(
        ExternalPurchase,
        on_delete=models.PROTECT,
        related_name='payment_allocations',
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['payment', 'purchase'],
                name='unique_external_payment_purchase_allocation',
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='external_payment_allocation_amount_positive',
            ),
        ]


class ExternalPurchaseMovement(models.Model):
    MOVEMENT_CHOICES = [
        ('received', 'Réception physique'),
        ('delivered', 'Sortie vers le client'),
        ('direct_delivery', 'Livraison directe au client'),
    ]

    purchase = models.ForeignKey(
        ExternalPurchase,
        on_delete=models.PROTECT,
        related_name='movements',
    )
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='external_purchase_movements',
        null=True,
        blank=True,
    )
    movement_type = models.CharField(max_length=24, choices=MOVEMENT_CHOICES)
    quantity = models.PositiveIntegerField()
    reference = models.CharField(max_length=120, blank=True, default='')
    proof_reference = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    occurred_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='external_purchase_movements_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['occurred_at', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='external_purchase_movement_quantity_positive',
            ),
        ]


class PurchaseReceipt(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('submitted', 'En attente de validation'),
        ('changes_requested', 'Correction demandée'),
        ('on_hold', 'En attente de contrôle'),
        ('rejected', 'Rejetée'),
        ('received', 'Reçue'),
        ('cancelled', 'Annulée'),
    ]
    ALLOCATION_METHOD_CHOICES = [
        ('quantity', 'Par quantité'),
        ('value', 'Par valeur'),
        ('weight', 'Par poids'),
        ('volume', 'Par volume'),
    ]

    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='receipts')
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='purchase_receipts',
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=120, unique=True)
    received_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    currency = models.CharField(max_length=10, default='GNF')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('1'))
    exchange_rate_date = models.DateField(null=True, blank=True)
    cost_status = models.CharField(
        max_length=20,
        choices=[('provisional', 'Provisoire'), ('final', 'Définitif')],
        default='provisional',
    )
    allocation_method = models.CharField(max_length=20, choices=ALLOCATION_METHOD_CHOICES, default='quantity')
    notes = models.TextField(blank=True, default='')
    supplier_document_reference = models.CharField(max_length=255, blank=True, default='')
    discrepancy_reason = models.TextField(blank=True, default='')
    decision_reason = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_receipts_created',
    )
    submitted_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_receipts_submitted',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_receipts_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    reviewed_version = models.PositiveIntegerField(null=True, blank=True)
    transport_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customs_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    handling_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    insurance_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def total_acquisition_costs(self):
        return sum([
            Decimal(str(self.transport_cost)),
            Decimal(str(self.customs_cost)),
            Decimal(str(self.handling_cost)),
            Decimal(str(self.insurance_cost)),
            Decimal(str(self.other_cost)),
        ])

    @property
    def total_cost(self):
        return self.subtotal + self.total_acquisition_costs

    class Meta:
        ordering = ['-received_date']

    def __str__(self):
        return f'{self.reference} - {self.purchase_order.reference}'


class PurchaseReceiptItem(models.Model):
    purchase_receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='receipt_items')
    quantity_received = models.IntegerField(default=0)
    quantity_accepted = models.PositiveIntegerField(default=0)
    quantity_quarantined = models.PositiveIntegerField(default=0)
    quantity_quarantine_remaining = models.PositiveIntegerField(default=0)
    discrepancy_reason = models.TextField(blank=True, default='')
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    items_per_carton = models.PositiveIntegerField(default=1)
    supplier_reference = models.CharField(max_length=120, blank=True, default='')
    supplier_barcode = models.CharField(max_length=120, blank=True, default='')
    supplier_lot_reference = models.CharField(max_length=120, blank=True, default='')
    condition_status = models.CharField(max_length=120, blank=True, default='')
    packaging_condition = models.CharField(max_length=120, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def line_total(self):
        return self.quantity_received * self.unit_cost

    @property
    def acquisition_costs(self):
        if self.quantity_received <= 0:
            return Decimal('0')

        total_acquisition_costs = self.purchase_receipt.total_acquisition_costs
        if total_acquisition_costs == 0:
            return Decimal('0')

        allocation_method = self.purchase_receipt.allocation_method
        if allocation_method == 'value':
            base_for_item = self.line_total
            total_base = sum(item.line_total for item in self.purchase_receipt.items.all())
        elif allocation_method == 'weight':
            weight_for_item = getattr(self.product, 'weight', 0) or 0
            base_for_item = Decimal(str(weight_for_item)) * Decimal(self.quantity_received)
            total_base = sum(
                (Decimal(str(getattr(item.product, 'weight', 0) or 0)) * Decimal(item.quantity_received))
                for item in self.purchase_receipt.items.all()
            )
        elif allocation_method == 'volume':
            volume_for_item = getattr(self.product, 'volume', 0) or 0
            base_for_item = Decimal(str(volume_for_item)) * Decimal(self.quantity_received)
            total_base = sum(
                (Decimal(str(getattr(item.product, 'volume', 0) or 0)) * Decimal(item.quantity_received))
                for item in self.purchase_receipt.items.all()
            )
        else:
            base_for_item = Decimal(self.quantity_received)
            total_base = sum(item.quantity_received for item in self.purchase_receipt.items.all())

        if total_base <= 0:
            return Decimal('0')

        allocated_total = total_acquisition_costs * (base_for_item / total_base)
        return allocated_total / Decimal(self.quantity_received)

    @property
    def real_unit_cost(self):
        return self.unit_cost + self.acquisition_costs

    @property
    def real_line_total(self):
        return self.quantity_received * self.real_unit_cost

    class Meta:
        unique_together = ('purchase_receipt', 'product')

    def __str__(self):
        return f'{self.product.name} x {self.quantity_received}'

    @property
    def base_unit_cost(self):
        return self.real_unit_cost * self.purchase_receipt.exchange_rate


class ReceiptQuarantine(models.Model):
    STATUS_CHOICES = [
        ('quarantined', 'En quarantaine'),
        ('partially_released', 'Partiellement libéré'),
        ('released', 'Libéré'),
        ('written_off', 'Retiré du stock'),
    ]

    receipt_item = models.OneToOneField(
        PurchaseReceiptItem,
        on_delete=models.PROTECT,
        related_name='quarantine_record',
    )
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name='receipt_quarantines',
    )
    quantity = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='quarantined')
    reason = models.TextField()
    resolution_reason = models.TextField(blank=True, default='')
    resolved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipt_quarantines_resolved',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
