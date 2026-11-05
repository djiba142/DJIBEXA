from typing import ClassVar

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import Tenant


class UserManager(DjangoUserManager):
    def _create_user(self, username, email, password, **extra_fields):
        pin_code = extra_fields.get('pin_code')
        if pin_code:
            try:
                identify_hasher(pin_code)
            except ValueError:
                extra_fields['pin_code'] = make_password(pin_code)
        return super()._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ('admin', 'Administrateur'),
        ('stock', 'Gestionnaire de stock'),
        ('sales', 'Vendeur'),
    ]

    LANGUAGE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ('fr', 'Français'),
        ('en', 'English'),
        ('ar', 'العربية'),
        ('zh', '中文'),
    ]
    KEYBOARD_LAYOUT_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ('fr', 'Français'),
        ('us', 'US'),
    ]

    role = models.CharField(max_length=40, choices=ROLE_CHOICES, default='sales')
    additional_roles = models.JSONField(default=list, blank=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
    )
    is_platform_admin = models.BooleanField(default=False)
    invitation_pending = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    phone = models.CharField(max_length=30, blank=True, default='')
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    pin_code = models.CharField(max_length=128, blank=True, default='')
    preferred_language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='fr',
    )
    keyboard_layout = models.CharField(
        max_length=10,
        choices=KEYBOARD_LAYOUT_CHOICES,
        default='fr',
    )
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        ordering: ClassVar[list[str]] = ['-created_at']

    def __str__(self):
        full_name = self.get_full_name()
        return full_name or self.username

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def roles(self):
        if self.is_platform_admin:
            return []
        return list(dict.fromkeys([self.role, *(self.additional_roles or [])]))

    def has_role(self, role):
        return role in self.roles

    def has_any_role(self, *roles):
        assigned = set(self.roles)
        return bool(assigned.intersection(roles))

    def set_pin(self, raw_pin):
        self.pin_code = make_password(raw_pin)

    def check_pin(self, raw_pin):
        if not raw_pin or raw_pin == '0000':
            return False
        if check_password(raw_pin, self.pin_code):
            return True
        return False
