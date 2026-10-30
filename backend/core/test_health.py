from django.test import TestCase


class HealthCheckTests(TestCase):
    def test_health_check_confirms_database_connectivity(self):
        response = self.client.get('/healthz/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')
