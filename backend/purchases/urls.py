from django.urls import path

from .views import (
    PurchaseOrderActionView,
    PurchaseOrderDetailView,
    PurchaseOrderEmailView,
    PurchaseOrderListCreateView,
    PurchaseReceiptDecisionView,
    PurchaseReceiptDetailView,
    PurchaseReceiptBatchCreateView,
    PurchaseReceiptListCreateView,
    PurchaseReceiptImportView,
    PurchaseReceiptSubmitView,
    PurchaseReceiptValidateView,
    ReceiptQuarantineListView,
    ReceiptQuarantineResolutionView,
)
from .external_views import (
    ExternalPurchaseCancelView,
    ExternalPurchaseListView,
    ExternalPurchaseMovementListCreateView,
    ExternalPurchasePaymentListCreateView,
    ExternalPurchaseSummaryView,
    ExternalSalePurchaseCreateView,
)

urlpatterns = [
    path('external-sales/', ExternalSalePurchaseCreateView.as_view(), name='external-sale-purchase-create'),
    path('external-purchases/', ExternalPurchaseListView.as_view(), name='external-purchase-list'),
    path('external-purchases/summary/', ExternalPurchaseSummaryView.as_view(), name='external-purchase-summary'),
    path('external-purchases/<int:pk>/cancel/', ExternalPurchaseCancelView.as_view(), name='external-purchase-cancel'),
    path('external-purchases/<int:purchase_id>/movements/', ExternalPurchaseMovementListCreateView.as_view(), name='external-purchase-movements'),
    path('external-payments/', ExternalPurchasePaymentListCreateView.as_view(), name='external-purchase-payment-list-create'),
    path('orders/', PurchaseOrderListCreateView.as_view(), name='purchase-order-list-create'),
    path('orders/<int:pk>/', PurchaseOrderDetailView.as_view(), name='purchase-order-detail'),
    path('orders/<int:pk>/email/', PurchaseOrderEmailView.as_view(), name='purchase-order-email'),
    path('orders/<int:pk>/<str:action>/', PurchaseOrderActionView.as_view(), name='purchase-order-action'),
    path('receipts/', PurchaseReceiptListCreateView.as_view(), name='purchase-receipt-list-create'),
    path('receipts/batch/', PurchaseReceiptBatchCreateView.as_view(), name='purchase-receipt-batch-create'),
    path('receipts/import/', PurchaseReceiptImportView.as_view(), name='purchase-receipt-import'),
    path('receipts/<int:pk>/', PurchaseReceiptDetailView.as_view(), name='purchase-receipt-detail'),
    path('receipts/<int:pk>/submit/', PurchaseReceiptSubmitView.as_view(), name='purchase-receipt-submit'),
    path('receipts/<int:pk>/decision/<str:action>/', PurchaseReceiptDecisionView.as_view(), name='purchase-receipt-decision'),
    path('receipts/<int:pk>/validate/', PurchaseReceiptValidateView.as_view(), name='purchase-receipt-validate'),
    path('quarantines/', ReceiptQuarantineListView.as_view(), name='receipt-quarantine-list'),
    path('quarantines/<int:pk>/<str:action>/', ReceiptQuarantineResolutionView.as_view(), name='receipt-quarantine-resolution'),
]
