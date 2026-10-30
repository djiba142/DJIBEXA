import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0001_initial'),
        ('notifications', '0002_notification_is_read_notification_read_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'En attente'),
                    ('sent', 'Envoyé'),
                    ('failed', 'Échec'),
                    ('retry', 'Retry'),
                    ('cancelled', 'Annulé'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='attempt_count',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='notification',
            name='last_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='notification',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='notification',
            name='reminder_period',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
        migrations.AddField(
            model_name='notification',
            name='customer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notifications',
                to='customers.customer',
            ),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(
                condition=models.Q(('event_type', 'credit_reminder'), ('reminder_period__gt', '')),
                fields=('customer', 'reminder_period', 'event_type', 'channel'),
                name='unique_customer_credit_reminder_period',
            ),
        ),
    ]
