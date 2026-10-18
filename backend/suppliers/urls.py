from django.urls import path

from .views import (
    ExchangeRateListCreateView,
    SupplierDetailView,
    SupplierImportConfirmView,
    SupplierImportDocumentView,
    SupplierImportRowCorrectionView,
    SupplierImportRowMatchView,
    SupplierImportView,
    SupplierListCreateView,
)

urlpatterns = [
    path('exchange-rates/', ExchangeRateListCreateView.as_view(), name='exchange-rate-list-create'),
    path('imports/', SupplierImportView.as_view(), name='supplier-import-create'),
    path('imports/<int:import_id>/document/', SupplierImportDocumentView.as_view(), name='supplier-import-document'),
    path('imports/<int:pk>/confirm/', SupplierImportConfirmView.as_view(), name='supplier-import-confirm'),
    path('imports/<int:import_id>/rows/<int:row_id>/match/', SupplierImportRowMatchView.as_view(), name='supplier-import-row-match'),
    path('imports/<int:import_id>/rows/<int:row_id>/correction/', SupplierImportRowCorrectionView.as_view(), name='supplier-import-row-correction'),
    path('', SupplierListCreateView.as_view(), name='supplier-list-create'),
    path('<int:pk>/', SupplierDetailView.as_view(), name='supplier-detail'),
]
