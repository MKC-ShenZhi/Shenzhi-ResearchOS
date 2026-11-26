"""Run explicit isolated production-entry acceptance using cached application images.

Windows entry point uses WSL's Docker CLI. PostgreSQL must be an explicitly
created disposable Phase 4 container with the migrated phase3accept database.
Only containers created by this process are removed on exit.
"""
import argparse
import json
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
from tempfile import TemporaryDirectory
import time
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def linux_path(path):
    path = Path(path).resolve()
    return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]


def docker(*args):
    result = subprocess.run(['wsl', '--exec', 'docker', *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result.stdout.strip()


def wait(url, headers=None):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            result = httpx.get(url, headers=headers, timeout=2, trust_env=False)
            if result.status_code < 500:
                return result
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError('Isolated service did not become ready')


def eventually(check):
    deadline = time.monotonic() + 50
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.5)
    raise AssertionError('Isolated Worker evidence did not reach the expected state')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--network', required=True)
    parser.add_argument('--postgres', required=True)
    parser.add_argument('--admin-image', default='shenzhi-phase4/admin:accept')
    parser.add_argument('--agent-image', default='shenzhi-phase32-accept/agent:source')
    parser.add_argument('--backend-image', default='shenzhi-phase32-accept/backend:source')
    parser.add_argument('--ssh-image')
    args = parser.parse_args()
    if not args.network.startswith('shenzhi-phase4-') or not args.postgres.startswith('shenzhi-phase4-'):
        raise RuntimeError('Only explicitly named isolated Phase 4 resources are allowed')
    root = Path(__file__).resolve().parents[4]
    prefix = 'shenzhi-phase4-entry-' + secrets.token_hex(4)
    created = []
    tunnel = None
    linux_key_directory = None
    entry_secret = secrets.token_hex(32)
    report_token = secrets.token_hex(32)
    worker_id = prefix + '-worker'
    common = ['--network', args.network, '--label', 'shenzhi.phase=phase4-entry-acceptance']
    contracts = linux_path(root / 'packages/agent-contracts') + ':/repo/packages/agent-contracts:ro'
    db_host = args.postgres
    dsn = 'postgresql+asyncpg://phase4:phase4-isolated-test-only@' + db_host + '/'
    env = lambda values: [part for key, value in values.items() for part in ('-e', key + '=' + value)]
    try:
        with TemporaryDirectory(prefix='phase4-entry-') as directory:
            secret_file = Path(directory) / 'entry'
            secret_file.write_text(entry_secret, encoding='utf-8')
            secret_volume = linux_path(secret_file) + ':/run/secrets/admin_entry:ro'
            agent = prefix + '-agent'
            docker('run', '-d', '--name', agent, *common, '-v', contracts,
                '-v', linux_path(root / 'apps/agent/src') + ':/repo/apps/agent/src:ro',
                *env(dict(AGENT_DATABASE_URL=dsn + 'phase3accept', AGENT_MANAGEMENT_TOKEN='phase4-management-test',
                    AGENT_CONFIG_MANAGEMENT_TOKEN='phase4-config-test', AGENT_MANAGEMENT_INSPECTOR_ENABLED='true',
                    AGENT_WORKER_TOKEN='phase4-execution-worker-test', AGENT_WORKER_STALE_SECONDS='5',
                    AGENT_WORKER_OFFLINE_SECONDS='10', AGENT_WORKER_REPORT_IDENTITIES=json.dumps({worker_id: hashlib.sha256(report_token.encode()).hexdigest()}))),
                args.agent_image)
            created.append(agent)
            backend = prefix + '-backend'
            docker('run', '-d', '--name', backend, *common, '-p', '127.0.0.1:25438:3101',
                '-p', '127.0.0.1:25439:8000', '-p', '127.0.0.1:25440:25440', '-v', contracts, '-v', secret_volume,
                '-v', linux_path(root / 'apps/backend/app') + ':/repo/apps/backend/app:ro',
                *env(dict(CHAT_DATABASE_URL=dsn + 'shenzhi_a_line_backend_phase4', ADMIN_AUTH_MODE='ssh_tunnel',
                    ADMIN_ENTRY_SECRET_FILE='/run/secrets/admin_entry', ADMIN_TUNNEL_PRINCIPAL='acceptance-operator',
                    ADMIN_SESSION_SECRET='phase4-entry-session-secret-for-isolated-tests',
                    ADMIN_AGENT_AUDIT_SECRET='phase4-entry-independent-audit-secret-for-isolated-tests',
                    AGENT_INTERNAL_URL='http://' + agent + ':8101', AGENT_MANAGEMENT_TOKEN='phase4-management-test',
                    AGENT_CONFIG_MANAGEMENT_TOKEN='phase4-config-test')),
                args.backend_image, 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000',
                '--no-proxy-headers', '--lifespan', 'off')
            created.append(backend)
            docker('exec', backend, 'python', '-c',
                'import asyncio\nfrom app.core.database import get_engine\n'
                'from app.models.agent_management import ManagementAuditRow\n'
                'async def setup():\n    async with get_engine().begin() as connection:\n'
                '        await connection.run_sync(lambda sync: ManagementAuditRow.__table__.create(sync, checkfirst=True))\n'
                'asyncio.run(setup())')
            docker('run', '-d', '--name', worker_id, *common, '-v', contracts,
                '-v', linux_path(root / 'apps/agent/src') + ':/repo/apps/agent/src:ro',
                *env(dict(AGENT_INTERNAL_URL='http://' + agent + ':8101', AGENT_WORKER_ID=worker_id,
                    AGENT_WORKER_PROTOCOL='2', AGENT_WORKER_TOKEN='phase4-execution-worker-test',
                    AGENT_WORKER_REPORT_TOKEN=report_token, AGENT_WORKER_REPORT_INTERVAL_SECONDS='2')),
                args.agent_image, 'python', '-m', 'agent_app.worker_main')
            created.append(worker_id)
            admin = prefix + '-admin'
            docker('run', '-d', '--name', admin, '--network', 'container:' + backend, '--read-only',
                '--tmpfs', '/tmp:uid=101,gid=101,mode=0700', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges:true', '-v', secret_volume, args.admin_image)
            created.append(admin)
            public_config = Path(directory) / 'public.conf'
            public_config.write_text('server { listen 8080; include /etc/nginx/admin-deny.conf; '
                'location / { proxy_pass http://' + backend + ':8000; } }', encoding='utf-8')
            public = prefix + '-public'
            docker('run', '-d', '--name', public, *common, '-p', '127.0.0.1:25442:8080',
                '-v', linux_path(public_config) + ':/etc/nginx/conf.d/default.conf:ro',
                '-v', linux_path(root / 'infra/docker/nginx/public-admin-deny.conf') + ':/etc/nginx/admin-deny.conf:ro',
                'nginx:1.28-alpine')
            created.append(public)
            assert wait('http://127.0.0.1:25442/api/v1/admin-console').status_code == 404
            for path in ('/api/v1/admin-console/auth/me', '/api/v1/admin-console%2fauth/me'):
                assert httpx.get('http://127.0.0.1:25442' + path, trust_env=False).status_code == 404
            headers = {'Host': '127.0.0.1:3101'}
            assert wait('http://127.0.0.1:25438/health', headers).status_code == 200
            direct = wait('http://127.0.0.1:25439/api/v1/admin-console/auth/me')
            assert direct.status_code == 403
            with httpx.Client(base_url='http://127.0.0.1:25438', headers=headers, trust_env=False) as client:
                session = client.get('/api/v1/admin-console/auth/me')
                assert session.status_code == 200, session.text
                assert session.json()['data']['mode'] == 'ssh_tunnel'
                assert 'HttpOnly' in session.headers['set-cookie']
                assert client.get('/api/v1/admin-console/agent/providers').status_code == 200
                worker_path = '/api/v1/admin-console/agent/worker-evidence/' + worker_id
                def worker_state():
                    response = client.get(worker_path)
                    return response.json().get('data', {}) if response.status_code == 200 else {}
                first = eventually(lambda: (value if (value := worker_state()).get('state') == 'online' else None))
                first_instance = first['instance_id']
                def control(kind, target, action):
                    response = client.post('/api/v1/admin-console/agent/actions', headers={'X-Admin-Request': '1'},
                        json=dict(operation_id=str(__import__('uuid').uuid4()), kind=kind, target_id=target,
                                  action=action, reason='Isolated acceptance', timeout_seconds=10))
                    assert response.status_code == 200, response.text
                control('worker', worker_id, 'drain')
                state = client.get('/api/v1/admin-console/agent/worker-control/' + worker_id)
                assert state.json()['data']['state'] == 'drained'
                docker('network', 'disconnect', args.network, worker_id)
                eventually(lambda: worker_state().get('state') == 'offline')
                def incident():
                    response = client.get('/api/v1/admin-console/agent/alerts')
                    return next((item for item in response.json()['data']['items'] if item['worker_id'] == worker_id), None)
                alert = eventually(incident)
                control('alert', alert['alert_id'], 'acknowledge')
                docker('network', 'connect', args.network, worker_id)
                eventually(lambda: worker_state().get('state') == 'online')
                eventually(lambda: (value if (value := incident()) and value['recovered_at'] else None))
                control('alert', alert['alert_id'], 'close')
                docker('restart', worker_id)
                eventually(lambda: (value if (value := worker_state()).get('state') == 'online'
                    and value['instance_id'] != first_instance else None))
                control('worker', worker_id, 'resume')
                assert client.get('/api/v1/admin-console/auth/me', headers={'Origin': 'https://evil.example.invalid'}).status_code == 403
                assert client.get('/api/v1/admin-console/auth/me', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
                assert client.get('/api/v1/admin-console/auth/me', headers={'Host': 'public.example.invalid'}).status_code == 403
                page = client.get('/')
                assert entry_secret not in page.text
                assert 'frame-ancestors' in page.headers['content-security-policy']
                docker('restart', admin)
                assert wait('http://127.0.0.1:25438/health', headers).status_code == 200
                assert client.get('/api/v1/admin-console/auth/me').status_code == 200
                secret_file.write_text(secrets.token_hex(32), encoding='utf-8')
                assert client.get('/api/v1/admin-console/agent/providers').status_code == 403
                docker('restart', admin)
                assert wait('http://127.0.0.1:25438/health', headers).status_code == 200
                assert client.get('/api/v1/admin-console/agent/providers').status_code == 401
                assert client.get('/api/v1/admin-console/auth/me').status_code == 200
            if args.ssh_image:
                keys = Path(directory) / 'keys'
                keys.mkdir()
                for name in ('client', 'host'):
                    key = Ed25519PrivateKey.from_private_bytes(os.urandom(32))
                    (keys / name).write_bytes(key.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()))
                    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
                    (keys / (name + '.pub')).write_bytes(public + b'\n')
                (keys / 'known_hosts').write_bytes(b'[127.0.0.1]:25440 ' + (keys / 'host.pub').read_bytes())
                (keys / 'sshd_config').write_text('Port 25440\nListenAddress 0.0.0.0\nHostKey /tmp/host\n'
                    'PidFile /tmp/sshd.pid\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n'
                    'PermitRootLogin prohibit-password\nPubkeyAuthentication yes\nAuthorizedKeysFile /root/.ssh/authorized_keys\n'
                    'AllowTcpForwarding local\nPermitOpen 127.0.0.1:3101\nAllowAgentForwarding no\nX11Forwarding no\n'
                    'PermitTTY no\nMaxSessions 0\n', encoding='utf-8')
                sshd = prefix + '-sshd'
                docker('run', '-d', '--name', sshd, '--network', 'container:' + backend,
                    '-v', linux_path(keys) + ':/keys:ro', args.ssh_image, '-c',
                    'cp /keys/host /tmp/host && chmod 600 /tmp/host && cp /keys/client.pub /root/.ssh/authorized_keys '
                    '&& chmod 600 /root/.ssh/authorized_keys && exec /usr/sbin/sshd -D -e -f /keys/sshd_config')
                created.append(sshd)
                time.sleep(1)
                linux_key_directory = '/tmp/' + prefix + '-ssh'
                subprocess.run(['wsl', '--exec', 'mkdir', '-m', '700', linux_key_directory], check=True)
                subprocess.run(['wsl', '--exec', 'cp', linux_path(keys / 'client'), linux_key_directory + '/client'], check=True)
                subprocess.run(['wsl', '--exec', 'chmod', '600', linux_key_directory + '/client'], check=True)
                tunnel = subprocess.Popen(['wsl', '--exec', 'sh', '-c', 'echo $$ > "$1"; shift; exec ssh "$@"',
                    'sh', linux_key_directory + '/pid', '-N', '-T', '-p', '25440', '-i', linux_key_directory + '/client',
                    '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'UserKnownHostsFile=' + linux_path(keys / 'known_hosts'),
                    '-L', '127.0.0.1:25441:127.0.0.1:3101', 'root@127.0.0.1'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    assert wait('http://127.0.0.1:25441/api/v1/admin-console/auth/me', headers).status_code == 200
                except Exception:
                    if tunnel.poll() is not None:
                        raise RuntimeError(tunnel.stderr.read().decode(errors='replace')) from None
                    raise RuntimeError(docker('logs', '--tail', '12', sshd)) from None
                pid = subprocess.check_output(['wsl', '--exec', 'cat', linux_key_directory + '/pid'], text=True).strip()
                subprocess.run(['wsl', '--exec', 'kill', str(int(pid))], check=True)
                tunnel.wait(timeout=10)
                tunnel = None
                try:
                    httpx.get('http://127.0.0.1:25441/health', headers=headers, timeout=1, trust_env=False)
                    raise AssertionError('Closed SSH tunnel still reachable')
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
                    pass
            print(json.dumps(dict(production_static=True, tunnel_entry_cookie=True, direct_backend_denied=True,
                cross_site_denied=True, host_denied=True, actual_agent_registry=True, restart=True,
                public_proxy_denied=True, entry_secret_rotation=True,
                worker_network_recovery=True, worker_restart=True, drain_and_resume=True, alert_acknowledge_close=True,
                ssh_handshake=bool(args.ssh_image),
                source='Cached application dependencies with current source mounted read-only')))
    finally:
        if tunnel and tunnel.poll() is None:
            pid = subprocess.check_output(['wsl', '--exec', 'cat', linux_key_directory + '/pid'], text=True).strip()
            subprocess.run(['wsl', '--exec', 'kill', str(int(pid))], check=False, capture_output=True)
            tunnel.wait(timeout=10)
        if linux_key_directory:
            subprocess.run(['wsl', '--exec', 'rm', '-f', linux_key_directory + '/client', linux_key_directory + '/pid'], check=True)
            subprocess.run(['wsl', '--exec', 'rmdir', linux_key_directory], check=True)
        for name in reversed(created):
            docker('rm', '-f', name)


if __name__ == '__main__':
    main()
