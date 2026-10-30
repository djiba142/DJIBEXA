from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('contact_name', models.CharField(blank=True, default='', max_length=200)),
                ('phone', models.CharField(blank=True, default='', max_length=30)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('address', models.TextField(blank=True, default='')),
                ('company_name', models.CharField(blank=True, default='', max_length=200)),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
    ]
