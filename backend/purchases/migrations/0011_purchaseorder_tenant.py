import django.db.models.deletion
from django.db import migrations, models


def assign_existing_orders_to_supplier_tenant(apps, schema_editor):
    PurchaseOrder = apps.get_model('purchases', 'PurchaseOrder')
    database = schema_editor.connection.alias
    orders = PurchaseOrder.objects.using(database).filter(
        tenant__isnull=True,
        supplier__tenant__isnull=False,
    ).values_list('pk', 'supplier__tenant_id')
    for order_id, tenant_id in orders.iterator():
        PurchaseOrder.objects.using(database).filter(pk=order_id).update(
            tenant_id=tenant_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('purchases', '0010_purchaseorder_exchange_rate_applied_at_and_more'),
        ('suppliers', '0007_supplier_tenant'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='purchase_orders',
                to='core.tenant',
            ),
        ),
        migrations.RunPython(
            assign_existing_orders_to_supplier_tenant,
            migrations.RunPython.noop,
        ),
    ]
