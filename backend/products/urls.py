from django.urls import path

from .views import (
    CategoryListCreateView,
    ProductArchiveView,
    ProductDetailView,
    ProductListCreateView,
    ProductPricingView,
    ProductStockView,
)
from .catalog_imports import (
    ProductCatalogImportConfirmView,
    ProductCatalogImportMappingView,
    ProductCatalogImportPreviewView,
    ProductCatalogImportTemplateView,
)

urlpatterns = [
    path('categories/', CategoryListCreateView.as_view(), name='category-list-create'),
    path('catalog-import/template/', ProductCatalogImportTemplateView.as_view(), name='product-catalog-import-template'),
    path('catalog-import/', ProductCatalogImportPreviewView.as_view(), name='product-catalog-import-preview'),
    path('catalog-import/<int:pk>/mapping/', ProductCatalogImportMappingView.as_view(), name='product-catalog-import-mapping'),
    path('catalog-import/<int:pk>/confirm/', ProductCatalogImportConfirmView.as_view(), name='product-catalog-import-confirm'),
    path('<int:pk>/pricing/', ProductPricingView.as_view(), name='product-pricing'),
    path('<int:pk>/stock/', ProductStockView.as_view(), name='product-stock'),
    path('<int:pk>/archive/', ProductArchiveView.as_view(), name='product-archive'),
    path('', ProductListCreateView.as_view(), name='product-list-create'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
]
