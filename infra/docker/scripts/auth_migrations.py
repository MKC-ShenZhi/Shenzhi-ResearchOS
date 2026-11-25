"""Shared SQL discovery/checksum rules for auth migration and smoke checks."""
import hashlib
from pathlib import Path


def load_auth_migrations(directory=Path('/opt/auth-migrations')):
    migrations = []
    for path in sorted(directory.glob('*.sql')):
        # Match the existing migration ledger: strip UTF-8 BOM, normalize
        # platform line endings through read_text, then hash UTF-8 SQL text.
        sql = path.read_text(encoding='utf-8-sig')
        migrations.append((path.name, sql, hashlib.sha256(sql.encode()).hexdigest()))
    if not migrations:
        raise RuntimeError('No auth SQL migration files found')
    return migrations


def validate_auth_migrations(records, migrations):
    expected = {name: digest for name, _sql, digest in migrations}
    actual = {row['name']: row['sha256'] for row in records}
    problems = []
    for label, names in (
        ('missing', expected.keys() - actual.keys()),
        ('unexpected', actual.keys() - expected.keys()),
        ('checksum mismatch', {name for name in expected.keys() & actual.keys()
                               if expected[name] != actual[name]}),
    ):
        if names:
            problems.append(f'{label}: {", ".join(sorted(names))}')
    if problems:
        raise RuntimeError('Auth migration ledger mismatch; ' + '; '.join(problems))
