import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from users.models import User


ENVIRONMENT_VARIABLES = (
    'DJANGO_BOOTSTRAP_ADMIN_USERNAME',
    'DJANGO_BOOTSTRAP_ADMIN_EMAIL',
    'DJANGO_BOOTSTRAP_ADMIN_PASSWORD',
)


class Command(BaseCommand):
    help = 'Crée le premier administrateur de plateforme à partir de secrets d’environnement.'

    def handle(self, *args, **options):
        if User.objects.filter(is_platform_admin=True).exists():
            self.stdout.write('Un administrateur de plateforme existe déjà; création ignorée.')
            return

        values = {
            name: os.getenv(name, '')
            for name in ENVIRONMENT_VARIABLES
        }
        for name in ENVIRONMENT_VARIABLES[:2]:
            values[name] = values[name].strip()
        if not any(value.strip() for value in values.values()):
            self.stdout.write('Bootstrap admin non configuré; aucune création effectuée.')
            return
        if not all(value.strip() for value in values.values()):
            missing = ', '.join(
                name for name, value in values.items() if not value.strip()
            )
            raise CommandError(
                f'Variables de bootstrap manquantes : {missing}.'
            )

        username = slugify(values['DJANGO_BOOTSTRAP_ADMIN_USERNAME'])
        email = values['DJANGO_BOOTSTRAP_ADMIN_EMAIL'].lower()
        password = values['DJANGO_BOOTSTRAP_ADMIN_PASSWORD']
        if not username:
            raise CommandError('Le nom d’utilisateur de bootstrap est invalide.')

        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(
                f'Le nom d’utilisateur "{username}" est déjà utilisé.'
            )
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError('Cette adresse e-mail est déjà associée à un compte.')

        user = User(
            username=username,
            email=email,
            is_platform_admin=True,
            is_staff=True,
            is_superuser=True,
            must_change_password=True,
        )
        try:
            user.full_clean(exclude=['password'])
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError(str(error)) from error

        with transaction.atomic():
            if User.objects.filter(is_platform_admin=True).exists():
                self.stdout.write(
                    'Un administrateur de plateforme existe déjà; création ignorée.'
                )
                return
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                is_platform_admin=True,
                must_change_password=True,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Administrateur de plateforme créé '
                f'(nom d’utilisateur : {username}).'
            )
        )
