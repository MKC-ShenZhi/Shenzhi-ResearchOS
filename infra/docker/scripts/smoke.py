"""Container smoke checks. No external model requests or new business tasks.

Run in Backend: python /opt/docker/smoke.py [--full] [--write-probe]
--write-probe creates one isolated marker table to verify persistence on reruns.
"""
import argparse
import asyncio
import json
import os
import urllib.error
import urllib.request

from auth_migrations import load_auth_migrations, validate_auth_migrations


def request(url, *, headers=None, body=None, expected=200):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            status, result = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, result = error.code, error.read()
    assert status == expected, f'{url.split("?")[0]}: expected {expected}, got {status}'
    return json.loads(result) if result else None


async def main():
    import asyncpg
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--write-probe', action='store_true')
    args = parser.parse_args()
    request('http://backend:8000/health')
    request('http://web:3000/api/v1/health')
    request('http://web:3000/api/auth/get-session')
    request('http://backend:8000/api/v1/agent/config', expected=401)
    request('http://backend:8000/api/v1/admin-console/users', expected=403)
    request('http://web:3000/api/v1/admin-console/users', expected=404)
    db = await asyncpg.connect(os.environ['CHAT_DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://', 1))
    try:
        assert await db.fetchval('SELECT version_num FROM alembic_version')
        validate_auth_migrations(
            await db.fetch('SELECT name, sha256 FROM docker_auth_migrations'),
            load_auth_migrations(),
        )
        for table in ('user', 'account', 'session', 'verification', 'turnstile_verification'):
            assert await db.fetchval('SELECT to_regclass($1)', f'public."{table}"')
        if args.write_probe:
            await db.execute('CREATE TABLE IF NOT EXISTS docker_runtime_probe (id integer PRIMARY KEY, value text NOT NULL)')
            await db.execute("INSERT INTO docker_runtime_probe VALUES (1,'persistent') ON CONFLICT DO NOTHING")
            assert await db.fetchval('SELECT value FROM docker_runtime_probe WHERE id=1') == 'persistent'
    finally:
        await db.close()
    print('PASS: Web/BFF/Backend, auth session endpoint, business schema, rejected missing BFF credential and Admin access')
    if args.full:
        request('http://agent-api:8101/internal/v2/health')
        request('http://agent-api:8101/internal/v2/config', expected=401)
        service = {'Authorization': 'Bearer ' + os.environ['AGENT_SERVICE_TOKEN']}
        request('http://agent-api:8101/internal/v2/config', headers=service)
        request('http://backend:8000/api/v1/agent/config', headers={'x-shenzhi-bff-secret': os.environ['BACKEND_BFF_SECRET']})
        request('http://web:3000/api/v1/agent/config')
        if os.getenv('AGENT_V2_ADMISSION') != 'disabled':
            request('http://agent-api:8101/internal/v2/protocol-capabilities', headers={
                'Authorization': 'Bearer ' + os.environ['AGENT_GATEWAY_TOKEN']})
            request('http://agent-api:8101/internal/v2/protocol-capabilities', headers=service, expected=403)
        print('PASS: BFF -> Backend -> Agent config, V2 credential protection and configured V2 role isolation')
    print('Smoke complete; no model/search/email/task execution was attempted.')


if __name__ == '__main__':
    asyncio.run(main())
