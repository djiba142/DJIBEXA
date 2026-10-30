from django.utils.crypto import get_random_string

from .mailer import send_branded_mail


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
