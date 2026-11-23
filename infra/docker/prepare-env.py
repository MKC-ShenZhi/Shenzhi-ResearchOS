"""Create ignored Docker config without changing native files or existing values.

Python 3.12+, standard library only. Run from any directory. --from-local imports
only keys declared in Docker examples; no secret values are printed.
"""
import argparse
import re
import secrets
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=(.*)$', line)
        if not match:
            continue
        key, value = match.groups()
        value = value.strip()
        if value.startswith(('"', "'")):
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise ValueError(f'{path.name}: multiline/ambiguous value for {key}; configure manually')
            value = value[1:-1]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def save(path, values, compose=False):
    # Compose .env uses interpolation; app files use env_file format: raw.
    text = '\n'.join(f"{key}={chr(39) + value + chr(39) if compose else value}"
                     for key, value in values.items()) + '\n'
    path.write_text(text, encoding='utf-8', newline='\n')
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-local', action='store_true')
    args = parser.parse_args()
    paths = {name: HERE / 'env' / f'{name}.env' for name in ('web', 'backend', 'agent')}
    existing = {name: read(path) for name, path in paths.items()}
    originals = {name: read(ROOT / 'apps' / name / ('.env.local' if name == 'web' else '.env'))
                 if args.from_local else {} for name in paths}
    values = {}
    for name, path in paths.items():
        defaults = read(path.with_suffix('.env.example'))
        values[name] = {key: originals[name].get(key) or value for key, value in defaults.items()}
        values[name].update(existing[name])
    # Empty BASE_URL overrides disable the registry default, so import only
    # explicitly configured nonempty Provider overrides.
    for provider in ('DASHSCOPE', 'DEEPSEEK', 'ZHIPU', 'AUTODL'):
        for suffix in ('BASE_URL', 'MODEL'):
            key = f'{provider}_{suffix}'
            if originals['agent'].get(key) and key not in existing['agent']:
                values['agent'][key] = originals['agent'][key]

    compose = read(HERE / '.env.example')
    compose.update(read(HERE / '.env'))
    compose['POSTGRES_PASSWORD'] = compose['POSTGRES_PASSWORD'] or secrets.token_hex(24)
    # Safe URL components; no ambiguous quoting or accidental DSN syntax.
    for key in ('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'AGENT_DB'):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', compose[key]):
            raise ValueError(f'{key} must use letters, digits, _ or - for generated DSNs')
    if compose['POSTGRES_DB'] == compose['AGENT_DB']:
        raise ValueError('Business and Agent databases must be separate')
    web, backend, agent = (values[n] for n in ('web', 'backend', 'agent'))

    def paired(key, names):
        candidates = {existing[n][key] for n in names if existing[n].get(key)}
        if len(candidates) > 1:
            raise ValueError(f'Existing Docker {key} differs between services; fix manually')
        value = next(iter(candidates), None) or next((originals[n][key] for n in names if originals[n].get(key)), None) or secrets.token_urlsafe(48)
        for n in names:
            if not existing[n].get(key):
                values[n][key] = value

    paired('BACKEND_BFF_SECRET', ('web', 'backend'))
    for key in ('AGENT_SERVICE_TOKEN', 'AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN', 'AGENT_CONTROL_TOKEN'):
        paired(key, ('backend', 'agent'))
    agent['AGENT_WORKER_TOKEN'] = agent['AGENT_WORKER_TOKEN'] or secrets.token_urlsafe(48)
    if len({agent[k] for k in ('AGENT_SERVICE_TOKEN', 'AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN', 'AGENT_CONTROL_TOKEN', 'AGENT_WORKER_TOKEN')}) != 5:
        raise ValueError('Agent role credentials must be distinct')
    for key in ('AGENT_AUDIENCE', 'AGENT_GRANT_ISSUER'):
        # Existing configured admission identity is authoritative; never synthesize
        # a new identity when importing a V2 deployment.
        candidates = {originals[n][key] for n in ('backend', 'agent') if originals[n].get(key)}
        if len(candidates) > 1:
            raise ValueError(f'Native {key} mismatch')
        for n in ('backend', 'agent'):
            if key not in existing[n] and candidates:
                values[n][key] = next(iter(candidates))
        if backend[key] != agent[key]:
            raise ValueError(f'Docker {key} mismatch')

    user, password = compose['POSTGRES_USER'], compose['POSTGRES_PASSWORD']
    dsn = f'postgresql://{user}:{password}@postgres:5432/'
    overrides = {
        'web': dict(DATABASE_URL=dsn + compose['POSTGRES_DB'], BUSINESS_BACKEND_URL='http://backend:8000',
                    BETTER_AUTH_URL=f"http://localhost:{compose['WEB_PORT']}",
                    BETTER_AUTH_TRUSTED_ORIGINS=f"http://localhost:{compose['WEB_PORT']}",
                    BACKEND_ALLOW_INSECURE_LOCAL_BFF='false'),
        'backend': dict(CHAT_DATABASE_URL=dsn + compose['POSTGRES_DB'], AGENT_INTERNAL_URL='http://agent-api:8101',
                        BACKEND_ALLOW_INSECURE_LOCAL_BFF='false', AGENT_ALLOW_TEST_POLICY='false',
                        BACKGROUND_JOBS_ENABLED='false'),
        'agent': dict(AGENT_DATABASE_URL=dsn.replace('postgresql://', 'postgresql+asyncpg://') + compose['AGENT_DB'],
                      AGENT_INTERNAL_URL='http://agent-api:8101', BACKEND_INTERNAL_URL='http://backend:8000/api/v1/agent',
                      BACKEND_ENTITLEMENTS_URL='http://backend:8000', AGENT_WORKSPACE_ROOT='/var/lib/shenzhi/workspace',
                      AGENT_USAGE_SPOOL_ROOT='/var/lib/shenzhi/usage-spool', AGENT_DEMO_MODE='0'),
    }
    for name, settings in overrides.items():
        for key, value in settings.items():
            if key not in existing[name]:
                values[name][key] = value
    web['BETTER_AUTH_SECRET'] = web['BETTER_AUTH_SECRET'] or secrets.token_urlsafe(48)

    for name, key, filename in (('backend', 'AGENT_GRANT_PRIVATE_KEY_FILE', 'grant-private.pem'),
                                 ('agent', 'AGENT_GRANT_PUBLIC_KEYS_FILE', 'grant-public.json')):
        directory = HERE / 'secrets' / name
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        if key not in existing[name] and originals[name].get(key):
            source = Path(originals[name][key])
            if not source.is_absolute():
                source = ROOT / 'apps' / name / source
            destination = directory / filename
            if not destination.exists():
                destination.write_bytes(source.read_bytes())
                destination.chmod(0o600)
            values[name][key] = f'/run/secrets/{name}/{filename}'
    if backend['AGENT_V2_ADMISSION'] != 'disabled':
        if agent['AGENT_V1_ADMISSION'] != 'drain_only' or agent['AGENT_WORKER_PROTOCOL'] != '2':
            raise ValueError('V2 requires drain_only and protocol=2; configure explicitly')
        if not backend['AGENT_GRANT_PRIVATE_KEY_FILE'] or not agent['AGENT_GRANT_PUBLIC_KEYS_FILE']:
            raise ValueError('V2 signing keys required; no admission downgrade performed')
    # Public values must agree with the production image build configuration.
    for key in compose:
        if key.startswith('NEXT_PUBLIC_') and key not in read(HERE / '.env'):
            compose[key] = web.get(key, compose[key])
    for name, path in paths.items():
        save(path, values[name])
    save(HERE / '.env', compose, compose=True)
    print('Docker env prepared; native files untouched. Existing Docker values retained.')
    print('Review env files privately; external loopback services need host.docker.internal or a reachable URL.')


if __name__ == '__main__':
    main()
