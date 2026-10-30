from django.apps import apps
from django.test.runner import DiscoverRunner


class NexoraTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        Tenant = apps.get_model('core', 'Tenant')
        Tenant.objects.using('default').get_or_create(
            slug='kourouma-auto-parts',
            defaults={'name': 'Kourouma Auto Parts', 'status': 'active'},
        )
        return old_config
