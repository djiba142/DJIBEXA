import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0011_stocktransfercarton'),
        ('products', '0006_product_alternative_references'),
    ]

    operations = [
        migrations.CreateModel(
            name='SampleCarton',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(max_length=120, unique=True)),
                ('sample_count', models.PositiveIntegerField()),
                ('qr_code', models.CharField(max_length=200, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sample_cartons', to='inventory.inventorylocation')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sample_cartons', to='products.product')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
