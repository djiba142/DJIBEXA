from datetime import time as datetime_time

from django.db import models

from customers.models import Customer
from sales.models import Sale


class TenantCreditReminderSettings(models.Model):
    tenant = models.OneToOneField(
        'core.Tenant',
        on_delete=models.PROTECT,
        related_name='credit_reminder_settings',
    )
    enabled = models.BooleanField(default=True)
    frequency = models.CharField(
        max_length=20,
        choices=[('weekly', 'Hebdomadaire')],
        default='weekly',
    )
    day_of_week = models.PositiveSmallIntegerField(default=4)
    time = models.TimeField(default=datetime_time(17, 0))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(day_of_week__gte=0, day_of_week__lte=6),
                name='credit_reminder_day_in_week',
            ),
        ]

    def __str__(self):
        return f'Rappels de crédit — {self.tenant.name}'


class Notification(models.Model):
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.PROTECT,
        related_name='notifications',
        null=True,
        blank=True,
    )
    CHANNEL_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('email', 'Email'),
        ('internal', 'Interne'),
    ]

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('sent', 'Envoyé'),
        ('failed', 'Échec'),
        ('retry', 'Retry'),
        ('cancelled', 'Annulé'),
    ]

    EVENT_CHOICES = [
        ('sale_confirmed', 'Vente confirmée'),
        ('payment_received', 'Paiement reçu'),
        ('invoice_sent', 'Facture envoyée'),
        ('credit_reminder', 'Rappel crédit'),
        ('stock_replenishment_requested', 'Demande de ravitaillement'),
    ]

    recipient_user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='notifications_received',
        null=True,
        blank=True,
    )
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        related_name='notifications',
        null=True,
        blank=True,
    )
    channel = models.CharField(max_length=30, choices=CHANNEL_CHOICES, default='whatsapp')
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES, default='sale_confirmed')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True, default='')
    recipient_phone = models.CharField(max_length=30, blank=True, default='')
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default='')
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    reminder_period = models.CharField(max_length=10, blank=True, default='')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'reminder_period', 'event_type', 'channel'],
                condition=models.Q(event_type='credit_reminder', reminder_period__gt=''),
                name='unique_customer_credit_reminder_period',
            ),
        ]

    def __str__(self):
        return f'{self.get_event_type_display()} - {self.get_status_display()}'
