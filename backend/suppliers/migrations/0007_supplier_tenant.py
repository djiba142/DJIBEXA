import django.db.models.deletion
from django.db import migrations, models


def assign_existing_suppliers_to_default_tenant(apps, schema_editor):
    Tenant = apps.get_model('core', 'Tenant')
    Supplier = apps.get_model('suppliers', 'Supplier')
    database = schema_editor.connection.alias

    tenant = Tenant.objects.using(database).filter(
        slug='kourouma-auto-parts',
    ).first()
    if tenant is None:
        return
    Supplier.objects.using(database).filter(tenant__isnull=True).update(
        tenant_id=tenant.pk,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_platformsettings_tenant_company_tenant'),
        ('suppliers', '0006_alter_exchangerate_unique_together_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplier',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='suppliers',
                to='core.tenant',
            ),
        ),
        migrations.RunPython(
            assign_existing_suppliers_to_default_tenant,
            migrations.RunPython.noop,
        ),
    ]
