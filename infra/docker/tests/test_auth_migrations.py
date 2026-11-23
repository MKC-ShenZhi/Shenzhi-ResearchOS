import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from auth_migrations import load_auth_migrations, validate_auth_migrations


class AuthMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        # Synthetic SQL only: no real database or production migration edits.
        for name in ('001_better_auth.sql', '002_turnstile_verification.sql', '003_oauth_placeholder_scope.sql'):
            (self.directory / name).write_text('SELECT 1;\n', encoding='utf-8')

    def ledger(self):
        return [dict(name=name, sha256=digest) for name, _sql, digest in load_auth_migrations(self.directory)]

    def test_current_three_migrations(self):
        validate_auth_migrations(self.ledger(), load_auth_migrations(self.directory))

    def test_fourth_migration_discovered_without_smoke_changes(self):
        (self.directory / '004_fixture.sql').write_text('SELECT 4;\n')
        migrations = load_auth_migrations(self.directory)
        self.assertEqual(len(migrations), 4)
        validate_auth_migrations(self.ledger(), migrations)

    def test_missing_ledger_record(self):
        with self.assertRaisesRegex(RuntimeError, 'missing: 001_better_auth.sql'):
            validate_auth_migrations(self.ledger()[1:], load_auth_migrations(self.directory))

    def test_checksum_mismatch(self):
        ledger = self.ledger()
        ledger[0]['sha256'] = 'fixture-wrong-checksum'
        with self.assertRaisesRegex(RuntimeError, 'checksum mismatch: 001_better_auth.sql'):
            validate_auth_migrations(ledger, load_auth_migrations(self.directory))

    def test_unexpected_ledger_record(self):
        ledger = self.ledger() + [dict(name='999_unexpected.sql', sha256='fixture')]
        with self.assertRaisesRegex(RuntimeError, 'unexpected: 999_unexpected.sql'):
            validate_auth_migrations(ledger, load_auth_migrations(self.directory))

    def test_checksum_matches_existing_bom_and_newline_rules(self):
        (self.directory / '004_fixture.sql').write_bytes(b'\xef\xbb\xbfSELECT 4;\r\n')
        name, sql, digest = load_auth_migrations(self.directory)[-1]
        self.assertEqual(name, '004_fixture.sql')
        self.assertEqual(sql, 'SELECT 4;\n')
        self.assertEqual(digest, hashlib.sha256(b'SELECT 4;\n').hexdigest())

    def test_absent_migration_directory_fails_explicitly(self):
        with self.assertRaisesRegex(RuntimeError, 'No auth SQL migration files'):
            load_auth_migrations(self.directory / 'absent')


if __name__ == '__main__':
    unittest.main()
