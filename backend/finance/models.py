from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import Tenant


class FinancialAccount(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('cash', 'Caisse'),
        ('bank', 'Compte bancaire'),
        ('other', 'Autre compte'),
    ]
    STATUS_CHOICES = [
        ('active', 'Actif'),
        ('inactive', 'Inactif'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='financial_accounts',
    )
    name = models.CharField(max_length=160)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='cash')
    currency = models.CharField(max_length=10, default='GNF')
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_financial_account_name_per_tenant',
            ),
            models.UniqueConstraint(
                fields=['name'],
                condition=Q(tenant__isnull=True),
                name='unique_unassigned_financial_account_name',
            ),
        ]

    @property
    def current_balance(self):
        incoming = self.transactions.filter(status='validated', direction='in').aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        outgoing = self.transactions.filter(status='validated', direction='out').aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        return self.opening_balance + incoming - outgoing


class FinancialTransaction(models.Model):
    TYPE_CHOICES = [
        ('income', 'Recette'),
        ('expense', 'Dépense'),
        ('payment', 'Paiement'),
        ('refund', 'Remboursement'),
        ('transfer', 'Transfert'),
        ('adjustment', 'Ajustement'),
        ('fund_return', 'Retour de fonds'),
        ('other', 'Autre'),
    ]
    DIRECTION_CHOICES = [('in', 'Entrée'), ('out', 'Sortie')]
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('validated', 'Validé'),
        ('cancelled', 'Annulé'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='financial_transactions',
    )
    reference = models.CharField(max_length=40, unique=True, editable=False)
    transaction_date = models.DateTimeField(default=timezone.now)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default='GNF')
    account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, related_name='transactions')
    category = models.CharField(max_length=120, blank=True, default='')
    description = models.TextField(blank=True, default='')
    origin = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='financial_transactions_created')
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='financial_transactions_validated')
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_date', '-id']

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.localdate().year
            last_id = FinancialTransaction.objects.filter(created_at__year=year).order_by('-id').values_list('id', flat=True).first() or 0
            self.reference = f'TRX-{year}-{last_id + 1:06d}'
        super().save(*args, **kwargs)


class Fund(models.Model):
    STATUS_CHOICES = [
        ('open', 'En cours'),
        ('closed', 'Clôturé'),
        ('cancelled', 'Annulé'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='funds',
    )
    reference = models.CharField(max_length=40, unique=True, editable=False)
    purpose = models.CharField(max_length=200)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='managed_funds')
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default='GNF')
    assigned_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='funds_created')
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-assigned_at', '-id']

    @property
    def spent_amount(self):
        return self.expenses.filter(status='validated').aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def returned_amount(self):
        return self.returns.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def remaining_to_regularize(self):
        return max(self.amount - self.spent_amount - self.returned_amount, Decimal('0'))

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.localdate().year
            last_id = Fund.objects.filter(created_at__year=year).order_by('-id').values_list('id', flat=True).first() or 0
            self.reference = f'FND-{year}-{last_id + 1:05d}'
        super().save(*args, **kwargs)


class FundReturn(models.Model):
    fund = models.ForeignKey(Fund, on_delete=models.PROTECT, related_name='returns')
    reference = models.CharField(max_length=40, unique=True, editable=False)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    returned_at = models.DateTimeField(default=timezone.now)
    returned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='fund_returns')
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-returned_at', '-id']

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.localdate().year
            last_id = FundReturn.objects.filter(returned_at__year=year).order_by('-id').values_list('id', flat=True).first() or 0
            self.reference = f'RET-{year}-{last_id + 1:05d}'
        super().save(*args, **kwargs)