from typing import Any, ClassVar

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    is_platform_admin = serializers.BooleanField(read_only=True)
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=User.ROLE_CHOICES),
        required=False,
    )

    class Meta:
        model = User
        fields: ClassVar[tuple[str, ...]] = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'roles',
            'is_platform_admin',
            'phone',
            'photo',
            'password',
            'pin_code',
            'preferred_language',
            'keyboard_layout',
            'is_active',
            'must_change_password',
            'created_at',
            'updated_at',
        )
        read_only_fields: ClassVar[tuple[str, ...]] = (
            'id',
            'is_platform_admin',
            'must_change_password',
            'created_at',
            'updated_at',
        )
        extra_kwargs: ClassVar[dict[str, dict[str, Any]]] = {
            'password': {'write_only': True, 'required': False},
            'pin_code': {'write_only': True},
        }

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError(
                'Le mot de passe doit contenir au moins 8 caractères.'
            )
        return value

    def validate_pin_code(self, value):
        if not value.isdigit() or not 4 <= len(value) <= 6:
            raise serializers.ValidationError(
                'Le code PIN doit contenir entre 4 et 6 chiffres.'
            )
        if value == '0000':
            raise serializers.ValidationError(
                'Le code PIN par défaut n’est pas autorisé.'
            )
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password') and not attrs.get('pin_code'):
            raise serializers.ValidationError({
                'password': 'Définissez un mot de passe ou un code PIN pour ce compte.',
            })
        assigned_roles = attrs.get('roles')
        role = attrs.get('role', self.instance.role if self.instance else 'sales')
        if assigned_roles is None:
            assigned_roles = (
                self.instance.roles
                if self.instance and 'role' not in attrs
                else [role]
            )
        assigned_roles = list(dict.fromkeys(assigned_roles))
        if not assigned_roles:
            raise serializers.ValidationError({
                'roles': 'Attribuez au moins une fonction à ce compte.',
            })
        if role not in assigned_roles:
            role = assigned_roles[0]
        attrs['role'] = role
        attrs['roles'] = assigned_roles
        is_active = attrs.get(
            'is_active',
            self.instance.is_active if self.instance else True,
        )
        allowed_roles = {choice[0] for choice in User.ROLE_CHOICES}
        if is_active and not set(assigned_roles).issubset(allowed_roles):
            raise serializers.ValidationError({
                'roles': 'Attribuez des fonctions valides avant de réactiver ce compte.',
            })
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['roles'] = instance.roles
        return data

    def create(self, validated_data):
        assigned_roles = validated_data.pop('roles', None)
        if assigned_roles is not None:
            primary_role = validated_data.get('role', assigned_roles[0])
            if primary_role not in assigned_roles:
                primary_role = assigned_roles[0]
            validated_data['role'] = primary_role
            validated_data['additional_roles'] = [
                role for role in assigned_roles if role != primary_role
            ]
        password = validated_data.pop('password', None)
        pin_code = validated_data.pop('pin_code', None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=['password', 'updated_at'])
        elif pin_code:
            user.set_pin(pin_code)
            user.save(update_fields=['pin_code', 'updated_at'])
        return user

    def update(self, instance, validated_data):
        assigned_roles = validated_data.pop('roles', None)
        if assigned_roles is not None:
            primary_role = validated_data.get('role', instance.role)
            if primary_role not in assigned_roles:
                primary_role = assigned_roles[0]
            validated_data['role'] = primary_role
            validated_data['additional_roles'] = [
                role for role in assigned_roles if role != primary_role
            ]
        password = validated_data.pop('password', None)
        pin_code = validated_data.pop('pin_code', None)
        old_photo_name = instance.photo.name if instance.photo else None
        photo_storage = instance.photo.storage if instance.photo else None
        instance = super().update(instance, validated_data)
        if (
            old_photo_name
            and old_photo_name != (instance.photo.name if instance.photo else None)
            and photo_storage
        ):
            photo_storage.delete(old_photo_name)
        if password:
            instance.set_password(password)
            instance.save(update_fields=['password', 'updated_at'])
        elif pin_code:
            instance.set_pin(pin_code)
            instance.save(update_fields=['pin_code', 'updated_at'])
        return instance

    def validate_photo(self, value):
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('La photo ne peut pas dépasser 5 Mo.')
        return value


class UserProfileSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        read_only_fields: ClassVar[tuple[str, ...]] = (
            'id',
            'username',
            'role',
            'roles',
            'is_active',
            'created_at',
            'updated_at',
        )


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=200)
    password = serializers.CharField(max_length=128, min_length=8, required=False, write_only=True)
    pin = serializers.CharField(max_length=6, min_length=4, required=False, write_only=True)

    def validate(self, attrs):
        password = attrs.get('password')
        pin = attrs.get('pin')
        if not password and not pin:
            raise serializers.ValidationError(
                {'password': 'Saisissez votre mot de passe.'}
            )
        if pin and not pin.isdigit():
            raise serializers.ValidationError(
                {'pin': 'Le code PIN historique doit contenir uniquement des chiffres.'}
            )
        return attrs


class LogoutResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class RegisterSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(max_length=300, write_only=True)
    password = serializers.CharField(max_length=128, min_length=8, write_only=True)
    email = serializers.EmailField()

    class Meta:
        model = User
        fields: ClassVar[tuple[str, ...]] = ('full_name', 'email', 'password')

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Cette adresse e-mail est déjà utilisée.')
        return value.lower()

    def create(self, validated_data):
        full_name = validated_data.pop('full_name').strip()
        name_parts = full_name.split(None, 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        username_base = validated_data['email'].split('@', 1)[0].lower()
        username = username_base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f'{username_base}{suffix}'

        user = User.objects.create_user(
            username=username,
            email=validated_data['email'],
            first_name=first_name,
            last_name=last_name,
            password=validated_data['password'],
            role='sales',
            is_active=False,
        )
        return user


class PinResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PinResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField()
    password = serializers.CharField(max_length=128, min_length=8, write_only=True)
