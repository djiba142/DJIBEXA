from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from sales.serializers import SaleSerializer
from payments.serializers import PaymentSerializer
from users.permissions import role_permission
from .models import SyncOperation


class SyncOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncOperation
        fields = ['local_id', 'operation_type', 'status', 'result', 'error', 'created_at']
        read_only_fields = ['status', 'result', 'error', 'created_at']


class SyncView(APIView):
    permission_classes = [role_permission('sales')]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        operations = request.data.get('operations', request.data)
        if isinstance(operations, dict):
            operations = [operations]
        if not isinstance(operations, list):
            return Response({'detail': 'operations doit être une liste ou un objet.'}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        for operation in operations:
            local_id = operation.get('local_id')
            operation_type = operation.get('operation_type')
            payload = operation.get('payload', {})
            if not local_id or operation_type not in {'sale', 'payment'} or not isinstance(payload, dict):
                results.append({'local_id': local_id, 'status': 'rejected', 'error': 'Opération invalide.'})
                continue

            existing = SyncOperation.objects.filter(user=request.user, local_id=local_id).first()
            if existing:
                results.append(SyncOperationSerializer(existing).data)
                continue

            try:
                serializer_class = SaleSerializer if operation_type == 'sale' else PaymentSerializer
                serializer = serializer_class(data=payload, context={'request': request})
                serializer.is_valid(raise_exception=True)
                record = SyncOperation.objects.create(
                    user=request.user,
                    local_id=local_id,
                    operation_type=operation_type,
                    status='accepted',
                    payload=payload,
                )
                saved = serializer.save()
                record.result = {
                    'id': saved.id,
                    'reference': getattr(saved, 'invoice_number', None) or getattr(saved, 'reference', None),
                }
                record.save(update_fields=['result'])
                results.append(SyncOperationSerializer(record).data)
            except (serializers.ValidationError, ValueError) as exc:
                record = SyncOperation.objects.create(
                    user=request.user,
                    local_id=local_id,
                    operation_type=operation_type,
                    status='rejected',
                    payload=payload,
                    error=getattr(exc, 'detail', str(exc)),
                )
                results.append(SyncOperationSerializer(record).data)

        return Response({'results': results}, status=status.HTTP_200_OK)