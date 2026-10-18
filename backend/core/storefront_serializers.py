from collections.abc import Mapping
from pathlib import Path

from rest_framework import serializers


MAX_STOREFRONT_IMAGE_SIZE = 5 * 1024 * 1024
MAX_STOREFRONT_IMAGE_PIXELS = 16_000_000
SUPPORTED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = set(data) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError({
                    field: 'Ce champ n’est pas pris en charge.'
                    for field in sorted(unknown_fields)
                })
        return super().to_internal_value(data)


class StorefrontSectionsSerializer(StrictSerializer):
    about = serializers.BooleanField()
    services = serializers.BooleanField()
    categories = serializers.BooleanField()
    contact = serializers.BooleanField()


class StorefrontContentSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200, allow_blank=False, trim_whitespace=True)
    industry = serializers.CharField(max_length=120, allow_blank=True, trim_whitespace=True)
    tagline = serializers.CharField(max_length=240, allow_blank=True, trim_whitespace=True)
    description = serializers.CharField(max_length=2000, allow_blank=True, trim_whitespace=True)
    phone = serializers.CharField(max_length=30, allow_blank=True, trim_whitespace=True)
    email = serializers.EmailField(allow_blank=True)
    address = serializers.CharField(max_length=240, allow_blank=True, trim_whitespace=True)
    city = serializers.CharField(max_length=120, allow_blank=True, trim_whitespace=True)
    primary_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$')
    accent_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$')
    services = serializers.ListField(
        child=serializers.CharField(max_length=120, allow_blank=False, trim_whitespace=True),
        max_length=12,
    )
    categories = serializers.ListField(
        child=serializers.CharField(max_length=120, allow_blank=False, trim_whitespace=True),
        max_length=20,
    )
    sections = StorefrontSectionsSerializer()

    def validate_services(self, value):
        if any(not item for item in value):
            raise serializers.ValidationError('Chaque service doit contenir un libellé.')
        if len({item.casefold() for item in value}) != len(value):
            raise serializers.ValidationError('Les services ne doivent pas être en double.')
        return value

    def validate_categories(self, value):
        if any(not item for item in value):
            raise serializers.ValidationError('Chaque catégorie doit contenir un libellé.')
        if len({item.casefold() for item in value}) != len(value):
            raise serializers.ValidationError('Les catégories ne doivent pas être en double.')
        return value


class StorefrontAssetSerializer(StrictSerializer):
    image = serializers.ImageField()

    def validate_image(self, value):
        if value.size > MAX_STOREFRONT_IMAGE_SIZE:
            raise serializers.ValidationError('La taille maximale d’une image est de 5 Mo.')
        image = getattr(value, 'image', None)
        if image is None or image.format not in SUPPORTED_IMAGE_FORMATS:
            raise serializers.ValidationError('Utilisez une image PNG, JPEG ou WebP valide.')
        extension = Path(value.name).suffix.lower()
        valid_extensions = {
            'JPEG': {'.jpg', '.jpeg'},
            'PNG': {'.png'},
            'WEBP': {'.webp'},
        }
        if extension not in valid_extensions[image.format]:
            raise serializers.ValidationError('L’extension du fichier ne correspond pas à son image.')
        if image.width * image.height > MAX_STOREFRONT_IMAGE_PIXELS:
            raise serializers.ValidationError('L’image ne peut pas dépasser 16 millions de pixels.')
        return value
