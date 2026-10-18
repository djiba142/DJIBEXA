import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_platformsettings_tenant_company_tenant'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(
                    choices=[
                        ('create', 'Création'),
                        ('update', 'Mise à jour'),
                        ('activate', 'Activation'),
                        ('suspend', 'Suspension'),
                        ('resume', 'Reprise'),
                    ],
                    max_length=20,
                )),
                ('details', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='platform_audit_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('tenant', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='platform_audit_logs',
                    to='core.tenant',
                )),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
