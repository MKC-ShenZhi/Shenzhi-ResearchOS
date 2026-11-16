import unittest
from unittest.mock import patch

from starlette.requests import Request

from app.core.errors import BusinessError
from app.core.identity import migration_identity, request_identity, request_owner


def request(headers: dict[str, str], host: str = '127.0.0.1') -> Request:
    return Request({
        'type': 'http',
        'headers': [(key.encode(), value.encode()) for key, value in headers.items()],
        'client': (host, 12345),
    })


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict('os.environ', {'BACKEND_BFF_SECRET': 'shared-secret'})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_authenticated_identity_is_reusable_and_owner_is_derived(self):
        headers = {'x-shenzhi-bff-secret': 'shared-secret', 'x-shenzhi-user-id': 'user-1'}
        identity = request_identity(request(headers))
        self.assertEqual((identity.kind, identity.subject_id), ('user', 'user-1'))
        self.assertEqual(request_owner(request(headers)), 'user:user-1')

    def test_anonymous_identity_is_canonicalized(self):
        headers = {'x-shenzhi-bff-secret': 'shared-secret', 'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'}
        identity = request_identity(request(headers))
        self.assertEqual((identity.kind, identity.subject_id), ('anonymous', '00000000-0000-4000-8000-000000000001'))

    def test_rejects_missing_or_ambiguous_identity_and_invalid_values(self):
        base = {'x-shenzhi-bff-secret': 'shared-secret'}
        cases = [
            base,
            {**base, 'x-shenzhi-user-id': 'user-1', 'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'},
            {**base, 'x-shenzhi-user-id': ' user-1 '},
            {**base, 'x-shenzhi-user-id': 'x' * 256},
            {**base, 'x-shenzhi-anonymous-id': 'not-a-uuid'},
        ]
        for headers in cases:
            with self.subTest(headers=headers), self.assertRaises(BusinessError) as caught:
                request_identity(request(headers))
            self.assertEqual(caught.exception.status, 401)

    def test_rejects_wrong_bff_secret(self):
        with self.assertRaises(BusinessError) as caught:
            request_identity(request({'x-shenzhi-bff-secret': 'wrong', 'x-shenzhi-user-id': 'user-1'}))
        self.assertEqual(caught.exception.status, 401)

    def test_migration_identity_requires_trusted_target_and_source(self):
        headers = {
            'x-shenzhi-bff-secret': 'shared-secret',
            'x-shenzhi-user-id': 'user-1',
            'x-shenzhi-source-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }
        identity = migration_identity(request(headers))
        self.assertEqual(identity.target_owner, 'user:user-1')
        self.assertEqual(identity.source_owner, 'anon:00000000-0000-4000-8000-000000000001')

        for invalid in (
            {key: value for key, value in headers.items() if key != 'x-shenzhi-user-id'},
            {key: value for key, value in headers.items() if key != 'x-shenzhi-source-anonymous-id'},
            {**headers, 'x-shenzhi-source-anonymous-id': 'not-a-uuid'},
        ):
            with self.subTest(headers=invalid), self.assertRaises(BusinessError) as caught:
                migration_identity(request(invalid))
            self.assertEqual(caught.exception.status, 401)


if __name__ == '__main__':
    unittest.main()
