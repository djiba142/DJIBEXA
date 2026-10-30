from django.db import migrations, models


def remove_default_tenant_limit(apps, schema_editor):
    PlatformSettings = apps.get_model('core', 'PlatformSettings')
    PlatformSettings.objects.using(schema_editor.connection.alias).update(
        max_tenants=None,
    )


def restore_default_tenant_limit(apps, schema_editor):
    PlatformSettings = apps.get_model('core', 'PlatformSettings')
    PlatformSettings.objects.using(schema_editor.connection.alias).update(
        max_tenants=10,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_platformtaskrun'),
    ]

    operations = [
        migrations.AlterField(
            model_name='platformsettings',
            name='max_tenants',
            field=models.PositiveIntegerField(
                blank=True,
                default=None,
                null=True,
            ),
        ),
        migrations.RunPython(
            remove_default_tenant_limit,
            restore_default_tenant_limit,
        ),
    ]
