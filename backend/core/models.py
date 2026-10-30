from calendar import monthrange

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import FileExtensionValidator, RegexValidator
from django.utils import timezone

from .storefront_storage import (
    private_storefront_storage,
    storefront_cover_path,
    storefront_logo_path,
)


class Tenant(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente d’activation'),
        ('active', 'Active'),
        ('suspended', 'Suspendue'),
    ]

    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    trial_activated_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    max_users = models.PositiveIntegerField(default=10)
    enabled_modules = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def activate_trial(self, activated_at=None):
        if self.trial_activated_at is not None:
            raise ValidationError('La période d’essai est déjà activée.')

        activated_at = activated_at or timezone.now()
        month_offset = activated_at.month - 1 + 3
        end_year = activated_at.year + month_offset // 12
        end_month = month_offset % 12 + 1
        end_day = min(activated_at.day, monthrange(end_year, end_month)[1])

        self.status = 'active'
        self.trial_activated_at = activated_at
        self.trial_ends_at = activated_at.replace(
            year=end_year,
            month=end_month,
            day=end_day,
        )
        self.save(update_fields=[
            'status',
            'trial_activated_at',
            'trial_ends_at',
            'updated_at',
        ])

    @property
    def effective_status(self):
        return self.status_at()

    def status_at(self, now=None):
        now = now or timezone.now()
        if self.status != 'active':
            return self.status
        if self.trial_ends_at and self.trial_ends_at <= now:
            return 'expired'
        return 'active'

    def __str__(self):
        return self.name


class PlatformSettings(models.Model):
    max_tenants = models.PositiveIntegerField(null=True, blank=True, default=None)
    max_active_users = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'DJIBEXA Platform Settings'


class PlatformAuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Création'),
        ('update', 'Mise à jour'),
        ('activate', 'Activation'),
        ('suspend', 'Suspension'),
        ('resume', 'Reprise'),
        ('invite_admin', 'Invitation du premier administrateur'),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='platform_audit_logs',
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='platform_audit_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.actor} - {self.action}'


class PlatformTaskRun(models.Model):
    STATUS_CHOICES = [
        ('running', 'En cours'),
        ('succeeded', 'Réussie'),
        ('failed', 'Échec'),
    ]

    task_name = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_type = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-started_at', '-id']
        indexes = [
            models.Index(fields=['task_name', '-started_at']),
        ]

    def __str__(self):
        return f'{self.task_name} - {self.status}'


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Création'),
        ('update', 'Mise à jour'),
        ('delete', 'Suppression'),
        ('login', 'Connexion'),
        ('payment', 'Paiement'),
        ('sale', 'Vente'),
        ('stock', 'Stock'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, default='create')
    model_name = models.CharField(max_length=120, blank=True, default='')
    record_id = models.PositiveIntegerField(default=0)
    details = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.action}'


class AppSetting(models.Model):
    key = models.CharField(max_length=120, unique=True)
    value = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key


class Company(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='company_profile',
    )
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=240, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    address = models.TextField(blank=True, default='')
    currency = models.CharField(max_length=10, default='GNF')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name


def default_storefront_content():
    return {
        'title': '',
        'industry': '',
        'tagline': '',
        'description': '',
        'phone': '',
        'email': '',
        'address': '',
        'city': '',
        'primary_color': '#123D60',
        'accent_color': '#0EA5E9',
        'services': [],
        'categories': [],
        'sections': {
            'about': True,
            'services': True,
            'categories': True,
            'contact': True,
        },
    }


class TenantStorefront(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.PROTECT,
        related_name='storefront',
    )
    draft_content = models.JSONField(default=default_storefront_content)
    published_content = models.JSONField(default=dict, blank=True)
    draft_logo = models.ImageField(
        upload_to=storefront_logo_path,
        storage=private_storefront_storage,
        blank=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
    )
    published_logo = models.ImageField(
        upload_to=storefront_logo_path,
        storage=private_storefront_storage,
        blank=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
    )
    draft_cover = models.ImageField(
        upload_to=storefront_cover_path,
        storage=private_storefront_storage,
        blank=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
    )
    published_cover = models.ImageField(
        upload_to=storefront_cover_path,
        storage=private_storefront_storage,
        blank=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
    )
    published_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='storefront_updates',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'vitrine publique'
        verbose_name_plural = 'vitrines publiques'

    def __str__(self):
        return f'Vitrine de {self.tenant.name}'


class Partner(models.Model):
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=300, blank=True, default='')
    logo_url = models.URLField(max_length=500, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    whatsapp = models.CharField(max_length=30, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    website = models.URLField(max_length=500, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    show_on_invoice = models.BooleanField(default=True)
    show_on_orders = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class IdempotencyRecord(models.Model):
    key = models.CharField(max_length=255)
    endpoint = models.CharField(max_length=255)
    scope_hash = models.CharField(max_length=64, unique=True)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class SyncOperation(models.Model):
    STATUS_CHOICES = [
        ('accepted', 'Acceptée'),
        ('rejected', 'Rejetée'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sync_operations')
    local_id = models.CharField(max_length=120)
    operation_type = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'local_id'], name='unique_sync_operation_per_user'),
        ]
        ordering = ['-created_at']
