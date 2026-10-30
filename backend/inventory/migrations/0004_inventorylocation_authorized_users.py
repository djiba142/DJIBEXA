from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_carton'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='inventorylocation',
            name='authorized_users',
            field=models.ManyToManyField(blank=True, related_name='authorized_inventory_locations', to=settings.AUTH_USER_MODEL),
        ),
    ]