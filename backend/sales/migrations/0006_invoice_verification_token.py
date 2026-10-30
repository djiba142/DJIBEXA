import uuid

from django.db import migrations, models


def populate_invoice_qr_codes(apps, schema_editor):
    Invoice = apps.get_model('sales', 'Invoice')
    for invoice in Invoice.objects.all().iterator():
        token_prefix = str(invoice.verification_token).replace('-', '')[:8].upper()
        invoice.qr_code = f'NEXORA-INV-{invoice.invoice_number}-{token_prefix}'
        invoice.save(update_fields=['qr_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0005_sale_seller'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='verification_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.RunPython(populate_invoice_qr_codes, migrations.RunPython.noop),
    ]