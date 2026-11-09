from django.db import migrations, models


def ensure_trial_duration_months_column(apps, schema_editor):
    tenant_model = apps.get_model('core', 'Tenant')
    field_name = 'trial_duration_months'
    with schema_editor.connection.cursor() as cursor:
        columns = schema_editor.connection.introspection.get_table_description(
            cursor,
            tenant_model._meta.db_table,
        )
    if any(column.name == field_name for column in columns):
        return

    field = models.PositiveSmallIntegerField(default=3)
    field.set_attributes_from_name(field_name)
    field.model = tenant_model
    schema_editor.add_field(tenant_model, field)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0013_platformdemorequest'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_trial_duration_months_column,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='tenant',
                    name='trial_duration_months',
                    field=models.PositiveSmallIntegerField(default=3),
                ),
            ],
        ),
    ]
