import base64
import hashlib
import json
import logging
from datetime import timedelta

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .mailer import create_branded_email
from .models import EmailOutbox

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
LEASE_TIMEOUT = timedelta(minutes=5)


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
    entry, created = EmailOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'tenant': tenant,
            'recipient': recipient,
            'template_code': 'branded',
            'payload': {'encrypted': encrypted_payload},
        },
    )
    if created:
        transaction.on_commit(
            lambda entry_id=entry.pk: deliver_outbox_entry(entry_id),
            robust=True,
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


def send_claimed_outbox_email(email_id, recipient, encrypted_payload, attempt):
    try:
        entry = EmailOutbox(id=email_id, payload=encrypted_payload)
        payload = decrypt_outbox_payload(entry)
        email = create_branded_email(
            subject=payload['subject'],
            message=payload['message'],
            recipient_list=[recipient],
            action_url=payload.get('action_url'),
            action_label=payload.get('action_label'),
        )
        if email.send(fail_silently=False) != 1:
            raise RuntimeError('Le backend e-mail n’a confirmé aucun envoi.')
    except Exception as error:
        logger.exception('Échec de livraison d’un e-mail outbox (id=%s).', email_id)
        delay_seconds = min(3600, 60 * (2 ** min(attempt - 1, 6)))
        EmailOutbox.objects.filter(pk=email_id).update(
            status='failed',
            next_attempt_at=timezone.now() + timedelta(seconds=delay_seconds),
            last_error=type(error).__name__,
            updated_at=timezone.now(),
        )
        return False

    now = timezone.now()
    EmailOutbox.objects.filter(pk=email_id).update(
        status='sent',
        sent_at=now,
        last_error='',
        updated_at=now,
    )
    return True


def deliver_outbox_entry(email_id):
    now = timezone.now()
    available = (
        Q(status='queued', next_attempt_at__lte=now)
        | Q(status='failed', next_attempt_at__lte=now, attempts__lt=MAX_ATTEMPTS)
        | Q(
            status='sending',
            updated_at__lt=now - LEASE_TIMEOUT,
            attempts__lt=MAX_ATTEMPTS,
        )
    )
    with transaction.atomic():
        entry = (
            EmailOutbox.objects.select_for_update()
            .filter(available, pk=email_id)
            .first()
        )
        if entry is None:
            return False
        entry.status = 'sending'
        entry.attempts += 1
        entry.last_error = ''
        entry.save(update_fields=['status', 'attempts', 'last_error', 'updated_at'])
        claimed = (entry.pk, entry.recipient, entry.payload, entry.attempts)

    return send_claimed_outbox_email(*claimed)
