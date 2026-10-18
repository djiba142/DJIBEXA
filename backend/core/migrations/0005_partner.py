from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_syncoperation'),
    ]

    operations = [
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('tagline', models.CharField(blank=True, default='', max_length=300)),
                ('logo_url', models.URLField(blank=True, default='', max_length=500)),
                ('phone', models.CharField(blank=True, default='', max_length=30)),
                ('whatsapp', models.CharField(blank=True, default='', max_length=30)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('website', models.URLField(blank=True, default='', max_length=500)),
                ('notes', models.TextField(blank=True, default='')),
                ('show_on_invoice', models.BooleanField(default=True)),
                ('show_on_orders', models.BooleanField(default=True)),
                ('active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AlterModelOptions(
            name='company',
            options={'verbose_name_plural': 'companies'},
        ),
    ]
