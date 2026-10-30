from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_inventorylocation_authorized_users'),
        ('sales', '0003_sale_external_reference_sale_external_supplier_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='inventory.inventorylocation'),
        ),
    ]