from django.urls import path

from .platform_views import (
    PlatformAuditLogListView,
    PlatformDemoRequestDetailView,
    PlatformDemoRequestListView,
    PlatformMonitoringView,
    PlatformModulesView,
    PlatformModuleDetailView,
    PlatformOverviewView,
    PlatformReportsView,
    PlatformPaymentActionView,
    PlatformPaymentsView,
    PlatformPlanDetailView,
    PlatformPlansView,
    PlatformSettingsView,
    PlatformSubscriptionActionView,
    PlatformSubscriptionsView,
    PlatformTenantActionView,
    PlatformTenantAdminInvitationView,
    PlatformTenantCreateView,
    PlatformTenantDetailView,
    PlatformTenantDomainActionView,
    PlatformTenantDomainsView,
    PlatformTenantModulesView,
    PlatformUserActionView,
    PlatformUsersView,
)


urlpatterns = [
    path('overview/', PlatformOverviewView.as_view(), name='platform-overview'),
    path('reports/', PlatformReportsView.as_view(), name='platform-reports'),
    path('settings/', PlatformSettingsView.as_view(), name='platform-settings'),
    path('users/', PlatformUsersView.as_view(), name='platform-users'),
    path(
        'users/<int:pk>/<str:action>/',
        PlatformUserActionView.as_view(),
        name='platform-user-action',
    ),
    path('plans/', PlatformPlansView.as_view(), name='platform-plans'),
    path('plans/<int:pk>/', PlatformPlanDetailView.as_view(), name='platform-plan-detail'),
    path('subscriptions/', PlatformSubscriptionsView.as_view(), name='platform-subscriptions'),
    path(
        'subscriptions/<int:pk>/<str:action>/',
        PlatformSubscriptionActionView.as_view(),
        name='platform-subscription-action',
    ),
    path('payments/', PlatformPaymentsView.as_view(), name='platform-payments'),
    path(
        'payments/<int:pk>/<str:action>/',
        PlatformPaymentActionView.as_view(),
        name='platform-payment-action',
    ),
    path('modules/', PlatformModulesView.as_view(), name='platform-modules'),
    path('modules/<int:pk>/', PlatformModuleDetailView.as_view(), name='platform-module-detail'),
    path(
        'tenants/<int:pk>/modules/',
        PlatformTenantModulesView.as_view(),
        name='platform-tenant-modules',
    ),
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
        'tenants/<int:pk>/domains/',
        PlatformTenantDomainsView.as_view(),
        name='platform-tenant-domains',
    ),
    path(
        'domains/<int:pk>/<str:action>/',
        PlatformTenantDomainActionView.as_view(),
        name='platform-tenant-domain-action',
    ),
    path(
        'tenants/<int:pk>/<str:action>/',
        PlatformTenantActionView.as_view(),
        name='platform-tenant-action',
    ),
    path('audit/', PlatformAuditLogListView.as_view(), name='platform-audit-log'),
    path(
        'demo-requests/',
        PlatformDemoRequestListView.as_view(),
        name='platform-demo-requests',
    ),
    path(
        'demo-requests/<int:pk>/',
        PlatformDemoRequestDetailView.as_view(),
        name='platform-demo-request-detail',
    ),
    path(
        'monitoring/',
        PlatformMonitoringView.as_view(),
        name='platform-monitoring',
    ),
]
