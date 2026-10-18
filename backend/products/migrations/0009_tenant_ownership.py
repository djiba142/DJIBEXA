import django.db.models.deletion
from django.db import migrations, models


def assign_existing_catalogue_to_default_tenant(apps, schema_editor):
    Tenant = apps.get_model('core', 'Tenant')
    Category = apps.get_model('products', 'Category')
    Product = apps.get_model('products', 'Product')
    ProductCatalogImport = apps.get_model('products', 'ProductCatalogImport')
    database = schema_editor.connection.alias

    tenant = Tenant.objects.using(database).filter(
        slug='kourouma-auto-parts',
    ).first()
    if tenant is None:
        return

    for model in (Category, Product, ProductCatalogImport):
        model.objects.using(database).filter(tenant__isnull=True).update(
            tenant_id=tenant.pk,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_platformsettings_tenant_company_tenant'),
        ('products', '0008_productcatalogimport'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='product_categories',
                to='core.tenant',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='core.tenant',
            ),
        ),
        migrations.AddField(
            model_name='productcatalogimport',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='product_catalog_imports',
                to='core.tenant',
            ),
        ),
        migrations.RunPython(
            assign_existing_catalogue_to_default_tenant,
            migrations.RunPython.noop,
        ),
    ]
