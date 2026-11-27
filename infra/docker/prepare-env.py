"""Create ignored Docker config without changing native files or existing values.

Python 3.12+, standard library only. Run from any directory. --from-local imports
only keys declared in Docker examples; no secret values are printed.
"""
import argparse
import os
import re
import secrets
import tempfile
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


def render(values, compose=False, template=None):
    # Compose .env uses interpolation; app files use env_file format: raw.
    def assignment(key):
        value = values[key]
        return f"{key}={chr(39) + value + chr(39) if compose else value}"

    if template is None:
        return ('\n'.join(assignment(key) for key in values) + '\n').encode('utf-8')
    lines, emitted = [], set()
    for line in template.read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'^(#\s*)?([A-Za-z_][A-Za-z_0-9]*)=', line)
        if match:
            commented, key = match.groups()
            if key in values:
                lines.append(assignment(key))
                emitted.add(key)
            elif commented:
                lines.append(line)
        else:
            lines.append(line)
    extra = [key for key in values if key not in emitted]
    if extra:
        lines.extend(['', '# 本地额外配置（未在示例模板中声明）'])
        lines.extend(assignment(key) for key in extra)
    return ('\n'.join(lines) + '\n').encode('utf-8')


def publish(files):
    """Stage validated output first; restore replaced files if publication fails."""
    staged, backups, replaced = {}, {}, []

    def stage(path, data, mode=0o600):
        fd, temporary = tempfile.mkstemp(prefix='.prepare-', dir=path.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            temporary.chmod(mode)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return temporary

    try:
        for path, data in files.items():
            if path.exists() and path.read_bytes() == data:
                continue
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.exists():
                backups[path] = stage(path, path.read_bytes(), path.stat().st_mode & 0o777)
            staged[path] = stage(path, data)
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
    except BaseException:
        failed_backups = []
        for path in reversed(replaced):
            try:
                if path in backups:
                    os.replace(backups[path], path)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                # Retain the original bytes for manual recovery if the disk
                # also refuses rollback; never delete the only remaining copy.
                if path in backups:
                    failed_backups.append(str(backups.pop(path)))
        if failed_backups:
            raise RuntimeError('Publication rollback failed; original backups retained: '
                               + ', '.join(failed_backups)) from None
        raise
    finally:
        for temporary in (*staged.values(), *backups.values()):
            temporary.unlink(missing_ok=True)


def nonempty(value):
    return bool(value and value.strip())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-local', action='store_true')
    args = parser.parse_args(argv)
    paths = {name: HERE / 'env' / f'{name}.env' for name in ('web', 'backend', 'agent', 'payment')}
    existing = {name: read(path) for name, path in paths.items()}
    originals = {name: read(ROOT / 'apps' / name / ('.env.local' if name == 'web' else '.env'))
                 if args.from_local else {} for name in paths}
    values = {}
    for name, path in paths.items():
        defaults = read(path.with_suffix('.env.example'))
        values[name] = {key: originals[name][key] if nonempty(originals[name].get(key)) else value
                        for key, value in defaults.items()}
        values[name].update({key: value for key, value in existing[name].items()
                             if nonempty(value) or key not in values[name]})
    # These controls belonged to the retired V1 admission/dual-protocol worker.
    values['agent'].pop('AGENT_V1_ADMISSION', None)
    values['agent'].pop('AGENT_WORKER_PROTOCOL', None)
    # Empty BASE_URL overrides disable the registry default, so import only
    # explicitly configured nonempty Provider overrides.
    # Import only the optional nonempty overrides declared in the template.
    template = paths['agent'].with_suffix('.env.example').read_text(encoding='utf-8-sig')
    for key in re.findall(r'^#\s*([A-Z][A-Z0-9_]*)=', template, re.MULTILINE):
        if nonempty(originals['agent'].get(key)) and not nonempty(existing['agent'].get(key)):
            values['agent'][key] = originals['agent'][key]
        if not nonempty(values['agent'].get(key)):
            values['agent'].pop(key, None)

    compose = read(HERE / '.env.example')
    existing_compose = read(HERE / '.env')
    compose.update({key: value for key, value in existing_compose.items()
                    if nonempty(value) or key not in compose})
    compose['POSTGRES_PASSWORD'] = compose['POSTGRES_PASSWORD'] or secrets.token_hex(24)
    compose['ADMIN_DEV_SESSION_SECRET'] = compose['ADMIN_DEV_SESSION_SECRET'] or secrets.token_urlsafe(48)
    if len(compose['ADMIN_DEV_SESSION_SECRET']) < 32:
        raise ValueError('ADMIN_DEV_SESSION_SECRET must be at least 32 characters')
    # Safe URL components; no ambiguous quoting or accidental DSN syntax.
    for key in ('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'AGENT_DB'):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', compose[key]):
            raise ValueError(f'{key} must use letters, digits, _ or - for generated DSNs')
    if compose['POSTGRES_DB'] == compose['AGENT_DB']:
        raise ValueError('Business and Agent databases must be separate')
    web, backend, agent = (values[n] for n in ('web', 'backend', 'agent'))

    def paired(key, names, generate=True):
        candidates = {existing[n][key] for n in names if nonempty(existing[n].get(key))}
        if len(candidates) > 1:
            raise ValueError(f'Existing Docker {key} differs between services; fix manually')
        if not candidates:
            candidates = {originals[n][key] for n in names if nonempty(originals[n].get(key))}
            if len(candidates) > 1:
                raise ValueError(f'Native {key} differs between services; fix manually')
        value = next(iter(candidates), None)
        if value is None:
            value = secrets.token_urlsafe(48) if generate else values[names[0]][key]
        for n in names:
            if not nonempty(existing[n].get(key)):
                values[n][key] = value

    paired('BACKEND_BFF_SECRET', ('web', 'backend'))
    paired('PAYMENT_SERVICE_TOKEN', ('backend', 'payment'))
    for key in ('WECHAT_APP_ID', 'WECHAT_MCH_ID'):
        paired(key, ('backend', 'payment'), generate=False)
    for key in ('AGENT_SERVICE_TOKEN', 'AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN', 'AGENT_CONTROL_TOKEN', 'AGENT_MANAGEMENT_TOKEN'):
        paired(key, ('backend', 'agent'))
    agent['AGENT_WORKER_TOKEN'] = agent['AGENT_WORKER_TOKEN'] or secrets.token_urlsafe(48)
    if len({agent[k] for k in ('AGENT_SERVICE_TOKEN', 'AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN', 'AGENT_CONTROL_TOKEN', 'AGENT_WORKER_TOKEN', 'AGENT_MANAGEMENT_TOKEN')}) != 6:
        raise ValueError('Agent role credentials must be distinct')
    for key in ('AGENT_AUDIENCE', 'AGENT_GRANT_ISSUER'):
        # Existing configured admission identity is authoritative; never synthesize
        # a new identity when importing a V2 deployment.
        paired(key, ('backend', 'agent'), generate=False)
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
                        PAYMENT_SERVICE_URL='http://payment:8090',
                        BACKEND_ALLOW_INSECURE_LOCAL_BFF='false', AGENT_ALLOW_TEST_POLICY='false',
                        BACKGROUND_JOBS_ENABLED='false'),
        'agent': dict(AGENT_DATABASE_URL=dsn.replace('postgresql://', 'postgresql+asyncpg://') + compose['AGENT_DB'],
                      AGENT_INTERNAL_URL='http://agent-api:8101', BACKEND_INTERNAL_URL='http://backend:8000/api/v2/agent',
                      BACKEND_ENTITLEMENTS_URL='http://backend:8000', AGENT_WORKSPACE_ROOT='/var/lib/shenzhi/workspace',
                      AGENT_USAGE_SPOOL_ROOT='/var/lib/shenzhi/usage-spool', AGENT_DEMO_MODE='0'),
    }
    for name, settings in overrides.items():
        for key, value in settings.items():
            if not nonempty(existing[name].get(key)):
                values[name][key] = value
    web['BETTER_AUTH_SECRET'] = web['BETTER_AUTH_SECRET'] or secrets.token_urlsafe(48)

    files = {}
    for name, key, filename in (('backend', 'AGENT_GRANT_PRIVATE_KEY_FILE', 'grant-private.pem'),
                                 ('agent', 'AGENT_GRANT_PUBLIC_KEYS_FILE', 'grant-public.json')):
        directory = HERE / 'secrets' / name
        configured = existing[name].get(key)
        destination = directory / filename
        if nonempty(configured):
            prefix = f'/run/secrets/{name}/'
            if configured.startswith(prefix):
                source = directory / configured[len(prefix):]
                if not source.resolve().is_relative_to(directory.resolve()):
                    raise ValueError(f'{key}: invalid secrets path')
            else:
                source = Path(configured)
                if not source.is_absolute():
                    source = HERE / source
        elif destination.exists():
            # Reuse a previously copied key, even when native config is absent.
            source = destination
        elif nonempty(originals[name].get(key)):
            source = Path(originals[name][key])
            if not source.is_absolute():
                source = ROOT / 'apps' / name / source
        else:
            values[name][key] = ''
            continue
        try:
            if not source.is_file():
                raise ValueError(f'{key}: configured signing file is missing or not a regular file')
            content = source.read_bytes()
            if not content.strip():
                raise ValueError(f'{key}: configured signing file is empty')
        except OSError:
            raise ValueError(f'{key}: configured signing file is unreadable') from None
        if not nonempty(configured):
            if source != destination:
                files[destination] = content
            values[name][key] = f'/run/secrets/{name}/{filename}'
    if backend['AGENT_V2_ADMISSION'] != 'disabled':
        if not backend['AGENT_GRANT_PRIVATE_KEY_FILE'] or not agent['AGENT_GRANT_PUBLIC_KEYS_FILE']:
            raise ValueError('V2 signing keys required; no admission downgrade performed')
    # Public values must agree with the production image build configuration.
    for key in compose:
        if key.startswith('NEXT_PUBLIC_') and not nonempty(existing_compose.get(key)):
            compose[key] = web.get(key, compose[key])
    for name, path in paths.items():
        files[path] = render(values[name], template=path.with_suffix('.env.example'))
    files[HERE / '.env'] = render(compose, compose=True, template=HERE / '.env.example')
    # No environment or signing file is changed before every validation passes.
    for name in ('backend', 'agent', 'payment'):
        (HERE / 'secrets' / name).mkdir(mode=0o700, parents=True, exist_ok=True)
    publish(files)
    print('Docker env prepared; native files untouched. Existing Docker values retained.')
    print('Review env files privately; external loopback services need host.docker.internal or a reachable URL.')


if __name__ == '__main__':
    main()
