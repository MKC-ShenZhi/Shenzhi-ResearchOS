"""Run the M1 browser demo using the existing M0 acceptance databases only.

No migrations, seed data, real model Worker or upstream research requests.
Stop with Ctrl+C; all child processes launched here are stopped together.
"""
from __future__ import annotations

import os
import asyncio
import re
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from dotenv import dotenv_values
import asyncpg

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / 'apps/backend/.venv/m1-demo-logs'


def isolated_database(value, database):
    parsed = urlsplit(value or '')
    if (parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.port != 55432
            or parsed.path != '/' + database):
        raise RuntimeError('拒绝连接：演示仅复用本机 55432 的 M0-C1 隔离验收库')
    return value


def environments():
    backend = dotenv_values(ROOT / '.env.m0-c1-backend')
    agent = dotenv_values(ROOT / '.env.m0-c1-agent')
    # Blank app-local dotenv entries before Next/uvicorn can load old destinations.
    env = os.environ.copy()
    for path in (ROOT / 'apps/backend/.env', ROOT / 'apps/agent/.env',
                 ROOT / 'apps/web/.env', ROOT / 'apps/web/.env.local',
                 ROOT / 'apps/web/.env.development', ROOT / 'apps/web/.env.development.local',
                 ROOT / '.env.m0-c1-backend', ROOT / '.env.m0-c1-agent'):
        if path.exists():
            for key in environment_keys(path):
                env[key] = ''
    env.update(PYTHONUTF8='1', BACKGROUND_JOBS_ENABLED='false',
               BACKEND_ALLOW_INSECURE_LOCAL_BFF='false', AGENT_DEMO_MODE='1',
               AGENT_INTERNAL_URL='http://127.0.0.1:18101',
               BACKEND_INTERNAL_URL='http://127.0.0.1:18000',
               BUSINESS_BACKEND_URL='http://127.0.0.1:18000',
               CHAT_DATABASE_URL=isolated_database(backend.get('CHAT_DATABASE_URL'), 'shenzhi_m0c1_backend'),
               AGENT_DATABASE_URL=isolated_database(agent.get('AGENT_DATABASE_URL'), 'shenzhi_m0c1_agent'),
               BACKEND_BFF_SECRET=secrets.token_urlsafe(32),
               AGENT_SERVICE_TOKEN=secrets.token_urlsafe(32),
               AGENT_WORKSPACE_ROOT=str(ROOT / 'apps/agent/workspace/m1-demo'),
               BETTER_AUTH_SECRET=secrets.token_urlsafe(32),
               BETTER_AUTH_URL='http://127.0.0.1:13000',
               BETTER_AUTH_TRUSTED_ORIGINS='http://127.0.0.1:13000',
               TURNSTILE_ENABLED='false',
               NEXT_TELEMETRY_DISABLED='1')
    # Existing anonymous access needs no test account or auth table writes.
    env['DATABASE_URL'] = env['CHAT_DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
    return env


def environment_keys(path):
    """Scrubbing needs assignment names, not dotenv values or interpolation.

    These files belong to other runtimes (including Next's dotenv dialect).
    Only the dedicated acceptance files above supply Python configuration.
    """
    return re.findall(r'^\s*(?:export\s+)?([\w.-]+)\s*=',
                      path.read_text(encoding='utf-8-sig'), re.MULTILINE)


def start(env):
    for port in (18101, 18000, 13000):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError(f'端口 {port} 已占用；请先停止该端口的本地服务')
    LOGS.mkdir(parents=True, exist_ok=True)
    agent_python = str(ROOT / 'apps/agent/.venv/Scripts/python.exe')
    backend_python = str(ROOT / 'apps/backend/.venv/Scripts/python.exe')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('找不到 Node，请先按仓库开发说明安装工具链')
    specs = [
        ('agent-api', 'apps/agent', [agent_python, '-m', 'uvicorn', 'agent_app.main:app',
                                    '--host', '127.0.0.1', '--port', '18101']),
        ('backend', 'apps/backend', [backend_python, '-m', 'uvicorn', 'app.main:app',
                                    '--host', '127.0.0.1', '--port', '18000']),
        ('mock-worker', 'apps/agent', [agent_python, '-m', 'agent_app.demo_worker']),
        ('web', 'apps/web', [node, 'node_modules/next/dist/bin/next', 'dev',
                             '--webpack', '--hostname', '127.0.0.1', '--port', '13000']),
    ]
    processes = []
    try:
        for name, cwd, command in specs:
            with (LOGS / f'{name}.log').open('w', encoding='utf-8') as log:
                proc = subprocess.Popen(command, cwd=ROOT / cwd, env=env, stdout=log,
                                        stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append((name, proc))
        return processes
    except BaseException:
        stop(processes)
        raise


def stop(processes):
    for _, proc in reversed(processes):
        if proc.poll() is None:
            if os.name == 'nt':
                # venv launchers and Next spawn children; terminate this owned tree.
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                proc.terminate()
    for _, proc in reversed(processes):
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def ready(processes):
    deadline = time.monotonic() + 90
    pending = {'Agent API': 'http://127.0.0.1:18101/internal/v1/health',
               'Backend': 'http://127.0.0.1:18000/health',
               'Web': 'http://127.0.0.1:13000/agents',
               '匿名身份 BFF': 'http://127.0.0.1:13000/api/v1/identity/bootstrap',
               'Mock 配置 BFF': 'http://127.0.0.1:13000/api/v1/agent/config'}
    while pending and time.monotonic() < deadline:
        if any(proc.poll() is not None for _, proc in processes):
            raise RuntimeError(f'服务启动失败，请查看 {LOGS}')
        for name, url in list(pending.items()):
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        del pending[name]
            except OSError:
                pass
        time.sleep(0.5)
    if pending:
        raise RuntimeError(f'启动等待超时：{list(pending)}；请查看 {LOGS}')


async def check_demo_queue(env):
    connection = await asyncpg.connect(env['AGENT_DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://'))
    try:
        count = await connection.fetchval("""
            SELECT count(*) FROM agent_runs
            WHERE status IN ('pending', 'running')
              AND request_json->>'model' IS DISTINCT FROM 'demo/m1'
        """)
        if count:
            raise RuntimeError('隔离库中存在非 Mock 待执行任务；拒绝启动 Mock Worker')
    finally:
        await connection.close()


def main():
    env = environments()
    asyncio.run(check_demo_queue(env))
    processes = start(env)
    try:
        ready(processes)
        print('Mock 演示已启动：http://127.0.0.1:13000/agents', flush=True)
        print('无需登录，使用现有匿名身份；请保留 Cookie。Ctrl+C 停止全部演示服务。', flush=True)
        while all(proc.poll() is None for _, proc in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop(processes)


if __name__ == '__main__':
    main()
