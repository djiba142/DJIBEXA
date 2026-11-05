from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.crypto import get_random_string

from .mailer import send_branded_mail


def send_password_setup_email(user, tenant):
    user.set_unusable_password()
    user.must_change_password = True
    user.save(update_fields=['password', 'must_change_password', 'updated_at'])

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    validity_hours = max(1, (settings.PASSWORD_RESET_TIMEOUT + 3599) // 3600)
    setup_url = (
        f'{settings.FRONTEND_BASE_URL.rstrip("/")}/reset-password'
        f'?uid={uid}&token={token}&purpose=invitation'
    )
    send_branded_mail(
        subject='Votre invitation DJIBEXA — choisissez votre mot de passe',
        message=(
            f'Bonjour {user.get_full_name() or user.username},\n\n'
            f'Votre espace {tenant.name} est activé. Votre compte administrateur est prêt.\n'
            f'Votre identifiant est : {user.username}\n\n'
            'Cliquez sur le bouton ci-dessous pour choisir votre mot de passe. '
            f'Ce lien est personnel, à usage unique et expire sous {validity_hours} heures.\n\n'
            f'Si le bouton ne fonctionne pas, copiez ce lien :\n{setup_url}\n\n'
            f'Si le lien a expiré, ouvrez {settings.FRONTEND_BASE_URL.rstrip("/")}/auth '
            'et utilisez « Mot de passe oublié ? » pour en recevoir un nouveau.\n\n'
            'Si vous ne vous attendiez pas à cette invitation, contactez '
            'l’administrateur de la plateforme.'
        ),
        recipient_list=[user.email],
        fail_silently=False,
        action_url=setup_url,
        action_label='Choisir mon mot de passe',
    )


def send_temporary_password_email(user, tenant, temporary_password=None):
    temporary_password = temporary_password or get_random_string(24)
    user.set_password(temporary_password)
    user.must_change_password = True
    user.save(update_fields=['password', 'must_change_password', 'updated_at'])
    access_message = (
        'Vous pourrez vous connecter dès que l’espace aura été activé par '
        'l’administrateur de la plateforme.'
        if not user.is_active
        else 'Vous pouvez vous connecter dès maintenant.'
    )
    send_branded_mail(
        subject='Votre accès DJIBEXA — mot de passe provisoire',
        message=(
            f'Bonjour {user.get_full_name() or user.username},\n\n'
            f'Votre compte pour l’espace {tenant.name} a été créé.\n'
            f'Votre identifiant est : {user.username}\n'
            f'Votre mot de passe provisoire est : {temporary_password}\n\n'
            'À votre première connexion, vous devrez obligatoirement choisir '
            f'un nouveau mot de passe avant d’accéder aux autres fonctions. {access_message}\n\n'
            'Si vous ne vous attendiez pas à la création de ce compte, '
            'contactez l’administrateur de votre entreprise.'
        ),
        recipient_list=[user.email],
        fail_silently=False,
    )
