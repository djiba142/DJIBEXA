import base64
import hashlib
import json

from cryptography.fernet import Fernet
from django.conf import settings

from .models import EmailOutbox


def _payload_cipher():
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest(),
    )
    return Fernet(key)


def queue_branded_email(
    *,
    recipient,
    subject,
    message,
    idempotency_key,
    tenant=None,
    action_url=None,
    action_label=None,
):
    payload = json.dumps({
        'subject': subject,
        'message': message,
        'action_url': action_url,
        'action_label': action_label,
    }).encode('utf-8')
    encrypted_payload = _payload_cipher().encrypt(payload).decode('ascii')
    entry, _ = EmailOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'tenant': tenant,
            'recipient': recipient,
            'template_code': 'branded',
            'payload': {'encrypted': encrypted_payload},
        },
    )
    return entry


def decrypt_outbox_payload(entry):
    encrypted = entry.payload.get('encrypted')
    if not encrypted:
        raise ValueError('Le contenu de cet e-mail est absent ou invalide.')
    decrypted = _payload_cipher().decrypt(encrypted.encode('ascii'))
    payload = json.loads(decrypted)
    if not all(key in payload for key in ('subject', 'message')):
        raise ValueError('Le contenu de cet e-mail est incomplet.')
    return payload
