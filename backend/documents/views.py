from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import tenant_scoped_queryset
from users.permissions import role_permission
from .models import DeliveryNote, Document
from .serializers import DeliveryNoteSerializer, DocumentSerializer


class DocumentListCreateView(generics.ListCreateAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated, role_permission('core')]


class DocumentDetailView(generics.RetrieveUpdateAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated, role_permission('core')]

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.status = 'archived'
        instance.notes = instance.notes or ''
        if 'archivé' not in instance.notes.lower():
            instance.notes = f"{instance.notes} Archivage effectué par {request.user.display_name or request.user.username}.".strip()
        instance.save(update_fields=['status', 'notes', 'updated_at'])
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)


class DeliveryNoteListCreateView(generics.ListCreateAPIView):
    queryset = DeliveryNote.objects.select_related('sale__customer').prefetch_related('items__product').all()
    serializer_class = DeliveryNoteSerializer
    permission_classes = [permissions.IsAuthenticated, role_permission('sales')]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='sale__tenant',
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DeliveryNoteDetailView(generics.RetrieveUpdateAPIView):
    queryset = DeliveryNote.objects.select_related('sale__customer').prefetch_related('items__product').all()
    serializer_class = DeliveryNoteSerializer
    permission_classes = [permissions.IsAuthenticated, role_permission('sales')]

    def get_queryset(self):
        return tenant_scoped_queryset(
            super().get_queryset(),
            self.request.user,
            tenant_field='sale__tenant',
        )


class DeliveryNoteVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        note = DeliveryNote.objects.select_related('sale__customer').filter(
            verification_token=token,
        ).first()
        if note is None:
            return Response({'detail': 'Bon de livraison introuvable ou jeton invalide.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'valid': note.status != 'cancelled' and note.sale.status != 'cancelled',
            'status': 'cancelled' if note.status == 'cancelled' or note.sale.status == 'cancelled' else note.status,
            'kind': 'delivery',
            'number': note.reference,
            'created_at': note.created_at,
            'items_count': note.items.count(),
        }, status=status.HTTP_200_OK)
