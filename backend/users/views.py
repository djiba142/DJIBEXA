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

from core.models import AuditLog, PlatformSettings, Tenant
from core.mailer import send_branded_mail
from core.onboarding import send_temporary_password_email
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
        temporary_password = get_random_string(24)
        request_data = request.data.copy()
        request_data['password'] = temporary_password
        serializer = self.get_serializer(data=request_data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data.get('email'):
            raise serializers.ValidationError({
                'email': 'Une adresse e-mail est nécessaire pour envoyer le mot de passe provisoire.',
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
        send_temporary_password_email(user, tenant, temporary_password)
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
        user = User.objects.filter(email__iexact=serializer.validated_data['email'], is_active=True).first()
        response_data = {
            'success': True,
            'message': 'Si ce compte existe, les instructions ont été envoyées à cette adresse.',
        }
        if user:
            token = default_token_generator.make_token(user)
            reset_url = (
                f'{settings.FRONTEND_BASE_URL}/reset-password'
                f'?uid={urlsafe_base64_encode(force_bytes(user.pk))}&token={token}'
            )
            send_branded_mail(
                subject='Réinitialisation de votre mot de passe — DJIBEXA',
                message=(
                    f'Bonjour {user.display_name},\n\n'
                    'Une demande de réinitialisation du mot de passe de votre compte a été reçue.\n'
                    'Pour choisir un nouveau mot de passe, ouvrez ce lien :\n'
                    f'{reset_url}\n\n'
                    'Si vous n’êtes pas à l’origine de cette demande, ignorez cet e-mail.'
                ),
                recipient_list=[user.email],
                fail_silently=False,
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
        if not user or not default_token_generator.check_token(user, serializer.validated_data['token']):
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
            if tenant is None:
                return Response(
                    {
                        'success': False,
                        'message': 'L’espace de cette invitation est indisponible.',
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
        return Response({'success': True, 'message': 'Mot de passe réinitialisé. Vous pouvez vous connecter.'}, status=status.HTTP_200_OK)


@extend_schema_view(post=extend_schema(responses=LogoutResponseSerializer))
class LogoutView(APIView):
    serializer_class = LogoutResponseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        logout(request)
        return Response({'success': True, 'message': 'Déconnexion réussie.'}, status=status.HTTP_200_OK)
