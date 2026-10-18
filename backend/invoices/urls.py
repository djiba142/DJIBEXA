from django.urls import path

from .views import InvoiceBrandingAssetView, InvoiceBrandingView, InvoiceDetailView, InvoiceIssueView, InvoiceListView, InvoicePdfView, InvoiceQrImageView, InvoiceQrView, InvoiceVerifyView

urlpatterns = [
    path('branding/', InvoiceBrandingView.as_view(), name='invoice-branding'),
    path('branding/assets/<str:asset>/', InvoiceBrandingAssetView.as_view(), name='invoice-branding-asset'),
    path('', InvoiceListView.as_view(), name='invoice-list'),
    path('<int:pk>/', InvoiceDetailView.as_view(), name='invoice-detail'),
    path('<int:pk>/issue/', InvoiceIssueView.as_view(), name='invoice-issue'),
    path('<int:pk>/pdf/', InvoicePdfView.as_view(), name='invoice-pdf'),
    path('<int:pk>/qr/', InvoiceQrView.as_view(), name='invoice-qr'),
    path('<int:pk>/qr-image/', InvoiceQrImageView.as_view(), name='invoice-qr-image'),
    path('verify/<uuid:token>/', InvoiceVerifyView.as_view(), name='invoice-verify'),
]
