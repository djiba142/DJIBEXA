from django.urls import path

from .platform_views import (
    PlatformAuditLogListView,
    PlatformMonitoringView,
    PlatformOverviewView,
    PlatformTenantActionView,
    PlatformTenantAdminInvitationView,
    PlatformTenantCreateView,
    PlatformTenantDetailView,
)


urlpatterns = [
    path('overview/', PlatformOverviewView.as_view(), name='platform-overview'),
    path('tenants/', PlatformTenantCreateView.as_view(), name='platform-tenant-create'),
    path(
        'tenants/<int:pk>/',
        PlatformTenantDetailView.as_view(),
        name='platform-tenant-detail',
    ),
    path(
        'tenants/<int:pk>/admin-invitation/',
        PlatformTenantAdminInvitationView.as_view(),
        name='platform-tenant-admin-invitation',
    ),
    path(
        'tenants/<int:pk>/<str:action>/',
        PlatformTenantActionView.as_view(),
        name='platform-tenant-action',
    ),
    path('audit/', PlatformAuditLogListView.as_view(), name='platform-audit-log'),
    path(
        'monitoring/',
        PlatformMonitoringView.as_view(),
        name='platform-monitoring',
    ),
]
