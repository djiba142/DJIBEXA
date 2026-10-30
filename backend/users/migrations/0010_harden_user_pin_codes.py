from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import migrations, models


def normalize_pin_codes(apps, schema_editor):
    User = apps.get_model('users', 'User')
    database = schema_editor.connection.alias

    for user in User.objects.using(database).only('pk', 'pin_code').iterator():
        pin_code = user.pin_code or ''
        if not pin_code:
            continue

        if pin_code == '0000' or check_password('0000', pin_code):
            user.pin_code = ''
        else:
            try:
                identify_hasher(pin_code)
            except ValueError:
                user.pin_code = make_password(pin_code)
            else:
                continue

        user.save(using=database, update_fields=['pin_code'])


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0009_user_additional_roles'),
    ]

    operations = [
        migrations.RunPython(normalize_pin_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='pin_code',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
