from django.core.validators import (
	FileExtensionValidator,
	MaxValueValidator,
	MinValueValidator,
	RegexValidator,
)
from django.conf import settings
from django.db import models

from .storage import invoice_branding_asset_path, private_invoice_storage


def default_invoice_phone_numbers():
	return []


def default_invoice_email_addresses():
	return []


class InvoiceBranding(models.Model):
	ALIGNMENT_CHOICES = [('left', 'Gauche'), ('center', 'Centré')]
	LINE_DISPLAY_CHOICES = [('compact', 'Compact'), ('carnet', 'Carnet')]
	STAMP_POSITION_CHOICES = [
		('left', 'Gauche'),
		('center', 'Centre'),
		('right', 'Droite'),
	]

	tenant = models.OneToOneField(
		'core.Tenant',
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name='invoice_branding',
	)
	company_name = models.CharField(max_length=200, blank=True, default='')
	activity = models.CharField(max_length=240, blank=True, default='')
	distributor_details = models.TextField(blank=True, default='')
	address = models.CharField(max_length=240, blank=True, default='')
	phone_numbers = models.JSONField(default=default_invoice_phone_numbers, blank=True)
	email = models.EmailField(blank=True, default='')
	email_addresses = models.JSONField(default=default_invoice_email_addresses, blank=True)
	additional_lines = models.JSONField(default=list, blank=True)
	line_display_mode = models.CharField(
		max_length=12,
		choices=LINE_DISPLAY_CHOICES,
		default='compact',
	)
	header_alignment = models.CharField(max_length=10, choices=ALIGNMENT_CHOICES, default='center')
	header_color = models.CharField(
		max_length=7,
		default='#123D60',
		validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Utilisez une couleur hexadécimale #RRGGBB.')],
	)
	text_color = models.CharField(
		max_length=7,
		default='#FFFFFF',
		validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Utilisez une couleur hexadécimale #RRGGBB.')],
	)
	show_company_name = models.BooleanField(default=True)
	show_activity = models.BooleanField(default=True)
	show_distributor = models.BooleanField(default=True)
	show_address = models.BooleanField(default=True)
	show_phones = models.BooleanField(default=True)
	show_emails = models.BooleanField(default=True)
	show_rccm = models.BooleanField(default=True)
	show_nif = models.BooleanField(default=True)
	show_logo = models.BooleanField(default=True)
	show_automotive_image = models.BooleanField(default=True)
	show_watermark = models.BooleanField(default=True)
	show_stamp = models.BooleanField(default=True)
	show_seller_signature = models.BooleanField(default=True)
	show_qr = models.BooleanField(default=True)
	seller_signature_name = models.CharField(max_length=200, blank=True, default='')
	seller_signature_title = models.CharField(max_length=100, blank=True, default='')
	stamp_position = models.CharField(
		max_length=6,
		choices=STAMP_POSITION_CHOICES,
		default='center',
	)
	stamp_size_mm = models.PositiveSmallIntegerField(
		default=20,
		validators=[MinValueValidator(12), MaxValueValidator(26)],
	)
	stamp_opacity = models.PositiveSmallIntegerField(
		default=100,
		validators=[MinValueValidator(20), MaxValueValidator(100)],
	)
	logo_image = models.ImageField(
		upload_to=invoice_branding_asset_path,
		storage=private_invoice_storage,
		blank=True,
		validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
	)
	automotive_image = models.ImageField(
		upload_to=invoice_branding_asset_path,
		storage=private_invoice_storage,
		blank=True,
		validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
	)
	watermark_image = models.ImageField(
		upload_to=invoice_branding_asset_path,
		storage=private_invoice_storage,
		blank=True,
		validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
	)
	stamp_image = models.ImageField(
		upload_to=invoice_branding_asset_path,
		storage=private_invoice_storage,
		blank=True,
		validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
	)
	seller_signature_image = models.ImageField(
		upload_to=invoice_branding_asset_path,
		storage=private_invoice_storage,
		blank=True,
		validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
	)
	rccm = models.CharField(max_length=80, blank=True, default='')
	nif = models.CharField(max_length=80, blank=True, default='')
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='invoice_branding_updates',
	)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = 'identité des factures'
		verbose_name_plural = 'identité des factures'

	def __str__(self):
		return self.company_name
