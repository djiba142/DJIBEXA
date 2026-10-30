from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_idempotencyrecord'),
    ]

    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('legal_name', models.CharField(blank=True, default='', max_length=240)),
                ('phone', models.CharField(blank=True, default='', max_length=30)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('address', models.TextField(blank=True, default='')),
                ('currency', models.CharField(default='GNF', max_length=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]