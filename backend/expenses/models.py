from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import Tenant
from finance.models import FinancialAccount, Fund


class ExpenseCategory(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='expense_categories',
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_expense_category_name_per_tenant',
            ),
            models.UniqueConstraint(
                fields=['name'],
                condition=Q(tenant__isnull=True),
                name='unique_unassigned_expense_category_name',
            ),
        ]

    def __str__(self):
        return self.name


class Expense(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('pending', 'En attente de validation'),
        ('validated', 'Validée'),
        ('rejected', 'Rejetée'),
        ('cancelled', 'Annulée'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='expenses',
    )
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses')
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expense_date = models.DateTimeField(auto_now_add=True)
    beneficiary = models.CharField(max_length=200, blank=True, default='')
    reference = models.CharField(max_length=120, blank=True, default='')
    justification = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, null=True, blank=True, related_name='expenses')
    fund = models.ForeignKey(Fund, on_delete=models.PROTECT, null=True, blank=True, related_name='expenses')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')
    cancellation_reason = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f'{self.title} - {self.amount}'


class ExpenseAttachment(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='expense_justifications/')
    original_name = models.CharField(max_length=255, blank=True, default='')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
