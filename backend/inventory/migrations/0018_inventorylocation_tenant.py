import django.db.models.deletion
from django.db import migrations, models


def assign_existing_locations_to_default_tenant(apps, schema_editor):
    Tenant = apps.get_model('core', 'Tenant')
    InventoryLocation = apps.get_model('inventory', 'InventoryLocation')
    database = schema_editor.connection.alias

    tenant = Tenant.objects.using(database).filter(
        slug='kourouma-auto-parts',
    ).first()
    if tenant is None:
        return
    InventoryLocation.objects.using(database).filter(tenant__isnull=True).update(
        tenant_id=tenant.pk,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_platformsettings_tenant_company_tenant'),
        ('inventory', '0017_stockreplenishmentrequest_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventorylocation',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_locations',
                to='core.tenant',
            ),
        ),
        migrations.RunPython(
            assign_existing_locations_to_default_tenant,
            migrations.RunPython.noop,
        ),
    ]
