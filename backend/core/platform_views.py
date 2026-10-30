import logging
import shutil

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsPlatformAdmin
from users.models import User

from .onboarding import send_temporary_password_email
from .models import PlatformAuditLog, PlatformSettings, PlatformTaskRun, Tenant
from .pagination import VersionedApiPagination

logger = logging.getLogger(__name__)


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


def activate_pending_tenant_admins(tenant):
    pending_admins = list(
        tenant.users.select_for_update().filter(
            is_active=False,
            is_platform_admin=False,
            invitation_pending=True,
            must_change_password=True,
        )
    )
    if not pending_admins:
        return
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
    for invited_admin in pending_admins:
        invited_admin.is_active = True
        invited_admin.invitation_pending = False
        invited_admin.save(update_fields=[
            'is_active',
            'invitation_pending',
            'updated_at',
        ])


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

        user = User(
            username=serializer.validated_data['username'],
            email=serializer.validated_data['email'],
            first_name=serializer.validated_data.get('first_name', ''),
            last_name=serializer.validated_data.get('last_name', ''),
            role='admin',
            tenant=tenant,
            is_active=tenant.status_at() == 'active',
            invitation_pending=tenant.status_at() != 'active',
        )
        user.save()
        send_temporary_password_email(user, tenant)
        PlatformAuditLog.objects.create(
            actor=request.user,
            tenant=tenant,
            action='invite_admin',
            details={'role': 'admin'},
        )
        return Response(
            {'invited': True},
            status=status.HTTP_201_CREATED,
        )


class PlatformTenantActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk, action):
        tenant = get_object_or_404(Tenant.objects.select_for_update(), pk=pk)
        now = timezone.now()
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
            activate_pending_tenant_admins(tenant)
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
            activate_pending_tenant_admins(tenant)
            audit_action = 'resume'
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
        return Response(tenant_summary(tenant))


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
