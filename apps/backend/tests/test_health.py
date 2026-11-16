import unittest

from fastapi.testclient import TestClient

from app.main import app


class HealthRouteTests(unittest.TestCase):
    def test_unversioned_health(self):
        with TestClient(app) as client:
            response = client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_versioned_health_matches_web_bff_contract(self):
        with TestClient(app) as client:
            response = client.get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
