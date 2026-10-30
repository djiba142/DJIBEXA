from django.urls import path

from .views import CreditListView, CustomerCreditDetailView, CustomerPaymentSummaryView, PaymentDetailView, PaymentListCreateView, PaymentReceiptView

urlpatterns = [
    path('', PaymentListCreateView.as_view(), name='payment-list-create'),
    path('credits/', CreditListView.as_view(), name='credit-list'),
    path('<int:pk>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('<int:pk>/receipt/', PaymentReceiptView.as_view(), name='payment-receipt'),
    path('customer/<int:customer_id>/', CustomerPaymentSummaryView.as_view(), name='customer-payment-summary'),
    path('customer/<int:customer_id>/credits/', CustomerCreditDetailView.as_view(), name='customer-credit-detail'),
]
