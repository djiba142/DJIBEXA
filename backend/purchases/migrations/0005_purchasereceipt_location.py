from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0001_initial'),
        ('purchases', '0004_purchasereceipt_allocation_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchasereceipt',
            name='location',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='purchase_receipts',
                to='inventory.inventorylocation',
            ),
        ),
    ]
