from calendar import monthrange
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db.models.functions import Lower
from django.utils import timezone

from .storefront_storage import (
    private_storefront_storage,
    storefront_cover_path,
    storefront_logo_path,
)
from .billing_storage import private_billing_storage, billing_proof_path


class Tenant(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('provisioning', 'Provisionnement en cours'),
        ('pending', 'En attente d’activation'),
        ('pending_activation', 'En attente d’activation'),
        ('trial', 'Période d’essai'),
        ('active', 'Active'),
        ('suspended', 'Suspendue'),
        ('blocked', 'Bloquée'),
        ('expired', 'Expirée'),
        ('archived', 'Archivée'),
        ('deletion_pending', 'Suppression demandée'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code = models.SlugField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=240, blank=True, default='')
    sector = models.CharField(max_length=120, blank=True, default='')
    description = models.TextField(blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=120, blank=True, default='')
    country = models.CharField(max_length=2, blank=True, default='')
    currency = models.CharField(max_length=3, default='GNF')
    language = models.CharField(max_length=10, default='fr')
    timezone = models.CharField(max_length=64, default='Africa/Conakry')
    logo = models.URLField(max_length=500, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    trial_activated_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    trial_duration_months = models.PositiveSmallIntegerField(default=3)
    max_users = models.PositiveIntegerField(default=10)
    enabled_modules = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name', 'id']

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.slug
        super().save(*args, **kwargs)

    def activate_trial(self, activated_at=None):
        if self.trial_activated_at is not None:
            raise ValidationError('La période d’essai est déjà activée.')

        activated_at = activated_at or timezone.now()
        month_offset = activated_at.month - 1 + self.trial_duration_months
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
        if self.status not in {'active', 'trial'}:
            return self.status
        if self.trial_ends_at and self.trial_ends_at <= now:
            return 'expired'
        return 'active'

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrateur entreprise'),
        ('sales', 'Vendeur'),
        ('stock', 'Gestionnaire de stock'),
        ('other', 'Autre rôle'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='tenant_memberships',
    )
    role = models.CharField(max_length=40, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    is_primary_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tenant_id', 'user_id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'user'],
                name='core_unique_tenant_membership',
            ),
            models.UniqueConstraint(
                fields=['tenant'],
                condition=models.Q(is_active=True, is_primary_admin=True),
                name='core_one_active_primary_admin_per_tenant',
            ),
        ]

    def __str__(self):
        return f'{self.user} — {self.tenant} ({self.role})'


class TenantDomain(models.Model):
    DOMAIN_TYPE_CHOICES = [
        ('application', 'Application'),
        ('storefront', 'Vitrine publique'),
    ]
    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('verified', 'Vérifié'),
        ('rejected', 'Refusé'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='domains',
    )
    hostname = models.CharField(max_length=253)
    domain_type = models.CharField(
        max_length=20,
        choices=DOMAIN_TYPE_CHOICES,
        default='application',
    )
    verification_status = models.CharField(
        max_length=12,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending',
    )
    is_primary = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_token_hash = models.CharField(max_length=64, blank=True, default='')
    verification_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['tenant_id', 'hostname']
        constraints = [
            models.UniqueConstraint(
                Lower('hostname'),
                name='core_unique_tenant_domain_hostname_ci',
            ),
            models.UniqueConstraint(
                fields=['tenant'],
                condition=models.Q(is_primary=True),
                name='core_one_primary_domain_per_tenant',
            ),
        ]

    def save(self, *args, **kwargs):
        self.hostname = self.hostname.strip().rstrip('.').lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.hostname


class PlatformSettings(models.Model):
    max_tenants = models.PositiveIntegerField(null=True, blank=True, default=None)
    max_active_users = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'DJIBEXA Platform Settings'


class PlatformModule(models.Model):
    TECHNICAL_STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('planned', 'Prévu'),
        ('deprecated', 'Déprécié'),
    ]

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True, default='')
    dependencies = models.JSONField(default=list, blank=True)
    technical_status = models.CharField(
        max_length=12,
        choices=TECHNICAL_STATUS_CHOICES,
        default='available',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name', 'id']

    def __str__(self):
        return self.name


class PlatformPlan(models.Model):
    BILLING_PERIOD_CHOICES = [
        ('monthly', 'Mensuel'),
        ('quarterly', 'Trimestriel'),
        ('yearly', 'Annuel'),
    ]

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True, default='')
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GNF')
    billing_period = models.CharField(
        max_length=12,
        choices=BILLING_PERIOD_CHOICES,
        default='monthly',
    )
    duration_months = models.PositiveSmallIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=10)
    modules = models.ManyToManyField(PlatformModule, related_name='plans', blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def __str__(self):
        return self.name


class PlanFeature(models.Model):
    plan = models.ForeignKey(
        PlatformPlan,
        on_delete=models.PROTECT,
        related_name='feature_versions',
    )
    feature = models.ForeignKey(
        PlatformModule,
        on_delete=models.PROTECT,
        related_name='plan_feature_versions',
    )
    version = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=True)
    limits = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['plan_id', 'feature_id', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['plan', 'feature', 'version'],
                name='core_unique_plan_feature_version',
            ),
        ]

    def __str__(self):
        return f'{self.plan} — {self.feature} (v{self.version})'


class TenantSubscription(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente de paiement'),
        ('active', 'Active'),
        ('suspended', 'Suspendue'),
        ('cancelled', 'Résiliée'),
        ('expired', 'Expirée'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    plan = models.ForeignKey(
        PlatformPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GNF')
    duration_months = models.PositiveSmallIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=10)
    included_modules = models.JSONField(default=list, blank=True)
    feature_snapshot = models.JSONField(default=dict, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    grace_period_ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_platform_subscriptions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant'],
                condition=models.Q(status__in=['pending', 'active', 'suspended']),
                name='core_one_current_subscription_per_tenant',
            ),
        ]

    def __str__(self):
        return f'{self.tenant} - {self.plan}'


class BillingInvoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('open', 'À régler'),
        ('paid', 'Réglée'),
        ('void', 'Annulée'),
        ('overdue', 'En retard'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='billing_invoices',
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.PROTECT,
        related_name='billing_invoices',
        null=True,
        blank=True,
    )
    invoice_number = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GNF')
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    description = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'invoice_number'],
                name='core_unique_billing_invoice_number_per_tenant',
            ),
        ]

    def __str__(self):
        return f'{self.invoice_number} — {self.tenant}'


class PaymentRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'À vérifier'),
        ('confirmed', 'Confirmé'),
        ('rejected', 'Rejeté'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='payment_records',
    )
    invoice = models.ForeignKey(
        BillingInvoice,
        on_delete=models.PROTECT,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GNF')
    payment_method = models.CharField(max_length=20)
    payment_reference = models.CharField(max_length=120, blank=True, default='')
    received_at = models.DateTimeField(default=timezone.now)
    proof_file = models.FileField(
        upload_to=billing_proof_path,
        storage=private_billing_storage,
        blank=True,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_billing_payments',
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='verified_billing_payments',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    notes = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at', '-id']

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors['amount'] = 'Le montant doit être supérieur à zéro.'
        if (
            self.invoice_id
            and self.tenant_id
            and self.invoice.tenant_id != self.tenant_id
        ):
            errors['invoice'] = 'La facture doit appartenir à la même entreprise.'
        if self.status == 'confirmed' and not self.verified_by_id:
            errors['verified_by'] = 'Un paiement confirmé doit avoir un vérificateur.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.invoice.invoice_number} — {self.amount} {self.currency}'


class Invitation(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='invitations',
    )
    email = models.EmailField(max_length=254)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tenant_invitations',
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_tenant_invitations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['tenant', 'email', 'expires_at']),
        ]

    def __str__(self):
        return f'{self.email} — {self.tenant}'


class EmailOutbox(models.Model):
    STATUS_CHOICES = [
        ('queued', 'En attente'),
        ('sending', 'En cours d’envoi'),
        ('sent', 'Envoyé'),
        ('failed', 'Échec'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_outbox',
    )
    recipient = models.EmailField(max_length=254)
    template_code = models.CharField(max_length=100)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='queued')
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default='')
    idempotency_key = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_attempt_at', 'created_at']
        indexes = [
            models.Index(fields=['status', 'next_attempt_at']),
        ]

    def __str__(self):
        return f'{self.template_code} — {self.recipient} ({self.status})'


class TenantUsageRecord(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='usage_records',
    )
    metric_code = models.CharField(max_length=80)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    measured_at = models.DateTimeField(default=timezone.now)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    class Meta:
        ordering = ['-measured_at', '-id']
        indexes = [
            models.Index(fields=['tenant', 'metric_code', '-measured_at']),
        ]

    def __str__(self):
        return f'{self.tenant} — {self.metric_code}: {self.quantity}'


class PlatformPayment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Espèces'),
        ('bank_transfer', 'Virement bancaire'),
        ('mobile_money', 'Mobile money'),
        ('other', 'Autre'),
    ]
    STATUS_CHOICES = [
        ('pending', 'À vérifier'),
        ('confirmed', 'Confirmé'),
        ('rejected', 'Rejeté'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='platform_payments',
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.PROTECT,
        related_name='payments',
    )
    payment_record = models.OneToOneField(
        PaymentRecord,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='platform_payment',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GNF')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=120, blank=True, default='')
    paid_at = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    notes = models.CharField(max_length=500, blank=True, default='')
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_platform_payments',
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_platform_payments',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.tenant} - {self.amount} {self.currency}'


class TenantModuleOverride(models.Model):
    STATUS_CHOICES = [
        ('inherit', 'Hérité du plan'),
        ('enabled', 'Activé'),
        ('disabled', 'Désactivé'),
        ('suspended', 'Suspendu temporairement'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='module_overrides',
    )
    module = models.ForeignKey(
        PlatformModule,
        on_delete=models.PROTECT,
        related_name='tenant_overrides',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    note = models.CharField(max_length=300, blank=True, default='')
    reason = models.CharField(max_length=500, blank=True, default='')
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_tenant_module_overrides',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='updated_tenant_module_overrides',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module__sort_order', 'module__name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'module'],
                name='core_unique_tenant_module_override',
            ),
        ]

    def __str__(self):
        return f'{self.tenant} - {self.module} - {self.status}'


class PlatformAuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Création'),
        ('update', 'Mise à jour'),
        ('activate', 'Activation'),
        ('suspend', 'Suspension'),
        ('resume', 'Reprise'),
        ('invite_admin', 'Invitation du premier administrateur'),
        ('plan_create', 'Création d’une offre'),
        ('plan_update', 'Modification d’une offre'),
        ('subscription_assign', 'Attribution d’un abonnement'),
        ('subscription_cancel', 'Résiliation d’un abonnement'),
        ('payment_record', 'Enregistrement d’un paiement'),
        ('payment_confirm', 'Confirmation d’un paiement'),
        ('payment_reject', 'Rejet d’un paiement'),
        ('module_override', 'Modification d’un module'),
        ('user_access', 'Modification d’un accès utilisateur'),
        ('settings_update', 'Modification des paramètres de la plateforme'),
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
    entity_type = models.CharField(max_length=120, blank=True, default='')
    entity_id = models.CharField(max_length=120, blank=True, default='')
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=500, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default='')
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


class PlatformDemoRequest(models.Model):
    STATUS_CHOICES = [
        ('new', 'Nouvelle'),
        ('contacted', 'Contactée'),
        ('closed', 'Clôturée'),
    ]

    company_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254)
    phone = models.CharField(max_length=30, blank=True, default='')
    message = models.TextField(max_length=2000)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='new')
    consent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.company_name} - {self.contact_name}'


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
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='business_audit_logs',
    )
    entity_type = models.CharField(max_length=120, blank=True, default='')
    entity_id = models.CharField(max_length=120, blank=True, default='')
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=500, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default='')
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
