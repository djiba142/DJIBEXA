from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0008_merge_manager_and_stock_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='additional_roles',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
