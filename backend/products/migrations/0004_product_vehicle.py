from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_product_weight_volume'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='vehicle',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
