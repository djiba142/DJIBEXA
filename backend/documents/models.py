from django.db import models
import uuid

from django.conf import settings
from sales.models import Sale
from products.models import Product


class Document(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('invoice', 'Facture'),
        ('receipt', 'Reçu'),
        ('purchase_order', 'Commande fournisseur'),
        ('supplier_file', 'Fichier fournisseur'),
        ('admin', 'Administratif'),
    ]

    STATUS_CHOICES = [
        ('active', 'Actif'),
        ('archived', 'Archivé'),
        ('deleted', 'Supprimé'),
    ]

    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=40, choices=DOCUMENT_TYPE_CHOICES, default='invoice')
    file_name = models.CharField(max_length=200, blank=True, default='')
    file_url = models.URLField(max_length=500, blank=True, default='')
    related_model = models.CharField(max_length=80, blank=True, default='')
    related_id = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class DeliveryNote(models.Model):
    STATUS_CHOICES = [
        ('prepared', 'Préparé'),
        ('delivered', 'Livré'),
        ('cancelled', 'Annulé'),
    ]

    reference = models.CharField(max_length=120, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='delivery_notes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='prepared')
    verification_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_notes_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.reference


class DeliveryNoteItem(models.Model):
    delivery_note = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='delivery_note_items')
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('delivery_note', 'product')
