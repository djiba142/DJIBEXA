import hashlib
import uuid

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import activate, get_language
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.crypto import get_random_string
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view

from core.models import (
    AuditLog,
    Invitation,
    PlatformSettings,
    Tenant,
    TenantMembership,
)
from core.onboarding import send_password_setup_email
from core.outbox import queue_branded_email
from .models import User
from .permissions import IsTenantAdminUser
from .serializers import LoginSerializer, LogoutResponseSerializer, PinResetConfirmSerializer, PinResetRequestSerializer, UserProfileSerializer, UserSerializer


class UserListView(generics.ListCreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdminUser]

    def get_queryset(self):
        return User.objects.filter(
            tenant_id=self.request.user.tenant_id,
            is_platform_admin=False,
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        if request.data.get('pin_code'):
            raise serializers.ValidationError({
                'pin_code': 'Le compte doit choisir ses identifiants depuis le lien d’invitation.',
            })
        request_data = request.data.copy()
        request_data['password'] = get_random_string(48)
        request_data.pop('pin_code', None)
        serializer = self.get_serializer(data=request_data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data.get('email'):
            raise serializers.ValidationError({
                'email': 'Une adresse e-mail est nécessaire pour envoyer l’invitation.',
            })
        tenant = Tenant.objects.select_for_update().get(pk=request.user.tenant_id)
        platform_settings = PlatformSettings.objects.select_for_update().get(pk=1)
        tenant_active_users = User.objects.filter(
            tenant=tenant,
            is_active=True,
        ).count()
        platform_active_users = User.objects.filter(
            is_active=True,
            is_platform_admin=False,
        ).count()
        if tenant_active_users >= tenant.max_users:
            raise serializers.ValidationError({
                'detail': 'La limite d’utilisateurs actifs de votre espace est atteinte.',
            })
        if (
            platform_settings.max_active_users is not None
            and platform_active_users >= platform_settings.max_active_users
        ):
            raise serializers.ValidationError({
                'detail': 'La limite globale d’utilisateurs actifs est atteinte.',
            })
        user = serializer.save(tenant=tenant, must_change_password=True)
        user.set_unusable_password()
        user.invitation_pending = True
        user.save(update_fields=[
            'password',
            'invitation_pending',
            'must_change_password',
            'updated_at',
        ])
        role = user.role if user.role in dict(TenantMembership.ROLE_CHOICES) else 'other'
        TenantMembership.objects.create(
            tenant=tenant,
            user=user,
            role=role,
            is_active=False,
            is_primary_admin=(
                role == 'admin'
                and not TenantMembership.objects.filter(
                    tenant=tenant,
                    is_primary_admin=True,
                ).exists()
            ),
        )
        send_password_setup_email(user, tenant, created_by=request.user)
        AuditLog.objects.create(
            user=request.user,
            action='create',
            model_name='User',
            record_id=user.id,
            details=f"Utilisateur créé: {user.display_name}",
        )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdminUser]

    def get_queryset(self):
        return User.objects.filter(
            tenant_id=self.request.user.tenant_id,
            is_platform_admin=False,
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        will_activate = (
            not instance.is_active
            and serializer.validated_data.get('is_active', instance.is_active)
        )
        requested_role = serializer.validated_data.get('role', instance.role)
        membership = TenantMembership.objects.select_for_update().filter(
            tenant_id=instance.tenant_id,
            user=instance,
        ).first()
        if (
            membership
            and membership.is_primary_admin
            and (
                requested_role != 'admin'
                or not serializer.validated_data.get('is_active', instance.is_active)
            )
        ):
            raise serializers.ValidationError({
                'detail': 'Transférez le rôle d’administrateur principal avant de modifier ce compte.',
            })
        if will_activate:
            tenant = Tenant.objects.select_for_update().get(
                pk=request.user.tenant_id,
            )
            platform_settings = PlatformSettings.objects.select_for_update().get(pk=1)
            tenant_active_users = User.objects.filter(
                tenant=tenant,
                is_active=True,
            ).count()
            platform_active_users = User.objects.filter(
                is_active=True,
                is_platform_admin=False,
            ).count()
            if tenant_active_users >= tenant.max_users:
                raise serializers.ValidationError({
                    'detail': 'La limite d’utilisateurs actifs de votre espace est atteinte.',
                })
            if (
                platform_settings.max_active_users is not None
                and platform_active_users >= platform_settings.max_active_users
            ):
                raise serializers.ValidationError({
                    'detail': 'La limite globale d’utilisateurs actifs est atteinte.',
                })
        user = serializer.save()
        membership_role = (
            user.role
            if user.role in dict(TenantMembership.ROLE_CHOICES)
            else 'other'
        )
        if membership is None:
            TenantMembership.objects.create(
                tenant_id=user.tenant_id,
                user=user,
                role=membership_role,
                is_active=user.is_active and not user.invitation_pending,
                is_primary_admin=(
                    membership_role == 'admin'
                    and not TenantMembership.objects.filter(
                        tenant_id=user.tenant_id,
                        is_active=True,
                        is_primary_admin=True,
                    ).exists()
                ),
            )
        else:
            membership.role = membership_role
            membership.is_active = user.is_active and not user.invitation_pending
            if membership_role != 'admin':
                membership.is_primary_admin = False
            membership.save()
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='User',
            record_id=user.id,
            details=f"Utilisateur mis à jour: {user.display_name}",
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'La suppression physique d’un utilisateur est interdite. Utilisez la désactivation.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class UserMeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        new_language = serializer.validated_data.get('preferred_language', instance.preferred_language)
        new_keyboard = serializer.validated_data.get('keyboard_layout', instance.keyboard_layout)

        instance = serializer.save()
        instance.preferred_language = new_language
        instance.keyboard_layout = new_keyboard
        instance.save(update_fields=['preferred_language', 'keyboard_layout'])

        request.session['django_language'] = new_language
        request.session['keyboard_layout'] = new_keyboard
        activate(new_language)
        if hasattr(request, 'user'):
            request.user = instance

        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: UserSerializer})
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data['identifier']
        password = serializer.validated_data.get('password')
        legacy_pin = serializer.validated_data.get('pin')

        user = User.objects.filter(username=identifier).first()
        if user is None:
            user = User.objects.filter(email=identifier).first()
        if user is None:
            user = User.objects.filter(phone=identifier).first()

        if user is None:
            return Response({'success': False, 'message': 'Identifiant introuvable.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'success': False, 'message': 'Compte inactif.'}, status=status.HTTP_401_UNAUTHORIZED)

        if user.invitation_pending:
            return Response(
                {
                    'success': False,
                    'message': 'Activez votre compte avec le lien reçu par e-mail.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.locked_until and user.locked_until > timezone.now():
            return Response({'success': False, 'message': 'Compte temporairement bloqué. Réessayez plus tard.'}, status=status.HTTP_403_FORBIDDEN)

        credentials_valid = user.check_password(password) if password else user.check_pin(legacy_pin)
        if not credentials_valid:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = timezone.now() + timezone.timedelta(minutes=15)
                user.failed_login_attempts = 0
                user.save(update_fields=['failed_login_attempts', 'locked_until'])
                return Response({'success': False, 'message': 'Compte bloqué temporairement après 5 échecs de connexion.'}, status=status.HTTP_403_FORBIDDEN)
            user.save(update_fields=['failed_login_attempts'])
            message = 'Code PIN incorrect.' if legacy_pin else 'Mot de passe incorrect.'
            return Response({'success': False, 'message': message}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_platform_admin:
            from core.tenancy import tenant_for_user

            tenant = tenant_for_user(user)
            if tenant is None or tenant.status_at() != 'active':
                return Response(
                    {
                        'success': False,
                        'message': 'L’espace est en attente, suspendu ou sa licence a expiré.',
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=['failed_login_attempts', 'locked_until'])

        login(request, user)
        AuditLog.objects.create(
            user=user,
            action='login',
            model_name='User',
            record_id=user.id,
            details=f'Connexion réussie pour {user.display_name}',
        )
        return Response({
            'success': True,
            'message': 'Connexion réussie.',
            'user': UserSerializer(user, context={'request': request}).data,
        }, status=status.HTTP_200_OK)


class RequiredPasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.must_change_password:
            return Response(
                {'detail': 'Aucun changement obligatoire de mot de passe n’est en attente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        if not isinstance(current_password, str) or not user.check_password(current_password):
            return Response(
                {'current_password': 'Le mot de passe provisoire est incorrect.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(new_password, str) or len(new_password) < 8:
            return Response(
                {'new_password': 'Le mot de passe doit contenir au moins 8 caractères.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({'new_password': error.messages}) from error

        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password', 'updated_at'])
        update_session_auth_hash(request, user)
        return Response({
            'success': True,
            'message': 'Mot de passe modifié.',
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class PinResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=PinResetRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, *args, **kwargs):
        serializer = PinResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data['email'],
            is_active=True,
        ).first()
        response_data = {
            'success': True,
            'message': 'Si ce compte existe, les instructions ont été envoyées à cette adresse.',
        }
        if user:
            if user.invitation_pending and user.tenant_id:
                if user.tenant.status_at() == 'active':
                    send_password_setup_email(user, user.tenant)
            else:
                token = default_token_generator.make_token(user)
                reset_url = (
                    f'{settings.FRONTEND_BASE_URL.rstrip("/")}/reset-password'
                    f'?uid={urlsafe_base64_encode(force_bytes(user.pk))}&token={token}'
                )
                queue_branded_email(
                    subject='Réinitialisation de votre mot de passe — DJIBEXA',
                    message=(
                        f'Bonjour {user.display_name},\n\n'
                        'Une demande de réinitialisation du mot de passe de votre compte a été reçue.\n'
                        'Pour choisir un nouveau mot de passe, utilisez le bouton ci-dessous.\n\n'
                        f'Si le bouton ne fonctionne pas, copiez ce lien :\n{reset_url}\n\n'
                        'Si vous n’êtes pas à l’origine de cette demande, ignorez cet e-mail.'
                    ),
                    recipient=user.email,
                    idempotency_key=f'password-reset:{uuid.uuid4()}',
                    action_url=reset_url,
                    action_label='Choisir un nouveau mot de passe',
                )
        return Response(response_data, status=status.HTTP_200_OK)


class PinResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=PinResetConfirmSerializer, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = PinResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user_id = int(urlsafe_base64_decode(serializer.validated_data['uid']))
        except (TypeError, ValueError):
            user_id = None
        user = User.objects.select_for_update().filter(pk=user_id).first() if user_id else None
        if user and not user.is_active and not user.invitation_pending:
            user = None
        token = serializer.validated_data['token']
        invitation = None
        if user and user.invitation_pending:
            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
            invitation = Invitation.objects.select_for_update().filter(
                user=user,
                token_hash=token_hash,
                used_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).first()
        valid_token = (
            invitation is not None
            if user and user.invitation_pending
            else bool(user and default_token_generator.check_token(user, token))
        )
        if not user or not valid_token:
            return Response({'success': False, 'message': 'Le lien de réinitialisation est invalide ou expiré.'}, status=status.HTTP_400_BAD_REQUEST)
        password = serializer.validated_data['password']
        try:
            validate_password(password, user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({'password': error.messages}) from error
        if user.invitation_pending:
            tenant = (
                Tenant.objects.select_for_update().filter(pk=user.tenant_id).first()
                if user.tenant_id
                else None
            )
            if tenant is None or tenant.status_at() != 'active':
                return Response(
                    {
                        'success': False,
                        'message': 'L’espace de cette invitation n’est pas disponible.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            tenant_active_users = User.objects.filter(
                tenant=tenant,
                is_active=True,
                is_platform_admin=False,
            ).exclude(pk=user.pk).count()
            if tenant_active_users >= tenant.max_users:
                return Response(
                    {
                        'success': False,
                        'message': 'La capacité d’utilisateurs de cet espace est atteinte.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            platform_settings = PlatformSettings.objects.select_for_update().get(pk=1)
            if platform_settings.max_active_users is not None:
                platform_active_users = User.objects.filter(
                    is_active=True,
                    is_platform_admin=False,
                ).exclude(pk=user.pk).count()
                if platform_active_users >= platform_settings.max_active_users:
                    return Response(
                        {
                            'success': False,
                            'message': 'La limite globale d’utilisateurs actifs est atteinte.',
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            invitation.used_at = timezone.now()
            invitation.revoked_at = invitation.used_at
            invitation.save(update_fields=['used_at', 'revoked_at'])
        user.set_password(password)
        user.is_active = True
        user.invitation_pending = False
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=[
            'password',
            'is_active',
            'invitation_pending',
            'must_change_password',
            'failed_login_attempts',
            'locked_until',
            'updated_at',
        ])
        if invitation is not None:
            membership = TenantMembership.objects.select_for_update().filter(
                tenant_id=user.tenant_id,
                user=user,
            ).first()
            if membership is None:
                role = user.role if user.role in dict(TenantMembership.ROLE_CHOICES) else 'other'
                membership = TenantMembership(
                    tenant_id=user.tenant_id,
                    user=user,
                    role=role,
                    is_primary_admin=(
                        role == 'admin'
                        and not TenantMembership.objects.filter(
                            tenant_id=user.tenant_id,
                            is_primary_admin=True,
                        ).exists()
                    ),
                )
            membership.is_active = True
            membership.save()
        return Response({'success': True, 'message': 'Mot de passe réinitialisé. Vous pouvez vous connecter.'}, status=status.HTTP_200_OK)


@extend_schema_view(post=extend_schema(responses=LogoutResponseSerializer))
class LogoutView(APIView):
    serializer_class = LogoutResponseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        logout(request)
        return Response({'success': True, 'message': 'Déconnexion réussie.'}, status=status.HTTP_200_OK)
