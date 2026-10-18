from django.urls import path

from .views import (
    DeliveryNoteDetailView,
    DeliveryNoteListCreateView,
    DeliveryNoteVerifyView,
    DocumentDetailView,
    DocumentListCreateView,
)

urlpatterns = [
    path('delivery-notes/', DeliveryNoteListCreateView.as_view(), name='delivery-note-list-create'),
    path('delivery-notes/<int:pk>/', DeliveryNoteDetailView.as_view(), name='delivery-note-detail'),
    path('delivery-notes/verify/<uuid:token>/', DeliveryNoteVerifyView.as_view(), name='delivery-note-verify'),
    path('', DocumentListCreateView.as_view(), name='document-list-create'),
    path('<int:pk>/', DocumentDetailView.as_view(), name='document-detail'),
]
