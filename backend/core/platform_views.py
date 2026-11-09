import logging
import hashlib
import secrets
import shutil
from datetime import datetime, timedelta
from decimal import Decimal

import dns.exception
import dns.resolver
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsPlatformAdmin
from users.models import User

from .onboarding import send_password_setup_email
from .platform_entitlements import add_calendar_months
from .models import (
    PlatformAuditLog,
    PlatformDemoRequest,
    PlatformModule,
    PlatformPayment,
    PlatformPlan,
    PlatformSettings,
    PlatformTaskRun,
    BillingInvoice,
    PaymentRecord,
    PlanFeature,
    Tenant,
    TenantDomain,
    TenantMembership,
    TenantModuleOverride,
    TenantSubscription,
)
from .pagination import VersionedApiPagination

logger = logging.getLogger(__name__)


class DomainDnsUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'Le DNS ne répond pas dans le délai imparti. Réessayez plus tard.'


class PlatformTenantCreateSerializer(serializers.ModelSerializer):
    max_users = serializers.IntegerField(min_value=1, default=10)

    class Meta:
        model = Tenant
        fields = ['name', 'slug', 'max_users']


class PlatformTenantCapacitySerializer(serializers.ModelSerializer):
    max_users = serializers.IntegerField(min_value=1)

    class Meta:
        model = Tenant
        fields = ['max_users']


class PlatformModuleSerializer(serializers.ModelSerializer):
    dependencies = serializers.ListField(
        child=serializers.SlugField(max_length=50),
        required=False,
    )

    class Meta:
        model = PlatformModule
        fields = ['id', 'code', 'name', 'description', 'dependencies', 'sort_order', 'is_active']

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields['code'].read_only = True
        return fields

    def validate_dependencies(self, dependencies):
        if len(dependencies) != len(set(dependencies)):
            raise serializers.ValidationError('Une dépendance ne peut être choisie qu’une fois.')
        if self.instance and self.instance.code in dependencies:
            raise serializers.ValidationError('Un module ne peut pas dépendre de lui-même.')
        existing = set(
            PlatformModule.objects.filter(is_active=True).values_list('code', flat=True)
        )
        unknown = set(dependencies) - existing
        if unknown:
            raise serializers.ValidationError(
                f'Dépendance inconnue : {", ".join(sorted(unknown))}.'
            )
        code = self.instance.code if self.instance else self.initial_data.get('code')
        graph = {
            module.code: set(module.dependencies)
            for module in PlatformModule.objects.exclude(
                pk=self.instance.pk if self.instance else None
            )
        }
        graph[code] = set(dependencies)

        def has_cycle(current, ancestors):
            if current in ancestors:
                return True
            return any(
                has_cycle(dependency, ancestors | {current})
                for dependency in graph.get(current, ())
            )

        if has_cycle(code, set()):
            raise serializers.ValidationError('Les dépendances ne peuvent pas former de cycle.')
        return dependencies


class PlatformPlanSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    duration_months = serializers.IntegerField(min_value=1, max_value=36)
    max_users = serializers.IntegerField(min_value=1)
    currency = serializers.RegexField(r'^[A-Za-z]{3}$', default='GNF')
    modules = serializers.SlugRelatedField(
        many=True,
        slug_field='code',
        queryset=PlatformModule.objects.filter(is_active=True),
    )

    class Meta:
        model = PlatformPlan
        fields = [
            'id',
            'code',
            'name',
            'description',
            'price',
            'currency',
            'billing_period',
            'duration_months',
            'max_users',
            'modules',
            'is_active',
        ]

    def validate(self, attrs):
        modules = attrs.get(
            'modules',
            self.instance.modules.filter(is_active=True) if self.instance else [],
        )
        selected_codes = {module.code for module in modules}
        missing_dependencies = {
            dependency
            for module in modules
            for dependency in module.dependencies
            if dependency not in selected_codes
        }
        if missing_dependencies:
            raise serializers.ValidationError({
                'modules': (
                    'Incluez les dépendances requises : '
                    f'{", ".join(sorted(missing_dependencies))}.'
                ),
            })
        if 'currency' in attrs:
            attrs['currency'] = attrs['currency'].upper()
        return attrs


class PlatformSubscriptionCreateSerializer(serializers.Serializer):
    tenant_id = serializers.IntegerField(min_value=1)
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=PlatformPlan.objects.filter(is_active=True),
    )


class PlatformPaymentCreateSerializer(serializers.ModelSerializer):
    proof_file = serializers.FileField(required=False, allow_empty_file=False, write_only=True)
    subscription_id = serializers.PrimaryKeyRelatedField(
        source='subscription',
        queryset=TenantSubscription.objects.all(),
    )

    class Meta:
        model = PlatformPayment
        fields = ['subscription_id', 'amount', 'method', 'reference', 'paid_at', 'notes', 'proof_file']

    def create(self, validated_data):
        self.proof_file = validated_data.pop('proof_file', None)
        return super().create(validated_data)

    def validate_amount(self, amount):
        if amount <= 0:
            raise serializers.ValidationError('Le montant doit être supérieur à zéro.')
        return amount

    def validate_proof_file(self, proof_file):
        if proof_file.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('Le justificatif ne peut pas dépasser 10 Mo.')
        extension = proof_file.name.rsplit('.', 1)[-1].lower()
        if extension not in {'pdf', 'jpg', 'jpeg', 'png'}:
            raise serializers.ValidationError(
                'Formats acceptés : PDF, JPG, JPEG et PNG.'
            )
        return proof_file

    def validate(self, attrs):
        subscription = attrs['subscription']
        if subscription.status not in {'pending', 'active'}:
            raise serializers.ValidationError({
                'subscription_id': 'Cet abonnement ne peut pas recevoir de paiement.',
            })
        if attrs['amount'] != subscription.amount:
            raise serializers.ValidationError({
                'amount': 'Le montant doit correspondre au tarif de l’abonnement.',
            })
        attrs['currency'] = subscription.currency
        return attrs


class TenantModuleOverrideSerializer(serializers.Serializer):
    module_code = serializers.SlugRelatedField(
        source='module',
        slug_field='code',
        queryset=PlatformModule.objects.filter(is_active=True),
    )
    status = serializers.ChoiceField(
        choices=['enabled', 'disabled', 'suspended', 'inherit'],
    )
    note = serializers.CharField(max_length=300, allow_blank=True, required=False)


class PlatformSettingsSerializer(serializers.ModelSerializer):
    max_tenants = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    max_active_users = serializers.IntegerField(min_value=1, allow_null=True, required=False)

    class Meta:
        model = PlatformSettings
        fields = ['max_tenants', 'max_active_users']

    def validate(self, attrs):
        current_tenants = Tenant.objects.count()
        current_users = User.objects.filter(
            is_active=True,
            is_platform_admin=False,
        ).count()
        max_tenants = attrs.get('max_tenants', self.instance.max_tenants)
        max_active_users = attrs.get(
            'max_active_users',
            self.instance.max_active_users,
        )
        if max_tenants is not None and max_tenants < current_tenants:
            raise serializers.ValidationError({
                'max_tenants': 'Le plafond ne peut pas être inférieur aux espaces existants.',
            })
        if max_active_users is not None and max_active_users < current_users:
            raise serializers.ValidationError({
                'max_active_users': (
                    'Le plafond ne peut pas être inférieur aux utilisateurs actifs.'
                ),
            })
        return attrs


class PlatformAdminInvitationSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        value = value.strip()
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Ce nom d’utilisateur est déjà utilisé.')
        return value

    def validate_email(self, value):
        value = User.objects.normalize_email(value.strip())
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Cette adresse e-mail est déjà utilisée.')
        return value


class PublicDemoRequestSerializer(serializers.ModelSerializer):
    consent = serializers.BooleanField(write_only=True)

    class Meta:
        model = PlatformDemoRequest
        fields = [
            'company_name',
            'contact_name',
            'email',
            'phone',
            'message',
            'consent',
        ]

    def validate_company_name(self, value):
        return value.strip()

    def validate_contact_name(self, value):
        return value.strip()

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        return value.strip()

    def validate_message(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Décrivez brièvement votre demande.')
        return value

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError(
                'Votre accord est nécessaire pour être recontacté.',
            )
        return value

    def create(self, validated_data):
        validated_data.pop('consent')
        validated_data['consent_at'] = timezone.now()
        return PlatformDemoRequest.objects.create(**validated_data)


class PlatformDemoRequestStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformDemoRequest
        fields = ['status']


class PlatformTenantDomainSerializer(serializers.ModelSerializer):
    hostname = serializers.RegexField(
        r'^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?$',
        max_length=253,
    )

    class Meta:
        model = TenantDomain
        fields = ['id', 'hostname', 'domain_type', 'verification_status', 'is_primary', 'verified_at', 'created_at']
        read_only_fields = ['id', 'verification_status', 'is_primary', 'verified_at', 'created_at']

    def validate_hostname(self, hostname):
        hostname = hostname.strip().rstrip('.').lower()
        if '.' not in hostname:
            raise serializers.ValidationError(
                'Saisissez un nom de domaine complet.'
            )
        if TenantDomain.objects.filter(hostname__iexact=hostname).exists():
            raise serializers.ValidationError(
                'Ce domaine est déjà enregistré pour une entreprise.'
            )
        return hostname


def issue_domain_challenge(domain):
    token = secrets.token_urlsafe(32)
    domain.verification_status = 'pending'
    domain.verified_at = None
    domain.verification_token_hash = hashlib.sha256(
        token.encode('utf-8')
    ).hexdigest()
    domain.verification_expires_at = timezone.now() + timedelta(days=7)
    domain.save(update_fields=[
        'verification_status',
        'verified_at',
        'verification_token_hash',
        'verification_expires_at',
    ])
    return {
        'recordName': f'_djibexa-challenge.{domain.hostname}',
        'recordType': 'TXT',
        'recordValue': f'djibexa-verification={token}',
        'expiresAt': domain.verification_expires_at,
    }


def verify_domain_dns(domain):
    if (
        not domain.verification_token_hash
        or not domain.verification_expires_at
        or domain.verification_expires_at <= timezone.now()
    ):
        raise ValidationError({
            'detail': 'Le défi DNS a expiré. Générez un nouveau défi.',
        })
    resolver = dns.resolver.Resolver()
    resolver.timeout = 2
    resolver.lifetime = 3
    try:
        answers = resolver.resolve(
            f'_djibexa-challenge.{domain.hostname}',
            'TXT',
            lifetime=3,
        )
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        raise ValidationError({
            'detail': 'Le TXT de vérification est introuvable. Vérifiez le DNS puis réessayez.',
        }) from None
    except (dns.exception.Timeout, dns.resolver.NoNameservers) as error:
        raise DomainDnsUnavailable() from error

    expected_hash = domain.verification_token_hash
    for answer in answers:
        value = b''.join(answer.strings).decode('utf-8', errors='replace')
        prefix = 'djibexa-verification='
        if not value.startswith(prefix):
            continue
        token_hash = hashlib.sha256(value[len(prefix):].encode('utf-8')).hexdigest()
        if secrets.compare_digest(expected_hash, token_hash):
            return True
    raise ValidationError({
        'detail': 'Le TXT de vérification ne correspond pas au défi attendu.',
    })


def tenant_summary(tenant):
    active_users = getattr(tenant, 'platform_active_users', None)
    if active_users is None:
        active_users = tenant.users.filter(
            is_active=True,
            is_platform_admin=False,
        ).count()
    has_users = getattr(tenant, 'platform_has_users', None)
    if has_users is None:
        has_users = tenant.users.filter(is_platform_admin=False).exists()
    return {
        'id': tenant.id,
        'name': tenant.name,
        'slug': tenant.slug,
        'status': tenant.status_at(),
        'trialActivatedAt': tenant.trial_activated_at,
        'trialEndsAt': tenant.trial_ends_at,
        'activeUsers': active_users,
        'maxUsers': tenant.max_users,
        'hasUsers': bool(has_users),
    }


def validate_platform_capacity(max_users):
    platform_settings = PlatformSettings.objects.select_for_update().get(pk=1)
    if (
        platform_settings.max_tenants is not None
        and Tenant.objects.count() >= platform_settings.max_tenants
    ):
        raise ValidationError({
            'detail': 'La limite d’espaces autorisés par la plateforme est atteinte.',
        })
    if (
        platform_settings.max_active_users is not None
        and max_users > platform_settings.max_active_users
    ):
        raise ValidationError({
            'max_users': 'La limite de cet espace dépasse le plafond global utilisateurs.',
        })


def activate_pending_tenant_admins(tenant, actor):
    pending_admins = list(
        tenant.users.select_for_update().filter(
            is_active=False,
            is_platform_admin=False,
            invitation_pending=True,
            must_change_password=True,
        )
    )
    if not pending_admins:
        return None
    if tenant.users.filter(
        is_active=True,
        is_platform_admin=False,
    ).count() + len(pending_admins) > tenant.max_users:
        raise ValidationError({
            'detail': 'La capacité de l’espace ne permet pas d’activer ses comptes en attente.',
        })
    platform_settings = PlatformSettings.objects.select_for_update().get(pk=1)
    if (
        platform_settings.max_active_users is not None
        and User.objects.filter(
            is_active=True,
            is_platform_admin=False,
        ).count() + len(pending_admins) > platform_settings.max_active_users
    ):
        raise ValidationError({
            'detail': 'La limite globale d’utilisateurs actifs ne permet pas cette activation.',
        })
    email_queued = True
    for invited_admin in pending_admins:
        invited_admin.is_active = True
        invited_admin.invitation_pending = False
        invited_admin.save(update_fields=[
            'is_active',
            'invitation_pending',
            'updated_at',
        ])
        send_password_setup_email(invited_admin, tenant, created_by=actor)
    return email_queued


class PlatformTenantCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = PlatformTenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validate_platform_capacity(serializer.validated_data['max_users'])
        tenant = serializer.save(status='pending')
        PlatformAuditLog.objects.create(
            actor=request.user,
            tenant=tenant,
            action='create',
            details={
                'name': tenant.name,
                'slug': tenant.slug,
                'max_users': tenant.max_users,
                'status': tenant.status,
            },
        )
        return Response(
            tenant_summary(tenant),
            status=status.HTTP_201_CREATED,
        )


class PlatformTenantDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def patch(self, request, pk):
        tenant = get_object_or_404(
            Tenant.objects.select_for_update(),
            pk=pk,
        )
        serializer = PlatformTenantCapacitySerializer(
            tenant,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        max_users = serializer.validated_data['max_users']
        active_users = tenant.users.filter(
            is_active=True,
            is_platform_admin=False,
        ).count()
        if max_users < active_users:
            raise ValidationError({
                'max_users': 'Le plafond ne peut pas être inférieur aux utilisateurs actifs.',
            })
        platform_settings = PlatformSettings.objects.get(pk=1)
        if (
            platform_settings.max_active_users is not None
            and max_users > platform_settings.max_active_users
        ):
            raise ValidationError({
                'max_users': 'La limite de cet espace dépasse le plafond global utilisateurs.',
            })
        old_max_users = tenant.max_users
        serializer.save()
        PlatformAuditLog.objects.create(
            actor=request.user,
            tenant=tenant,
            action='update',
            details={
                'field': 'max_users',
                'old_value': old_max_users,
                'new_value': tenant.max_users,
            },
        )
        return Response(tenant_summary(tenant))


class PlatformTenantAdminInvitationView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk):
        tenant = get_object_or_404(
            Tenant.objects.select_for_update(),
            pk=pk,
        )
        PlatformSettings.objects.select_for_update().get(pk=1)
        serializer = PlatformAdminInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if tenant.users.filter(is_platform_admin=False).exists():
            raise ValidationError({
                'detail': 'Un compte existe déjà dans cet espace.',
            })
        if tenant.max_users < 1:
            raise ValidationError({
                'detail': 'La capacité de cet espace ne permet pas de créer un compte.',
            })

        platform_settings = PlatformSettings.objects.get(pk=1)
        if (
            platform_settings.max_active_users is not None
            and User.objects.filter(
                is_active=True,
                is_platform_admin=False,
            ).count() >= platform_settings.max_active_users
        ):
            raise ValidationError({
                'detail': 'La limite globale d’utilisateurs actifs est atteinte.',
            })

        is_active = tenant.status_at() == 'active'
        user = User(
            username=serializer.validated_data['username'],
            email=serializer.validated_data['email'],
            first_name=serializer.validated_data.get('first_name', ''),
            last_name=serializer.validated_data.get('last_name', ''),
            role='admin',
            tenant=tenant,
            is_active=is_active,
            invitation_pending=not is_active,
        )
        user.set_unusable_password()
        user.must_change_password = True
        user.save()
        TenantMembership.objects.create(
            tenant=tenant,
            user=user,
            role='admin',
            is_active=False,
            is_primary_admin=not TenantMembership.objects.filter(
                tenant=tenant,
                is_primary_admin=True,
            ).exists(),
        )
        if is_active:
            send_password_setup_email(user, tenant, created_by=request.user)
        PlatformAuditLog.objects.create(
            actor=request.user,
            tenant=tenant,
            action='invite_admin',
            details={'role': 'admin'},
        )
        return Response(
            {'invited': True, 'emailQueued': is_active},
            status=status.HTTP_201_CREATED,
        )


class PlatformTenantDomainsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk)
        return Response({
            'tenant': tenant_summary(tenant),
            'domains': [
                {
                    'id': domain.id,
                    'hostname': domain.hostname,
                    'domainType': domain.domain_type,
                    'verificationStatus': domain.verification_status,
                    'isPrimary': domain.is_primary,
                    'verifiedAt': domain.verified_at,
                    'createdAt': domain.created_at,
                    'challengeExpiresAt': domain.verification_expires_at,
                }
                for domain in tenant.domains.all()
            ],
        })

    @transaction.atomic
    def post(self, request, pk):
        tenant = get_object_or_404(Tenant.objects.select_for_update(), pk=pk)
        reason = request.data.get('reason', '').strip()
        if not reason or len(reason) > 500:
            raise ValidationError({
                'reason': 'Une justification de 1 à 500 caractères est obligatoire.',
            })
        serializer = PlatformTenantDomainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.save(tenant=tenant)
        challenge = issue_domain_challenge(domain)
        platform_audit(
            request.user,
            'update',
            tenant=tenant,
            request=request,
            entity_type='tenant_domain',
            entity_id=domain.pk,
            new_values={
                'hostname': domain.hostname,
                'verification_status': domain.verification_status,
            },
            reason=reason,
        )
        return Response({
            'domain': {
                'id': domain.id,
                'hostname': domain.hostname,
                'domainType': domain.domain_type,
                'verificationStatus': domain.verification_status,
                'isPrimary': domain.is_primary,
            },
            'challenge': challenge,
        }, status=status.HTTP_201_CREATED)


class PlatformTenantDomainActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk, action):
        domain = get_object_or_404(
            TenantDomain.objects.select_for_update().select_related('tenant'),
            pk=pk,
        )
        tenant = domain.tenant
        reason = request.data.get('reason', '').strip()
        if not reason or len(reason) > 500:
            raise ValidationError({
                'reason': 'Une justification de 1 à 500 caractères est obligatoire.',
            })
        old_values = {
            'verification_status': domain.verification_status,
            'is_primary': domain.is_primary,
        }
        new_values = {}
        challenge = None

        if action == 'verify':
            verify_domain_dns(domain)
            domain.verification_status = 'verified'
            domain.verified_at = timezone.now()
            domain.verification_token_hash = ''
            domain.verification_expires_at = None
            domain.save(update_fields=[
                'verification_status',
                'verified_at',
                'verification_token_hash',
                'verification_expires_at',
            ])
            new_values['verification_status'] = domain.verification_status
        elif action == 'renew-challenge':
            if domain.verification_status == 'verified':
                raise ValidationError({
                    'action': 'Un domaine déjà vérifié ne nécessite pas de défi.',
                })
            challenge = issue_domain_challenge(domain)
            new_values['verification_status'] = domain.verification_status
        elif action == 'set-primary':
            if domain.verification_status != 'verified':
                raise ValidationError({
                    'action': 'Vérifiez le domaine avant de le définir comme principal.',
                })
            TenantDomain.objects.filter(tenant=tenant, is_primary=True).update(
                is_primary=False
            )
            domain.is_primary = True
            domain.save(update_fields=['is_primary'])
            new_values['is_primary'] = True
        elif action == 'remove':
            if domain.is_primary:
                raise ValidationError({
                    'action': 'Retirez d’abord le domaine principal avant de le supprimer.',
                })
            domain.delete()
            new_values = {'removed': True}
        else:
            raise ValidationError({'action': 'Action de domaine inconnue.'})

        platform_audit(
            request.user,
            'update',
            tenant=tenant,
            request=request,
            entity_type='tenant_domain',
            entity_id=domain.pk,
            old_values=old_values,
            new_values=new_values,
            reason=reason,
        )
        response_data = {
            'domain': {
                'id': domain.pk,
                'hostname': domain.hostname,
                'domainType': domain.domain_type,
                'verificationStatus': domain.verification_status,
                'isPrimary': domain.is_primary,
                'verifiedAt': domain.verified_at,
            },
        }
        if challenge:
            response_data['challenge'] = challenge
        return Response(response_data)


class PlatformTenantActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk, action):
        tenant = get_object_or_404(Tenant.objects.select_for_update(), pk=pk)
        now = timezone.now()
        invitation_email_queued = None
        if action == 'activate':
            if tenant.status != 'pending':
                raise ValidationError({
                    'detail': 'Seul un espace en attente peut démarrer son essai.',
                })
            audit_action = 'activate'
            try:
                tenant.activate_trial(activated_at=now)
            except DjangoValidationError as error:
                raise ValidationError({'detail': error.messages}) from error
            invitation_email_queued = activate_pending_tenant_admins(tenant, request.user)
        elif action == 'suspend':
            if tenant.status != 'active':
                raise ValidationError({
                    'detail': 'Seul un espace actif peut être suspendu.',
                })
            tenant.status = 'suspended'
            tenant.save(update_fields=['status', 'updated_at'])
            audit_action = 'suspend'
        elif action == 'resume':
            if (
                tenant.status != 'suspended'
                or tenant.trial_ends_at is None
                or tenant.trial_ends_at <= now
            ):
                raise ValidationError({
                    'detail': 'Cet espace ne peut pas être réactivé sans prolongation de licence.',
                })
            tenant.status = 'active'
            tenant.save(update_fields=['status', 'updated_at'])
            invitation_email_queued = activate_pending_tenant_admins(tenant, request.user)
            audit_action = 'resume'
        elif action in {'archive', 'restore', 'request-deletion'}:
            reason = request.data.get('reason', '').strip()
            if not reason or len(reason) > 500:
                raise ValidationError({
                    'reason': 'Une justification de 1 à 500 caractères est obligatoire.',
                })
            old_status = tenant.status
            if action == 'archive' and tenant.status != 'archived':
                tenant.status = 'archived'
                tenant.archived_at = now
            elif action == 'restore' and tenant.status == 'archived':
                tenant.status = 'suspended'
                tenant.archived_at = None
            elif action == 'request-deletion' and tenant.status != 'deletion_pending':
                tenant.status = 'deletion_pending'
            else:
                raise ValidationError({
                    'action': 'Transition de cycle de vie invalide.',
                })
            tenant.save(update_fields=['status', 'archived_at', 'updated_at'])
            platform_audit(
                request.user,
                'update',
                tenant=tenant,
                request=request,
                entity_type='tenant',
                entity_id=tenant.pk,
                old_values={'status': old_status},
                new_values={'status': tenant.status},
                reason=reason,
                details={'lifecycle_action': action},
            )
            return Response(tenant_summary(tenant))
        else:
            raise ValidationError({'action': 'Action de plateforme inconnue.'})

        PlatformAuditLog.objects.create(
            actor=request.user,
            tenant=tenant,
            action=audit_action,
            details={
                'status': tenant.status_at(),
                'trial_ends_at': (
                    tenant.trial_ends_at.isoformat()
                    if tenant.trial_ends_at
                    else None
                ),
            },
        )
        response_data = tenant_summary(tenant)
        if invitation_email_queued is not None:
            response_data['invitationEmailQueued'] = invitation_email_queued
        return Response(response_data)


def platform_plan_data(plan):
    return {
        'id': plan.id,
        'code': plan.code,
        'name': plan.name,
        'description': plan.description,
        'price': str(plan.price),
        'currency': plan.currency,
        'billingPeriod': plan.billing_period,
        'durationMonths': plan.duration_months,
        'maxUsers': plan.max_users,
        'modules': list(plan.modules.values_list('code', flat=True)),
        'isActive': plan.is_active,
    }


def platform_subscription_data(subscription):
    return {
        'id': subscription.id,
        'tenantId': subscription.tenant_id,
        'tenantName': subscription.tenant.name,
        'planId': subscription.plan_id,
        'planName': subscription.plan.name,
        'status': subscription.status,
        'amount': str(subscription.amount),
        'currency': subscription.currency,
        'durationMonths': subscription.duration_months,
        'maxUsers': subscription.max_users,
        'modules': subscription.included_modules,
        'startsAt': subscription.starts_at,
        'endsAt': subscription.ends_at,
        'createdAt': subscription.created_at,
    }


def platform_payment_data(payment):
    return {
        'id': payment.id,
        'tenantId': payment.tenant_id,
        'tenantName': payment.tenant.name,
        'subscriptionId': payment.subscription_id,
        'planName': payment.subscription.plan.name,
        'amount': str(payment.amount),
        'currency': payment.currency,
        'method': payment.method,
        'reference': payment.reference,
        'paidAt': payment.paid_at,
        'status': payment.status,
        'notes': payment.notes,
        'recordedBy': payment.recorded_by.get_username(),
        'reviewedBy': (
            payment.reviewed_by.get_username()
            if payment.reviewed_by_id
            else None
        ),
        'reviewedAt': payment.reviewed_at,
        'invoiceNumber': (
            payment.payment_record.invoice.invoice_number
            if payment.payment_record_id
            else None
        ),
    }


def platform_invoice_data(invoice):
    return {
        'id': invoice.id,
        'tenantId': invoice.tenant_id,
        'tenantName': invoice.tenant.name,
        'subscriptionId': invoice.subscription_id,
        'invoiceNumber': invoice.invoice_number,
        'amount': str(invoice.amount),
        'currency': invoice.currency,
        'issueDate': invoice.issue_date,
        'dueDate': invoice.due_date,
        'status': invoice.status,
        'description': invoice.description,
    }


def platform_module_data(module):
    return {
        'id': module.id,
        'code': module.code,
        'name': module.name,
        'description': module.description,
        'dependencies': module.dependencies,
        'technicalStatus': module.technical_status,
        'sortOrder': module.sort_order,
        'isActive': module.is_active,
    }


def tenant_module_data(tenant, module):
    from .platform_entitlements import evaluate_tenant_module

    override = tenant.module_overrides.filter(module=module).first()
    access = evaluate_tenant_module(tenant, module.code)
    return {
        **platform_module_data(module),
        'status': override.status if override else 'inherit',
        'note': override.note if override else '',
        **access,
    }


def sync_plan_feature_versions(plan):
    selected_ids = set(plan.modules.values_list('pk', flat=True))
    for feature in PlatformModule.objects.all():
        latest = PlanFeature.objects.filter(
            plan=plan,
            feature=feature,
        ).order_by('-version').first()
        enabled = feature.pk in selected_ids
        limits = latest.limits if latest else {}
        if latest and latest.enabled == enabled:
            continue
        PlanFeature.objects.create(
            plan=plan,
            feature=feature,
            version=(latest.version + 1) if latest else 1,
            enabled=enabled,
            limits=limits,
        )


def plan_feature_snapshot(plan):
    snapshot = {}
    versions = set()
    for feature in plan.feature_versions.select_related('feature').order_by(
        'feature_id',
        '-version',
    ):
        if feature.feature.code in versions:
            continue
        versions.add(feature.feature.code)
        snapshot[feature.feature.code] = {
            'enabled': feature.enabled,
            'limits': feature.limits,
            'version': feature.version,
        }
    if not snapshot:
        snapshot = {
            code: {'enabled': True, 'limits': {}, 'version': 0}
            for code in plan.modules.values_list('code', flat=True)
        }
    return snapshot


def platform_audit(
    actor,
    action,
    tenant=None,
    details=None,
    *,
    request=None,
    entity_type='',
    entity_id='',
    old_values=None,
    new_values=None,
    reason='',
):
    forwarded_for = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',', 1)[0].strip()
        if request
        else ''
    )
    ip_address = (
        forwarded_for
        or (request.META.get('REMOTE_ADDR') if request else None)
    )
    return PlatformAuditLog.objects.create(
        actor=actor,
        tenant=tenant,
        action=action,
        details=details or {},
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else '',
        old_values=old_values or {},
        new_values=new_values or {},
        reason=reason,
        ip_address=ip_address or None,
        user_agent=(
            request.META.get('HTTP_USER_AGENT', '')[:500]
            if request
            else ''
        ),
    )


def start_platform_subscription(subscription, now=None):
    now = now or timezone.now()
    start = subscription.ends_at if (
        subscription.status == 'active'
        and subscription.ends_at
        and subscription.ends_at > now
    ) else now
    subscription.status = 'active'
    subscription.starts_at = subscription.starts_at or now
    subscription.ends_at = add_calendar_months(start, subscription.duration_months)
    subscription.save(update_fields=['status', 'starts_at', 'ends_at', 'updated_at'])

    tenant = Tenant.objects.select_for_update().get(pk=subscription.tenant_id)
    active_users = tenant.users.filter(
        is_active=True,
        is_platform_admin=False,
    ).count()
    if subscription.max_users < active_users:
        raise ValidationError({
            'detail': 'Le plafond de l’offre est inférieur aux utilisateurs actifs de l’espace.',
        })
    tenant.status = 'active'
    tenant.trial_activated_at = tenant.trial_activated_at or now
    tenant.trial_ends_at = subscription.ends_at
    tenant.max_users = subscription.max_users
    tenant.save(update_fields=[
        'status',
        'trial_activated_at',
        'trial_ends_at',
        'max_users',
        'updated_at',
    ])
    activate_pending_tenant_admins(tenant, subscription.created_by)
    return tenant


def create_billing_invoice(subscription):
    invoice_number = (
        f'DJX-{subscription.tenant_id:06d}-'
        f'{subscription.pk:06d}-'
        f'{subscription.billing_invoices.count() + 1:02d}'
    )
    return BillingInvoice.objects.create(
        tenant=subscription.tenant,
        subscription=subscription,
        invoice_number=invoice_number,
        amount=subscription.amount,
        currency=subscription.currency,
        status='paid' if subscription.amount == 0 else 'open',
        description=(
            f'Abonnement {subscription.plan.name} — '
            f'{subscription.duration_months} mois'
        ),
    )


def open_invoice_for_payment(subscription):
    invoice = BillingInvoice.objects.select_for_update().filter(
        subscription=subscription,
        status='open',
    ).order_by('created_at', 'pk').first()
    return invoice or create_billing_invoice(subscription)


def validate_override_dependencies(tenant, module, status):
    if status != 'enabled':
        return
    from .platform_entitlements import tenant_module_is_enabled

    for dependency in module.dependencies:
        if not tenant_module_is_enabled(tenant, dependency):
            raise ValidationError({
                'module_code': (
                    f'Activez d’abord le module requis « {dependency} ».'
                ),
            })


class PlatformPlansView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        return Response({
            'plans': [
                platform_plan_data(plan)
                for plan in PlatformPlan.objects.prefetch_related('modules')
            ],
            'modules': [
                platform_module_data(module)
                for module in PlatformModule.objects.filter(is_active=True)
            ],
        })

    @transaction.atomic
    def post(self, request):
        serializer = PlatformPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        sync_plan_feature_versions(plan)
        platform_audit(
            request.user,
            'plan_create',
            details={
                'plan_id': plan.pk,
                'name': plan.name,
                'price': str(plan.price),
                'currency': plan.currency,
            },
        )
        return Response(platform_plan_data(plan), status=status.HTTP_201_CREATED)


class PlatformPlanDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def patch(self, request, pk):
        plan = get_object_or_404(PlatformPlan.objects.select_for_update(), pk=pk)
        old_data = platform_plan_data(plan)
        serializer = PlatformPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        sync_plan_feature_versions(plan)
        platform_audit(
            request.user,
            'plan_update',
            details={
                'plan_id': plan.pk,
                'old_price': old_data['price'],
                'new_price': str(plan.price),
                'old_duration_months': old_data['durationMonths'],
                'new_duration_months': plan.duration_months,
            },
        )
        return Response(platform_plan_data(plan))


class PlatformSubscriptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        queryset = TenantSubscription.objects.select_related(
            'tenant',
            'plan',
        )
        tenant_id = request.query_params.get('tenant')
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        return Response({
            'subscriptions': [
                platform_subscription_data(subscription)
                for subscription in queryset
            ],
            'tenants': [
                tenant_summary(tenant)
                for tenant in Tenant.objects.all()
            ],
            'plans': [
                platform_plan_data(plan)
                for plan in PlatformPlan.objects.filter(is_active=True).prefetch_related('modules')
            ],
        })

    @transaction.atomic
    def post(self, request):
        serializer = PlatformSubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = get_object_or_404(
            Tenant.objects.select_for_update(),
            pk=serializer.validated_data['tenant_id'],
        )
        plan = serializer.validated_data['plan_id']
        active_users = tenant.users.filter(
            is_active=True,
            is_platform_admin=False,
        ).count()
        if plan.max_users < active_users:
            raise ValidationError({
                'plan_id': 'Le plafond de l’offre est inférieur aux utilisateurs actifs.',
            })

        current_subscriptions = TenantSubscription.objects.select_for_update().filter(
            tenant=tenant,
            status__in=['pending', 'active', 'suspended'],
        )
        for current in current_subscriptions:
            current.status = 'cancelled'
            current.save(update_fields=['status', 'updated_at'])
            platform_audit(
                request.user,
                'subscription_cancel',
                tenant=tenant,
                details={'subscription_id': current.pk, 'reason': 'replaced'},
            )

        subscription = TenantSubscription.objects.create(
            tenant=tenant,
            plan=plan,
            status='pending',
            amount=plan.price,
            currency=plan.currency,
            duration_months=plan.duration_months,
            max_users=plan.max_users,
            included_modules=[
                code
                for code, feature in plan_feature_snapshot(plan).items()
                if feature['enabled']
            ],
            feature_snapshot=plan_feature_snapshot(plan),
            created_by=request.user,
        )
        create_billing_invoice(subscription)
        if plan.price == 0:
            tenant = start_platform_subscription(subscription)
        elif tenant.status == 'active':
            tenant.status = 'suspended'
            tenant.save(update_fields=['status', 'updated_at'])
        platform_audit(
            request.user,
            'subscription_assign',
            tenant=tenant,
            details={
                'subscription_id': subscription.pk,
                'plan_id': plan.pk,
                'plan_name': plan.name,
                'status': subscription.status,
            },
        )
        return Response(
            platform_subscription_data(subscription),
            status=status.HTTP_201_CREATED,
        )


class PlatformSubscriptionActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk, action):
        subscription = get_object_or_404(
            TenantSubscription.objects.select_for_update().select_related('tenant', 'plan'),
            pk=pk,
        )
        now = timezone.now()
        if action == 'suspend' and subscription.status == 'active':
            subscription.status = 'suspended'
            subscription.tenant.status = 'suspended'
            subscription.tenant.save(update_fields=['status', 'updated_at'])
            audit_action = 'suspend'
        elif action == 'resume' and (
            subscription.status == 'suspended'
            and subscription.ends_at
            and subscription.ends_at > now
        ):
            subscription.status = 'active'
            subscription.tenant.status = 'active'
            subscription.tenant.save(update_fields=['status', 'updated_at'])
            audit_action = 'resume'
        elif action == 'cancel' and subscription.status in {'pending', 'active', 'suspended'}:
            subscription.status = 'cancelled'
            subscription.tenant.status = 'suspended'
            subscription.tenant.save(update_fields=['status', 'updated_at'])
            audit_action = 'subscription_cancel'
        else:
            raise ValidationError({'action': 'Transition d’abonnement invalide.'})
        subscription.save(update_fields=['status', 'updated_at'])
        platform_audit(
            request.user,
            audit_action,
            tenant=subscription.tenant,
            details={
                'subscription_id': subscription.pk,
                'status': subscription.status,
            },
        )
        return Response(platform_subscription_data(subscription))


class PlatformPaymentsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        queryset = PlatformPayment.objects.select_related(
            'tenant',
            'subscription__plan',
            'recorded_by',
            'reviewed_by',
            'payment_record__invoice',
        )
        payment_status = request.query_params.get('status', '').strip()
        if payment_status:
            queryset = queryset.filter(status=payment_status)
        return Response({
            'payments': [platform_payment_data(payment) for payment in queryset],
            'invoices': [
                platform_invoice_data(invoice)
                for invoice in BillingInvoice.objects.select_related('tenant').all()[:100]
            ],
            'subscriptions': [
                platform_subscription_data(subscription)
                for subscription in TenantSubscription.objects.filter(
                    status__in=['pending', 'active'],
                ).select_related('tenant', 'plan')
            ],
        })

    @transaction.atomic
    def post(self, request):
        serializer = PlatformPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription = serializer.validated_data['subscription']
        invoice = open_invoice_for_payment(subscription)
        received_at = timezone.make_aware(datetime.combine(
            serializer.validated_data['paid_at'],
            datetime.min.time(),
        ))
        payment_record = PaymentRecord.objects.create(
            tenant=subscription.tenant,
            invoice=invoice,
            amount=serializer.validated_data['amount'],
            currency=subscription.currency,
            payment_method=serializer.validated_data['method'],
            payment_reference=serializer.validated_data.get('reference', ''),
            received_at=received_at,
            proof_file=getattr(serializer, 'proof_file', None),
            recorded_by=request.user,
            notes=serializer.validated_data.get('notes', ''),
        )
        payment = serializer.save(
            tenant=subscription.tenant,
            recorded_by=request.user,
            payment_record=payment_record,
        )
        platform_audit(
            request.user,
            'payment_record',
            tenant=payment.tenant,
            details={
                'payment_id': payment.pk,
                'subscription_id': subscription.pk,
                'amount': str(payment.amount),
                'currency': payment.currency,
                'status': payment.status,
            },
        )
        return Response(platform_payment_data(payment), status=status.HTTP_201_CREATED)


class PlatformPaymentActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk, action):
        payment = get_object_or_404(
            PlatformPayment.objects.select_for_update().select_related(
                'tenant',
                'subscription__plan',
                'recorded_by',
            ),
            pk=pk,
        )
        if payment.status != 'pending' or action not in {'confirm', 'reject'}:
            raise ValidationError({'action': 'Transition de paiement invalide.'})
        payment_record = None
        if payment.payment_record_id:
            payment_record = PaymentRecord.objects.select_for_update().select_related(
                'invoice'
            ).get(pk=payment.payment_record_id)
        payment.status = 'confirmed' if action == 'confirm' else 'rejected'
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        if action == 'confirm':
            if payment.subscription.status not in {'pending', 'active'}:
                raise ValidationError({
                    'detail': 'L’abonnement associé ne peut pas être activé.',
                })
            if (
                payment_record
                and payment_record.invoice.status == 'paid'
            ):
                raise ValidationError({
                    'detail': 'Cette facture est déjà réglée.',
                })
            was_active_subscription = payment.subscription.status == 'active'
            tenant = start_platform_subscription(payment.subscription)
            if payment_record:
                payment_record.status = 'confirmed'
                payment_record.verified_by = request.user
                payment_record.save(update_fields=['status', 'verified_by'])
                invoice = payment_record.invoice
                invoice.status = 'paid'
                invoice.save(update_fields=['status'])
            audit_action = 'payment_confirm'
            details = {
                'payment_id': payment.pk,
                'subscription_id': payment.subscription_id,
                'amount': str(payment.amount),
                'currency': payment.currency,
                'ends_at': payment.subscription.ends_at.isoformat(),
            }
            if was_active_subscription:
                platform_audit(
                    request.user,
                    'resume',
                    tenant=tenant,
                    details={
                        'status': tenant.status_at(),
                        'trial_ends_at': tenant.trial_ends_at.isoformat(),
                    },
                )
        else:
            if payment_record:
                payment_record.status = 'rejected'
                payment_record.verified_by = request.user
                payment_record.save(update_fields=['status', 'verified_by'])
            audit_action = 'payment_reject'
            details = {
                'payment_id': payment.pk,
                'subscription_id': payment.subscription_id,
                'amount': str(payment.amount),
                'currency': payment.currency,
            }
        payment.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        platform_audit(
            request.user,
            audit_action,
            tenant=payment.tenant,
            details=details,
        )
        return Response(platform_payment_data(payment))


class PlatformModulesView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        return Response([
            platform_module_data(module)
            for module in PlatformModule.objects.all()
        ])

    @transaction.atomic
    def post(self, request):
        serializer = PlatformModuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        module = serializer.save()
        platform_audit(
            request.user,
            'module_override',
            details={'module_code': module.code, 'action': 'catalog_create'},
        )
        return Response(platform_module_data(module), status=status.HTTP_201_CREATED)


class PlatformModuleDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def patch(self, request, pk):
        module = get_object_or_404(PlatformModule.objects.select_for_update(), pk=pk)
        serializer = PlatformModuleSerializer(module, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        module = serializer.save()
        platform_audit(
            request.user,
            'module_override',
            details={'module_code': module.code, 'action': 'catalog_update'},
        )
        return Response(platform_module_data(module))


class PlatformTenantModulesView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk)
        return Response({
            'tenant': tenant_summary(tenant),
            'modules': [
                tenant_module_data(tenant, module)
                for module in PlatformModule.objects.filter(is_active=True)
            ],
        })

    @transaction.atomic
    def patch(self, request, pk):
        tenant = get_object_or_404(Tenant.objects.select_for_update(), pk=pk)
        serializer = TenantModuleOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        module = serializer.validated_data['module']
        override_status = serializer.validated_data['status']
        validate_override_dependencies(tenant, module, override_status)
        if override_status == 'inherit':
            TenantModuleOverride.objects.filter(tenant=tenant, module=module).delete()
        else:
            TenantModuleOverride.objects.update_or_create(
                tenant=tenant,
                module=module,
                defaults={
                    'status': override_status,
                    'note': serializer.validated_data.get('note', ''),
                    'updated_by': request.user,
                },
            )
        platform_audit(
            request.user,
            'module_override',
            tenant=tenant,
            details={
                'module_code': module.code,
                'status': override_status,
                'note': serializer.validated_data.get('note', ''),
            },
        )
        return Response({
            'tenant': tenant_summary(tenant),
            'modules': [
                tenant_module_data(tenant, item)
                for item in PlatformModule.objects.filter(is_active=True)
            ],
        })


def platform_user_data(user):
    return {
        'id': user.id,
        'username': user.get_username(),
        'name': user.get_full_name() or user.get_username(),
        'email': user.email,
        'role': user.role,
        'isActive': user.is_active,
        'invitationPending': user.invitation_pending,
        'failedLoginAttempts': user.failed_login_attempts,
        'lockedUntil': user.locked_until,
        'lastLogin': user.last_login,
        'createdAt': user.created_at,
        'tenantId': user.tenant_id,
        'tenantName': user.tenant.name if user.tenant_id else None,
    }


class PlatformUsersView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        queryset = User.objects.filter(
            is_platform_admin=False,
            tenant__isnull=False,
        ).select_related('tenant')
        tenant_id = request.query_params.get('tenant', '').strip()
        if tenant_id:
            if not tenant_id.isdecimal():
                raise ValidationError({'tenant': 'Identifiant d’espace invalide.'})
            queryset = queryset.filter(tenant_id=int(tenant_id))

        user_status = request.query_params.get('status', '').strip()
        if user_status == 'active':
            queryset = queryset.filter(is_active=True)
        elif user_status == 'inactive':
            queryset = queryset.filter(is_active=False, invitation_pending=False)
        elif user_status == 'invitation_pending':
            queryset = queryset.filter(invitation_pending=True)
        elif user_status == 'locked':
            queryset = queryset.filter(locked_until__gt=timezone.now())
        elif user_status:
            raise ValidationError({'status': 'Filtre d’état invalide.'})

        search = request.query_params.get('search', '').strip()[:120]
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(tenant__name__icontains=search)
                | Q(tenant__slug__icontains=search)
            )

        paginator = VersionedApiPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([
            platform_user_data(user)
            for user in page
        ])


class PlatformUserActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk, action):
        if action not in {'unlock', 'deactivate', 'activate', 'send-setup-link'}:
            raise ValidationError({'action': 'Action utilisateur inconnue.'})

        with transaction.atomic():
            user = get_object_or_404(
                User.objects.select_for_update().select_related('tenant'),
                pk=pk,
                is_platform_admin=False,
                tenant__isnull=False,
            )
            tenant = Tenant.objects.select_for_update().get(pk=user.tenant_id)
            now = timezone.now()
            details = {'user_id': user.pk, 'username': user.get_username()}

            if action == 'unlock':
                if not user.locked_until or user.locked_until <= now:
                    raise ValidationError({
                        'action': 'Ce compte ne fait pas actuellement l’objet d’un verrouillage.',
                    })
                user.failed_login_attempts = 0
                user.locked_until = None
                user.save(update_fields=[
                    'failed_login_attempts',
                    'locked_until',
                    'updated_at',
                ])
                details['action'] = 'unlock'
            elif action == 'deactivate':
                if not user.is_active:
                    raise ValidationError({'action': 'Ce compte est déjà désactivé.'})
                if user.role == 'admin' and tenant.users.filter(
                    is_active=True,
                    is_platform_admin=False,
                    role='admin',
                ).count() <= 1:
                    raise ValidationError({
                        'action': 'Le dernier administrateur actif de l’espace ne peut pas être désactivé.',
                    })
                user.is_active = False
                user.save(update_fields=['is_active', 'updated_at'])
                TenantMembership.objects.filter(
                    tenant=tenant,
                    user=user,
                ).update(is_active=False)
                details['action'] = 'deactivate'
            elif action == 'activate':
                if user.is_active:
                    raise ValidationError({'action': 'Ce compte est déjà actif.'})
                if tenant.status_at() != 'active':
                    raise ValidationError({
                        'action': 'Activez d’abord l’espace de cette entreprise.',
                    })
                if tenant.users.filter(
                    is_active=True,
                    is_platform_admin=False,
                ).count() >= tenant.max_users:
                    raise ValidationError({
                        'action': 'La capacité de l’espace est atteinte.',
                    })
                platform_settings = PlatformSettings.objects.select_for_update().get(pk=1)
                if platform_settings.max_active_users is not None and User.objects.filter(
                    is_active=True,
                    is_platform_admin=False,
                ).count() >= platform_settings.max_active_users:
                    raise ValidationError({
                        'action': 'La limite globale d’utilisateurs actifs est atteinte.',
                    })
                user.is_active = True
                user.invitation_pending = False
                user.save(update_fields=[
                    'is_active',
                    'invitation_pending',
                    'updated_at',
                ])
                TenantMembership.objects.filter(
                    tenant=tenant,
                    user=user,
                ).update(is_active=True)
                details['action'] = 'activate_user'
            else:
                if not user.is_active or tenant.status_at() != 'active':
                    raise ValidationError({
                        'action': 'Le compte et son espace doivent être actifs.',
                    })
                send_password_setup_email(user, tenant, created_by=request.user)
                TenantMembership.objects.filter(
                    tenant=tenant,
                    user=user,
                ).update(is_active=False)
                details['action'] = 'send_setup_link'

            platform_audit(
                request.user,
                'user_access',
                tenant=tenant,
                details=details,
            )
            return Response(platform_user_data(user))


class PlatformSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        platform_settings = PlatformSettings.objects.get(pk=1)
        return Response({
            'maxTenants': platform_settings.max_tenants,
            'maxActiveUsers': platform_settings.max_active_users,
            'tenantCount': Tenant.objects.count(),
            'activeUserCount': User.objects.filter(
                is_active=True,
                is_platform_admin=False,
            ).count(),
            'updatedAt': platform_settings.updated_at,
        })

    @transaction.atomic
    def patch(self, request):
        platform_settings = PlatformSettings.objects.select_for_update().get(pk=1)
        old_values = {
            'max_tenants': platform_settings.max_tenants,
            'max_active_users': platform_settings.max_active_users,
        }
        serializer = PlatformSettingsSerializer(
            platform_settings,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        platform_settings = serializer.save()
        new_values = {
            'max_tenants': platform_settings.max_tenants,
            'max_active_users': platform_settings.max_active_users,
        }
        platform_audit(
            request.user,
            'settings_update',
            details={
                'old_max_tenants': old_values['max_tenants'],
                'new_max_tenants': new_values['max_tenants'],
                'old_max_active_users': old_values['max_active_users'],
                'new_max_active_users': new_values['max_active_users'],
            },
        )
        return self.get(request)


class PlatformReportsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        now = timezone.now()
        tenants = list(
            Tenant.objects.only(
                'id',
                'status',
                'trial_ends_at',
                'enabled_modules',
            ),
        )
        tenant_statuses = [tenant.status_at(now) for tenant in tenants]
        subscriptions = TenantSubscription.objects.all()
        subscription_statuses = {
            item['status']: item['count']
            for item in subscriptions.values('status').annotate(count=Count('id'))
        }
        confirmed_payments = (
            PlatformPayment.objects.filter(status='confirmed')
            .values('currency')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('currency')
        )
        modules = list(PlatformModule.objects.filter(is_active=True))
        module_by_code = {module.code: module for module in modules}
        active_subscriptions = {
            subscription.tenant_id: subscription
            for subscription in subscriptions.filter(status='active').only(
                'tenant_id',
                'ends_at',
                'included_modules',
            )
        }
        overrides = {
            (override.tenant_id, override.module.code): override.status
            for override in TenantModuleOverride.objects.filter(
                tenant_id__in=[tenant.id for tenant in tenants],
            ).select_related('module')
        }
        active_tenants = [
            tenant
            for tenant in tenants
            if tenant.status_at(now) == 'active'
        ]

        def has_module_access(tenant, code, ancestors=None):
            if code in (ancestors or set()):
                return False
            module = module_by_code.get(code)
            if module is None:
                return False
            override = overrides.get((tenant.id, code))
            subscription = active_subscriptions.get(tenant.id)
            if override is not None:
                granted = override == 'enabled'
            elif subscription is not None:
                granted = bool(
                    subscription.ends_at
                    and subscription.ends_at > now
                    and code in subscription.included_modules
                )
            elif tenant.enabled_modules:
                granted = code in tenant.enabled_modules
            else:
                granted = True
            if not granted:
                return False
            return all(
                has_module_access(tenant, dependency, (ancestors or set()) | {code})
                for dependency in module.dependencies
            )

        module_counts = {
            module.code: sum(
                has_module_access(tenant, module.code)
                for tenant in active_tenants
            )
            for module in modules
        }
        return Response({
            'generatedAt': now,
            'tenants': {
                'total': len(tenants),
                'active': tenant_statuses.count('active'),
                'pending': tenant_statuses.count('pending'),
                'suspended': tenant_statuses.count('suspended'),
                'expired': tenant_statuses.count('expired'),
            },
            'subscriptions': {
                'total': subscriptions.count(),
                'byStatus': subscription_statuses,
            },
            'confirmedPayments': [
                {
                    'currency': item['currency'],
                    'total': format(item['total'].quantize(Decimal('0.01')), 'f'),
                    'count': item['count'],
                }
                for item in confirmed_payments
            ],
            'moduleAdoption': [
                {
                    'code': module.code,
                    'name': module.name,
                    'tenantCount': module_counts.get(module.code, 0),
                }
                for module in modules
            ],
        })


def platform_audit_details(entry):
    detail_types = {
        'create': {
            'name': str,
            'slug': str,
            'max_users': int,
            'status': str,
        },
        'update': {
            'field': str,
            'old_value': int,
            'new_value': int,
        },
        'activate': {
            'status': str,
            'trial_ends_at': str,
        },
        'suspend': {
            'status': str,
            'trial_ends_at': str,
        },
        'resume': {
            'status': str,
            'trial_ends_at': str,
        },
        'invite_admin': {
            'role': str,
        },
        'plan_create': {
            'plan_id': int,
            'name': str,
            'price': str,
            'currency': str,
        },
        'plan_update': {
            'plan_id': int,
            'old_price': str,
            'new_price': str,
            'old_duration_months': int,
            'new_duration_months': int,
        },
        'subscription_assign': {
            'subscription_id': int,
            'plan_id': int,
            'plan_name': str,
            'status': str,
        },
        'subscription_cancel': {
            'subscription_id': int,
            'reason': str,
            'status': str,
        },
        'payment_record': {
            'payment_id': int,
            'subscription_id': int,
            'amount': str,
            'currency': str,
            'status': str,
        },
        'payment_confirm': {
            'payment_id': int,
            'subscription_id': int,
            'amount': str,
            'currency': str,
            'ends_at': str,
        },
        'payment_reject': {
            'payment_id': int,
            'subscription_id': int,
            'amount': str,
            'currency': str,
        },
        'module_override': {
            'module_code': str,
            'status': str,
            'note': str,
            'action': str,
        },
        'user_access': {
            'user_id': int,
            'username': str,
            'action': str,
        },
        'settings_update': {
            'old_max_tenants': int,
            'new_max_tenants': int,
            'old_max_active_users': int,
            'new_max_active_users': int,
        },
    }
    allowed_types = detail_types.get(entry.action, {})
    if not isinstance(entry.details, dict):
        return {}
    safe_details = {}
    for key, expected_type in allowed_types.items():
        if key not in entry.details:
            continue
        value = entry.details[key]
        if key == 'trial_ends_at' and value is None:
            safe_details[key] = None
        elif key in {
            'old_max_tenants',
            'new_max_tenants',
            'old_max_active_users',
            'new_max_active_users',
        } and value is None:
            safe_details[key] = None
        elif isinstance(value, expected_type) and not isinstance(value, bool):
            safe_details[key] = value
    return safe_details


class PlatformAuditLogListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        queryset = PlatformAuditLog.objects.select_related(
            'actor',
            'tenant',
        )
        action = request.query_params.get('action', '').strip()
        if action:
            allowed_actions = {
                value for value, _label in PlatformAuditLog.ACTION_CHOICES
            }
            if action not in allowed_actions:
                raise ValidationError({'action': 'Filtre d’action invalide.'})
            queryset = queryset.filter(action=action)

        search = request.query_params.get('search', '').strip()[:120]
        if search:
            queryset = queryset.filter(
                Q(actor__username__icontains=search)
                | Q(tenant__name__icontains=search)
                | Q(tenant__slug__icontains=search)
            )

        paginator = VersionedApiPagination()
        page = paginator.paginate_queryset(
            queryset.order_by('-created_at', '-id'),
            request,
            view=self,
        )
        entries = [
            {
                'id': entry.id,
                'actor': entry.actor.get_username(),
                'tenant': (
                    entry.tenant.name
                    if entry.tenant_id and entry.tenant
                    else None
                ),
                'action': entry.action,
                'details': platform_audit_details(entry),
                'createdAt': entry.created_at,
            }
            for entry in page
        ]
        return paginator.get_paginated_response(entries)


class PublicDemoRequestThrottle(AnonRateThrottle):
    scope = 'demo_request'


class PublicDemoRequestCreateView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicDemoRequestThrottle]

    def post(self, request):
        serializer = PublicDemoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        demo_request = serializer.save()
        return Response(
            {'id': demo_request.id, 'createdAt': demo_request.created_at},
            status=status.HTTP_201_CREATED,
        )


class PlatformDemoRequestListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'platform_admin'

    def get(self, request):
        queryset = PlatformDemoRequest.objects.all()
        request_status = request.query_params.get('status', '').strip()
        if request_status:
            if request_status not in dict(PlatformDemoRequest.STATUS_CHOICES):
                raise ValidationError({'status': 'Filtre d’état invalide.'})
            queryset = queryset.filter(status=request_status)

        search = request.query_params.get('search', '').strip()[:120]
        if search:
            queryset = queryset.filter(
                Q(company_name__icontains=search)
                | Q(contact_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )

        paginator = VersionedApiPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        results = [
            {
                'id': item.id,
                'companyName': item.company_name,
                'contactName': item.contact_name,
                'email': item.email,
                'phone': item.phone,
                'message': item.message,
                'status': item.status,
                'createdAt': item.created_at,
                'updatedAt': item.updated_at,
            }
            for item in page
        ]
        return paginator.get_paginated_response(results)


class PlatformDemoRequestDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'platform_admin'

    def patch(self, request, pk):
        demo_request = get_object_or_404(PlatformDemoRequest, pk=pk)
        serializer = PlatformDemoRequestStatusSerializer(
            demo_request,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'id': demo_request.id, 'status': demo_request.status})


class PlatformMonitoringView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        database_status = 'operational'
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except DatabaseError:
            logger.exception('Platform monitoring could not check the database.')
            database_status = 'unavailable'

        try:
            disk = shutil.disk_usage(settings.BASE_DIR)
            storage = {
                'status': 'operational',
                'totalBytes': disk.total,
                'usedBytes': disk.used,
                'freeBytes': disk.free,
                'usedPercent': round(disk.used / disk.total * 100, 1)
                if disk.total
                else None,
            }
        except OSError:
            logger.exception('Platform monitoring could not check disk usage.')
            storage = {
                'status': 'unavailable',
                'totalBytes': None,
                'usedBytes': None,
                'freeBytes': None,
                'usedPercent': None,
            }

        task_data = {
            'status': 'unavailable',
            'startedAt': None,
            'finishedAt': None,
            'durationMs': None,
            'errorType': None,
            'history': [],
        }
        if database_status == 'operational':
            try:
                task_runs = list(
                    PlatformTaskRun.objects.filter(
                        task_name='process_credit_notifications',
                    ).order_by('-started_at', '-id')[:10],
                )
            except DatabaseError:
                logger.exception(
                    'Platform monitoring could not load task execution history.',
                )
            else:
                latest_task_run = task_runs[0] if task_runs else None
                if latest_task_run:
                    task_data = {
                        'status': latest_task_run.status,
                        'startedAt': latest_task_run.started_at,
                        'finishedAt': latest_task_run.finished_at,
                        'durationMs': latest_task_run.duration_ms,
                        'errorType': latest_task_run.error_type or None,
                        'history': [
                            {
                                'id': run.id,
                                'status': run.status,
                                'startedAt': run.started_at,
                                'finishedAt': run.finished_at,
                                'durationMs': run.duration_ms,
                                'errorType': run.error_type or None,
                            }
                            for run in task_runs
                        ],
                    }
                else:
                    task_data['status'] = 'unconfigured'

        return Response({
            'checkedAt': timezone.now(),
            'system': {
                'application': {'status': 'operational'},
                'database': {'status': database_status},
                'storage': storage,
            },
            'tasks': {
                'creditNotifications': task_data,
            },
            'unconfigured': [
                'serverErrors',
                'applicationErrors',
                'backgroundTasks',
                'backups',
                'securityAlerts',
            ],
        })


class PlatformOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        settings = PlatformSettings.objects.get(pk=1)
        tenants = list(
            Tenant.objects.annotate(
                platform_active_users=Count(
                    'users',
                    filter=Q(
                        users__is_active=True,
                        users__is_platform_admin=False,
                    ),
                ),
                platform_has_users=Count(
                    'users',
                    filter=Q(users__is_platform_admin=False),
                ),
            ).order_by('name', 'id')
        )
        tenant_summaries = [
            tenant_summary(tenant)
            for tenant in tenants
        ]
        statuses = [tenant['status'] for tenant in tenant_summaries]

        return Response({
            'limits': {
                'maxTenants': settings.max_tenants,
                'maxActiveUsers': settings.max_active_users,
            },
            'counts': {
                'tenants': len(tenant_summaries),
                'activeTenants': statuses.count('active'),
                'pendingTenants': statuses.count('pending'),
                'suspendedTenants': statuses.count('suspended'),
                'expiredTenants': statuses.count('expired'),
                'activeUsers': sum(
                    tenant['activeUsers'] for tenant in tenant_summaries
                ),
            },
            'tenants': tenant_summaries,
        })
