from django.urls import path

from .views import (
    ExternalSaleListCreateView,
    CustomerOrderActionView,
    CustomerOrderDetailView,
    CustomerOrderListCreateView,
    SaleCatalogView,
    SaleDetailView,
    SaleExternalSupplierListView,
    SaleListCreateView,
    SaleLocationListView,
    SaleReturnCreateView,
    SaleReturnQuarantineListView,
    SaleReturnQuarantineReleaseView,
)

urlpatterns = [
    path('customer-orders/', CustomerOrderListCreateView.as_view(), name='customer-order-list-create'),
    path(
        'customer-orders/<int:pk>/',
        CustomerOrderDetailView.as_view(),
        name='customer-order-detail',
    ),
    path(
        'customer-orders/<int:pk>/<str:action>/',
        CustomerOrderActionView.as_view(),
        name='customer-order-action',
    ),
    path('catalog/', SaleCatalogView.as_view(), name='sale-catalog'),
    path('locations/', SaleLocationListView.as_view(), name='sale-locations'),
    path(
        'external-suppliers/',
        SaleExternalSupplierListView.as_view(),
        name='sale-external-suppliers',
    ),
    path('external/', ExternalSaleListCreateView.as_view(), name='external-sale-list-create'),
    path('', SaleListCreateView.as_view(), name='sale-list-create'),
    path('<int:pk>/returns/', SaleReturnCreateView.as_view(), name='sale-return-create'),
    path(
        '<int:pk>/returns/quarantines/',
        SaleReturnQuarantineListView.as_view(),
        name='sale-return-quarantines',
    ),
    path(
        'return-quarantines/<int:pk>/release/',
        SaleReturnQuarantineReleaseView.as_view(),
        name='sale-return-quarantine-release',
    ),
    path('<int:pk>/', SaleDetailView.as_view(), name='sale-detail'),
]
