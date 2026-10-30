from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0002_product_cost_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='volume',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='product',
            name='weight',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
    ]
