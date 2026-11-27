"""Real Admin -> Backend -> Agent Registry browser smoke, using isolated local processes.

Run from the repository root with Python and pass a Chrome/Edge executable.
No databases, external Providers, fixed ports or existing services are used.
"""
import http.client
import http.server
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[3]


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def ready(url):
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(.1)
    raise RuntimeError('Server not ready: ' + url)


def main():
    chrome = sys.argv[1]
    agent_port, backend_port = port(), port()
    processes = []
    with tempfile.TemporaryDirectory(prefix='shenzhi-catalog-') as directory:
        secret = Path(directory) / 'entry'
        secret.write_text('a' * 64, encoding='utf-8')
        class Entry(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(ROOT / 'apps/admin/dist'), **kwargs)
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path.startswith('/api/'):
                    self.proxy()
                else:
                    super().do_GET()
            def do_POST(self):
                self.proxy()
            def proxy(self):
                connection = http.client.HTTPConnection('127.0.0.1', backend_port, timeout=10)
                headers = {key: value for key, value in self.headers.items() if key.lower() not in ('connection', 'x-shenzhi-admin-entry')}
                headers['X-ShenZhi-Admin-Entry'] = 'a' * 64
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                try:
                    connection.request(self.command, self.path, body=body, headers=headers)
                    response = connection.getresponse()
                    data = response.read()
                    self.send_response(response.status)
                    for key, value in response.getheaders():
                        if key.lower() not in ('connection', 'transfer-encoding', 'content-length'):
                            self.send_header(key, value)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                finally:
                    connection.close()
        entry = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Entry)
        entry_port = entry.server_port
        thread = threading.Thread(target=entry.serve_forever, daemon=True)
        thread.start()
        logs = []
        try:
            env = {**os.environ, 'AGENT_MANAGEMENT_TOKEN': 'catalog-test-role', 'AGENT_GATEWAY_TOKEN': 'gateway-test-role',
                'AGENT_WORKER_TOKEN': 'worker-test-role', 'AGENT_INTERNAL_URL': f'http://127.0.0.1:{agent_port}',
                'ADMIN_AUTH_MODE': 'ssh_tunnel', 'ADMIN_ENTRY_SECRET_FILE': str(secret),
                'ADMIN_TUNNEL_PRINCIPAL': 'test-admin', 'ADMIN_TUNNEL_ALLOWED_HOSTS': f'127.0.0.1:{entry_port}',
                'ADMIN_SESSION_SECRET': 's' * 40, 'BACKGROUND_JOBS_ENABLED': 'false', 'CHAT_DATABASE_URL': '',
                'AGENT_DATABASE_URL': '', 'PYTHONIOENCODING': 'utf-8'}
            for app, module, listen in [('agent', 'agent_app.main:app', agent_port), ('backend', 'app.main:app', backend_port)]:
                log = open(Path(directory) / (app + '.log'), 'w+', encoding='utf-8')
                logs.append(log)
                python = ROOT / 'apps' / app / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
                processes.append(subprocess.Popen([str(python), '-m', 'uvicorn', module, '--host', '127.0.0.1', '--port', str(listen), '--no-proxy-headers'],
                    cwd=ROOT / 'apps' / app, env=env, stdout=log, stderr=subprocess.STDOUT))
            ready(f'http://127.0.0.1:{agent_port}/internal/v2/health')
            ready(f'http://127.0.0.1:{backend_port}/health')
            # Backend must reject a direct loopback request without the dedicated entry secret.
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{backend_port}/api/v1/admin-console/auth/me')
                raise AssertionError('Direct Backend bypass accepted')
            except urllib.error.HTTPError as error:
                assert error.code == 403
            subprocess.run(['node', str(ROOT / 'apps/admin/tests/agent-management-smoke.mjs'), chrome,
                f'http://127.0.0.1:{entry_port}', '--tunnel'], cwd=ROOT, env=env, check=True)
        except BaseException:
            for log in logs:
                log.flush()
                log.seek(0)
                print(log.read()[-5000:], file=sys.stderr)
            raise
        finally:
            entry.shutdown()
            entry.server_close()
            thread.join()
            for process in processes:
                if os.name == 'nt' and process.poll() is None:
                    # venv python.exe is a launcher; terminate only this test's entire child tree.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for log in logs:
                log.close()


if __name__ == '__main__':
    main()
