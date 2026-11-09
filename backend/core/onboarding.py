import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone

from .models import Invitation, TenantMembership
from .outbox import queue_branded_email


@transaction.atomic
def send_password_setup_email(user, tenant, created_by=None):
    now = timezone.now()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    expires_at = now + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
    user.set_unusable_password()
    user.must_change_password = True
    user.invitation_pending = True
    user.save(update_fields=[
        'password',
        'must_change_password',
        'invitation_pending',
        'updated_at',
    ])
    TenantMembership.objects.filter(
        tenant=tenant,
        user=user,
    ).update(is_active=False)
    Invitation.objects.filter(
        user=user,
        used_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    invitation = Invitation.objects.create(
        tenant=tenant,
        email=user.email,
        user=user,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by=created_by or user,
    )

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    setup_url = (
        f'{settings.FRONTEND_BASE_URL.rstrip("/")}/reset-password'
        f'?{urlencode({"uid": uid, "token": token, "purpose": "invitation"})}'
    )
    message = (
        f'Bonjour {user.get_full_name() or user.username},\n\n'
        f'Votre espace {tenant.name} sur DJIBEXA est prêt. '
        f'Votre identifiant est : {user.username}\n\n'
        'Choisissez votre propre mot de passe avec le lien personnel ci-dessous. '
        f'Ce lien est à usage unique et expire le {timezone.localtime(expires_at):%d/%m/%Y à %H:%M}.\n\n'
        f'Lien d’activation :\n{setup_url}\n\n'
        f'En cas de difficulté, contactez le support : {settings.DEFAULT_FROM_EMAIL}.\n'
        'Si vous ne vous attendiez pas à cette invitation, contactez '
        'l’administrateur de la plateforme.'
    )
    return queue_branded_email(
        subject='Votre invitation DJIBEXA — choisissez votre mot de passe',
        message=message,
        recipient=user.email,
        tenant=tenant,
        idempotency_key=f'invitation:{invitation.pk}',
        action_url=setup_url,
        action_label='Choisir mon mot de passe',
    )
