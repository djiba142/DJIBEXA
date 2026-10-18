import csv
import io

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from core.pagination import VersionedApiPagination
from core.models import Tenant
from core.tenancy import tenant_for_user
from users.permissions import IsAdminUser, role_permission

from .models import Notification
from .reminders import (
    generate_weekly_credit_reminders,
    get_reminder_settings,
    persist_reminder_settings,
)
from .renderers import CsvRenderer
from .serializers import NotificationSerializer
from .services import dispatch_notification


def visible_notifications(user):
    tenant = tenant_for_user(user)
    if tenant is None:
        if Tenant.objects.exists() or getattr(user, 'is_platform_admin', False):
            return Notification.objects.none()
        return Notification.objects.filter(
            Q(recipient_user__isnull=True) | Q(recipient_user=user)
        )

    legacy_owner = (
        Q(sale__tenant_id=tenant.pk)
        | Q(customer__tenant_id=tenant.pk)
        | Q(recipient_user__tenant_id=tenant.pk)
    )
    same_tenant_relations = (
        (Q(sale__isnull=True) | Q(sale__tenant_id__isnull=True) | Q(sale__tenant_id=tenant.pk))
        & (
            Q(customer__isnull=True)
            | Q(customer__tenant_id__isnull=True)
            | Q(customer__tenant_id=tenant.pk)
        )
        & (
            Q(sale__customer__tenant_id__isnull=True)
            | Q(sale__customer__tenant_id=tenant.pk)
        )
        & (
            Q(recipient_user__isnull=True)
            | Q(recipient_user__tenant_id__isnull=True)
            | Q(recipient_user__tenant_id=tenant.pk)
        )
    )
    legacy_scope = Q(tenant__isnull=True) & legacy_owner
    if getattr(user, 'tenant_id', None) is None:
        legacy_scope |= (
            Q(tenant__isnull=True)
            & (Q(recipient_user__isnull=True) | Q(recipient_user=user))
        )

    return Notification.objects.filter(
        (Q(tenant_id=tenant.pk) | legacy_scope)
        & same_tenant_relations
    )


class NotificationTenantPermission(BasePermission):
    message = 'Votre compte doit être rattaché à un espace d’entreprise.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, 'is_platform_admin', False):
            return False
        if tenant_for_user(request.user) is not None:
            return True
        return not Tenant.objects.exists()


class CreditReminderSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    frequency = serializers.ChoiceField(choices=['weekly'], required=False)
    day_of_week = serializers.IntegerField(min_value=0, max_value=6, required=False)
    time = serializers.TimeField(
        format='%H:%M',
        input_formats=['%H:%M'],
        required=False,
    )
    timezone = serializers.CharField(read_only=True)


class CreditReminderSettingsView(generics.GenericAPIView):
    serializer_class = CreditReminderSettingsSerializer

    def get_permissions(self):
        permission_classes = [
            permissions.IsAuthenticated,
            NotificationTenantPermission,
            role_permission('notifications'),
        ]
        if self.request.method not in permissions.SAFE_METHODS:
            permission_classes.append(IsAdminUser)
        return [permission() for permission in permission_classes]

    def get(self, request, *args, **kwargs):
        tenant = tenant_for_user(request.user)
        serializer = self.get_serializer(get_reminder_settings(tenant))
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings_data = {
            key: value for key, value in serializer.validated_data.items()
            if key != 'timezone'
        }
        response_data = persist_reminder_settings(
            settings_data,
            request.user,
            tenant_for_user(request.user),
        )
        return Response(self.get_serializer(response_data).data)


class WeeklyCreditReminderView(generics.GenericAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        NotificationTenantPermission,
        role_permission('notifications'),
    ]

    def post(self, request, *args, **kwargs):
        created_ids = generate_weekly_credit_reminders(
            tenant=tenant_for_user(request.user),
            include_legacy=request.user.tenant_id is None,
        )
        return Response({
            'created': len(created_ids),
            'generated_at': timezone.now(),
            'notification_ids': created_ids,
        }, status=status.HTTP_200_OK)


class NotificationListCreateView(generics.ListCreateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        NotificationTenantPermission,
        role_permission('notifications'),
    ]

    def get_queryset(self):
        return visible_notifications(self.request.user).select_related(
            'sale', 'customer', 'recipient_user',
        )

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for_user(self.request.user))


class NotificationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        NotificationTenantPermission,
        role_permission('notifications'),
    ]

    def get_queryset(self):
        return visible_notifications(self.request.user).select_related(
            'sale', 'customer', 'recipient_user',
        )


class NotificationReadView(generics.GenericAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        NotificationTenantPermission,
        role_permission('notifications'),
    ]

    def get_queryset(self):
        return visible_notifications(self.request.user).select_related(
            'sale', 'customer', 'recipient_user',
        )

    def post(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at', 'updated_at'])
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationDispatchView(generics.GenericAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        NotificationTenantPermission,
        role_permission('notifications'),
    ]

    def get_queryset(self):
        return visible_notifications(self.request.user).select_related(
            'sale', 'customer', 'recipient_user',
        )

    def post(self, request, *args, **kwargs):
        notification = self.get_object()
        if notification.status == 'sent':
            return Response(
                {'detail': 'Cette notification a déjà été envoyée.'},
                status=status.HTTP_409_CONFLICT,
            )

        if notification.channel == 'whatsapp':
            result = dispatch_notification(notification.id)
            notification.refresh_from_db()
            if result.get('cancelled'):
                return Response(NotificationSerializer(notification).data, status=status.HTTP_200_OK)
            if not result.get('success', False):
                return Response({
                    'detail': result.get('error', 'Échec de l’envoi WhatsApp.'),
                    'status': notification.status,
                    'attempt_count': notification.attempt_count,
                    'next_attempt_at': notification.next_attempt_at,
                }, status=status.HTTP_502_BAD_GATEWAY)
        else:
            notification.status = 'sent'
            notification.is_read = False
            notification.save(update_fields=['status', 'is_read', 'updated_at'])
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationHistoryView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    pagination_class = VersionedApiPagination
    permission_classes = [
        permissions.IsAuthenticated,
        NotificationTenantPermission,
        role_permission('notifications'),
    ]

    def get_queryset(self):
        return visible_notifications(self.request.user).select_related(
            'sale__customer', 'customer', 'recipient_user',
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()).order_by('-created_at')
        page = self.paginate_queryset(queryset)
        items = []
        for notification in page or queryset:
            payload = NotificationSerializer(notification).data
            customer = notification.customer or (notification.sale.customer if notification.sale else None)
            payload['customer_name'] = customer.full_name if customer else ''
            payload['customer_phone'] = customer.phone if customer else ''
            payload['sale_id'] = notification.sale_id
            payload['sale_total'] = str(notification.sale.total_amount) if notification.sale else ''
            payload['sale_status'] = notification.sale.status if notification.sale else ''
            items.append(payload)

        if page is not None:
            return self.get_paginated_response(items)
        return Response(items, status=status.HTTP_200_OK)


@api_view(['GET'])
@renderer_classes([JSONRenderer, CsvRenderer])
@permission_classes([
    permissions.IsAuthenticated,
    NotificationTenantPermission,
    role_permission('notifications'),
])
def NotificationExportView(request, *args, **kwargs):
    notifications = visible_notifications(request.user).select_related(
        'sale__customer', 'customer', 'recipient_user',
    ).order_by('-created_at')
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow([
        'id', 'event_type', 'channel', 'status', 'recipient_phone', 'customer_name',
        'sale_id', 'sale_total', 'sale_status', 'message', 'created_at'
    ])
    for notification in notifications:
        customer = notification.customer or (notification.sale.customer if notification.sale else None)
        writer.writerow([
            notification.id,
            notification.event_type,
            notification.channel,
            notification.status,
            notification.recipient_phone,
            customer.full_name if customer else '',
            notification.sale_id or '',
            notification.sale.total_amount if notification.sale else '',
            notification.sale.status if notification.sale else '',
            notification.message,
            notification.created_at.isoformat() if notification.created_at else '',
        ])

    response = HttpResponse(csv_buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="notifications.csv"'
    return response


class MessageHistoryView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        NotificationTenantPermission,
        role_permission('notifications'),
    ]

    def get_queryset(self):
        return visible_notifications(self.request.user).select_related(
            'sale', 'recipient_user',
        )
