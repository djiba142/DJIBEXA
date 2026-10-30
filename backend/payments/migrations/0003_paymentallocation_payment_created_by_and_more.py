import django.conf
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models
import django.utils.timezone


def create_existing_payment_allocations(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    PaymentAllocation = apps.get_model('payments', 'PaymentAllocation')
    for payment in Payment.objects.filter(sale__isnull=False).iterator():
        PaymentAllocation.objects.get_or_create(
            payment_id=payment.id,
            sale_id=payment.sale_id,
            defaults={'amount': payment.amount},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_payment_financial_account'),
        ('sales', '0008_sale_discount'),
        migrations.swappable_dependency(django.conf.settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='payment_date',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='payment',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='customer_payments_created',
                to=django.conf.settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='PaymentAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('payment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='allocations',
                    to='payments.payment',
                )),
                ('sale', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='payment_allocations',
                    to='sales.sale',
                )),
            ],
            options={'ordering': ['created_at', 'id']},
        ),
        migrations.AddConstraint(
            model_name='paymentallocation',
            constraint=models.UniqueConstraint(
                fields=('payment', 'sale'),
                name='unique_payment_sale_allocation',
            ),
        ),
        migrations.AddConstraint(
            model_name='paymentallocation',
            constraint=models.CheckConstraint(
                condition=models.Q(('amount__gt', Decimal('0'))),
                name='payment_allocation_amount_positive',
            ),
        ),
        migrations.RunPython(
            create_existing_payment_allocations,
            migrations.RunPython.noop,
        ),
    ]
