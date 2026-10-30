from django.urls import path

from .views import CustomerCreditView, CustomerDetailView, CustomerInvoicesHistoryView, CustomerListCreateView, CustomerPaymentsHistoryView, CustomerSalesHistoryView

urlpatterns = [
    path('', CustomerListCreateView.as_view(), name='customer-list-create'),
    path('<int:pk>/', CustomerDetailView.as_view(), name='customer-detail'),
    path('<int:pk>/sales/', CustomerSalesHistoryView.as_view(), name='customer-sales-history'),
    path('<int:pk>/invoices/', CustomerInvoicesHistoryView.as_view(), name='customer-invoices-history'),
    path('<int:pk>/payments/', CustomerPaymentsHistoryView.as_view(), name='customer-payments-history'),
    path('<int:pk>/credit/', CustomerCreditView.as_view(), name='customer-credit'),
]
