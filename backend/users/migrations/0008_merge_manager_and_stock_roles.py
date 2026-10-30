from django.db import migrations, models


def merge_roles(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(role='manager').update(role='stock')
    User.objects.filter(role='viewer').update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0007_user_profile_photo'),
    ]

    operations = [
        migrations.RunPython(merge_roles),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Administrateur'),
                    ('stock', 'Gestionnaire de stock'),
                    ('sales', 'Vendeur'),
                ],
                default='sales',
                max_length=40,
            ),
        ),
    ]
