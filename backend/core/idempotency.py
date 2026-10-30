import hashlib
import json

from django.db import IntegrityError, transaction
from rest_framework.response import Response

from .models import IdempotencyRecord


def request_fingerprint(request):
    payload = json.dumps(request.data, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def request_scope_hash(key, endpoint, user):
    user_id = getattr(user, 'pk', None) or 'anonymous'
    value = f'{key}:{endpoint}:{user_id}'
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def replay_idempotent_request(request, endpoint):
    key = request.headers.get('Idempotency-Key')
    if not key:
        return None, None

    record = IdempotencyRecord.objects.filter(scope_hash=request_scope_hash(key, endpoint, request.user)).first()
    if record is None:
        return key, None
    if record.request_hash != request_fingerprint(request):
        return key, Response(
            {'detail': 'La même Idempotency-Key a été utilisée avec des données différentes.'},
            status=409,
        )
    return key, Response(record.response_body, status=record.response_status)


def store_idempotent_response(request, endpoint, key, response):
    if not key:
        return
    response_body = json.loads(json.dumps(response.data, default=str))
    IdempotencyRecord.objects.create(
        key=key,
        endpoint=endpoint,
        scope_hash=request_scope_hash(key, endpoint, request.user),
        request_hash=request_fingerprint(request),
        response_status=response.status_code,
        response_body=response_body,
        user=request.user,
    )


def execute_idempotent_request(request, endpoint, operation):
    key = request.headers.get('Idempotency-Key')
    if not key:
        return operation()

    try:
        with transaction.atomic():
            _, replay = replay_idempotent_request(request, endpoint)
            if replay is not None:
                return replay

            response = operation()
            store_idempotent_response(request, endpoint, key, response)
            return response
    except IntegrityError:
        _, replay = replay_idempotent_request(request, endpoint)
        if replay is not None:
            return replay
        raise