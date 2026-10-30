from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_company'),
    ]

    operations = [
        migrations.CreateModel(
            name='SyncOperation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('local_id', models.CharField(max_length=120)),
                ('operation_type', models.CharField(max_length=30)),
                ('status', models.CharField(choices=[('accepted', 'Acceptée'), ('rejected', 'Rejetée')], max_length=20)),
                ('payload', models.JSONField(default=dict)),
                ('result', models.JSONField(default=dict)),
                ('error', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sync_operations', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='syncoperation',
            constraint=models.UniqueConstraint(fields=('user', 'local_id'), name='unique_sync_operation_per_user'),
        ),
    ]