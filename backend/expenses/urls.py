from django.urls import path

from .views import ExpenseActionView, ExpenseAttachmentListCreateView, ExpenseCategoryListCreateView, ExpenseDetailView, ExpenseListCreateView

urlpatterns = [
    path('categories/', ExpenseCategoryListCreateView.as_view(), name='expense-category-list-create'),
    path('', ExpenseListCreateView.as_view(), name='expense-list-create'),
    path('<int:expense_id>/attachments/', ExpenseAttachmentListCreateView.as_view(), name='expense-attachments'),
    path('<int:pk>/', ExpenseDetailView.as_view(), name='expense-detail'),
    path('<int:pk>/<str:action>/', ExpenseActionView.as_view(), name='expense-action'),
]
