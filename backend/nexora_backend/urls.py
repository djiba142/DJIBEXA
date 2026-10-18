"""
URL configuration for nexora_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from notifications.views import (
    MessageHistoryView,
    NotificationDetailView,
    NotificationDispatchView,
    NotificationExportView,
    NotificationHistoryView,
    NotificationListCreateView,
    NotificationReadView,
    WeeklyCreditReminderView,
)
from core.health import health_check


def frontend_home(request):
    return redirect(settings.FRONTEND_BASE_URL)

urlpatterns = [
    path('healthz/', health_check, name='health-check'),
    path('', frontend_home, name='frontend-home'),
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/', include('nexora_backend.api_v1_urls')),
    path('api/notifications/export/', NotificationExportView, name='notification-export'),
    path('api/notifications/', include('notifications.urls')),
    path('api/users/', include('users.urls')),
    path('api/products/', include('products.urls')),
    path('api/suppliers/', include('suppliers.urls')),
    path('api/customers/', include('customers.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/purchases/', include('purchases.urls')),
    path('api/sales/', include('sales.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/expenses/', include('expenses.urls')),
    path('api/finance/', include('finance.urls')),
    path('api/invoices/', include('invoices.urls')),
    path('api/documents/', include('documents.urls')),
    path('api/core/', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
