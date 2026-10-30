from datetime import time

from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_settings_to_tenants(apps, schema_editor):
    Tenant = apps.get_model('core', 'Tenant')
    AppSetting = apps.get_model('core', 'AppSetting')
    TenantCreditReminderSettings = apps.get_model(
        'notifications',
        'TenantCreditReminderSettings',
    )
    database = schema_editor.connection.alias
    legacy = dict(
        AppSetting.objects.using(database).filter(
            key__in=[
                'credit_reminder_enabled',
                'credit_reminder_frequency',
                'credit_reminder_day_of_week',
                'credit_reminder_time',
            ],
        ).values_list('key', 'value')
    )

    enabled = legacy.get('credit_reminder_enabled', 'true').lower() == 'true'
    frequency = legacy.get('credit_reminder_frequency', 'weekly')
    if frequency != 'weekly':
        frequency = 'weekly'
    try:
        day_of_week = int(legacy.get('credit_reminder_day_of_week', '4'))
    except (TypeError, ValueError):
        day_of_week = 4
    if not 0 <= day_of_week <= 6:
        day_of_week = 4
    try:
        reminder_time = time.fromisoformat(
            legacy.get('credit_reminder_time', '17:00'),
        )
    except (TypeError, ValueError):
        reminder_time = time(17, 0)

    TenantCreditReminderSettings.objects.using(database).bulk_create([
        TenantCreditReminderSettings(
            tenant_id=tenant_id,
            enabled=enabled,
            frequency=frequency,
            day_of_week=day_of_week,
            time=reminder_time,
        )
        for tenant_id in Tenant.objects.using(database).values_list('pk', flat=True)
    ])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_tenantstorefront_draft_cover_and_more'),
        ('notifications', '0005_notification_tenant'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantCreditReminderSettings',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('enabled', models.BooleanField(default=True)),
                (
                    'frequency',
                    models.CharField(
                        choices=[('weekly', 'Hebdomadaire')],
                        default='weekly',
                        max_length=20,
                    ),
                ),
                ('day_of_week', models.PositiveSmallIntegerField(default=4)),
                ('time', models.TimeField(default=time(17, 0))),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'tenant',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='credit_reminder_settings',
                        to='core.tenant',
                    ),
                ),
            ],
            options={
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(('day_of_week__gte', 0), ('day_of_week__lte', 6)),
                        name='credit_reminder_day_in_week',
                    ),
                ],
            },
        ),
        migrations.RunPython(
            copy_legacy_settings_to_tenants,
            migrations.RunPython.noop,
        ),
    ]
