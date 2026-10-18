from django.urls import path

from .views import (
    FinancialAccountDetailView,
    FinancialAccountListCreateView,
    FinancialTransactionDetailView,
    FinancialTransactionListCreateView,
    FinancialTransactionValidateView,
    FinancialTransferView,
    FundActionView,
    FundDetailView,
    FundListCreateView,
    FinancialSummaryView,
    FinancialAuditView,
    FinancialReportView,
)

urlpatterns = [
    path('summary/', FinancialSummaryView.as_view(), name='financial-summary'),
    path('reports/', FinancialReportView.as_view(), name='financial-report'),
    path('audit/', FinancialAuditView.as_view(), name='financial-audit'),
    path('accounts/', FinancialAccountListCreateView.as_view(), name='financial-account-list-create'),
    path('accounts/<int:pk>/', FinancialAccountDetailView.as_view(), name='financial-account-detail'),
    path('transactions/', FinancialTransactionListCreateView.as_view(), name='financial-transaction-list-create'),
    path('transactions/<int:pk>/', FinancialTransactionDetailView.as_view(), name='financial-transaction-detail'),
    path('transactions/<int:pk>/validate/', FinancialTransactionValidateView.as_view(), name='financial-transaction-validate'),
    path('transfers/', FinancialTransferView.as_view(), name='financial-transfer'),
    path('funds/', FundListCreateView.as_view(), name='fund-list-create'),
    path('funds/<int:pk>/', FundDetailView.as_view(), name='fund-detail'),
    path('funds/<int:pk>/<str:action>/', FundActionView.as_view(), name='fund-action'),
]