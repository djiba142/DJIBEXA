import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.mailer import create_branded_email
from core.models import EmailOutbox
from core.outbox import decrypt_outbox_payload

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
LEASE_TIMEOUT = timedelta(minutes=5)


def _claim_next_email(now):
    retry_cutoff = now - LEASE_TIMEOUT
    available = (
        Q(status='queued', next_attempt_at__lte=now)
        | Q(status='failed', next_attempt_at__lte=now, attempts__lt=MAX_ATTEMPTS)
        | Q(status='sending', updated_at__lt=retry_cutoff, attempts__lt=MAX_ATTEMPTS)
    )
    with transaction.atomic():
        entry = (
            EmailOutbox.objects.select_for_update()
            .filter(available)
            .order_by('next_attempt_at', 'created_at', 'pk')
            .first()
        )
        if entry is None:
            return None
        entry.status = 'sending'
        entry.attempts += 1
        entry.last_error = ''
        entry.save(update_fields=['status', 'attempts', 'last_error', 'updated_at'])
        return entry.pk, entry.recipient, entry.payload, entry.attempts


def _send_claimed_email(email_id, recipient, encrypted_payload, attempt):
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


class Command(BaseCommand):
    help = 'Livre les e-mails transactionnels enregistrés dans l’outbox.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        limit = options['limit']
        if limit < 1:
            raise CommandError('--limit doit être supérieur à zéro.')

        sent = 0
        failed = 0
        for _ in range(limit):
            claimed = _claim_next_email(timezone.now())
            if claimed is None:
                break
            email_id, recipient, payload, attempt = claimed
            if _send_claimed_email(email_id, recipient, payload, attempt):
                sent += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f'E-mails envoyés : {sent}; échecs avec reprise planifiée : {failed}.',
        ))
        if failed:
            raise CommandError(f'{failed} e-mail(s) n’ont pas pu être livrés.')
