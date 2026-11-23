"""Exercise the running Mock demo through Web BFF, then compare isolated SQL records.

Run with Backend's installed environment. Refuses a real model catalog.
Creates labelled acceptance Sessions; never deletes or seeds database rows.
"""
import asyncio
import json
import uuid

import asyncpg
from dotenv import dotenv_values
import httpx

from agent_m1_demo import LOGS, ROOT, isolated_database


def data(response):
    response.raise_for_status()
    payload = response.json()
    assert payload['code'] == 0, payload
    return payload['data']


def events(text):
    result = []
    for block in text.split('\n\n'):
        fields = dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line)
        if 'event' in fields and 'data' in fields:
            result.append((int(fields['id']), fields['event'], json.loads(fields['data'])))
    return result


async def verify_sql(session_id, detail, expected):
    backend = dotenv_values(ROOT / '.env.m0-c1-backend')
    agent = dotenv_values(ROOT / '.env.m0-c1-agent')
    urls = [isolated_database(backend['CHAT_DATABASE_URL'], 'shenzhi_m0c1_backend'),
            isolated_database(agent['AGENT_DATABASE_URL'], 'shenzhi_m0c1_agent')]
    connections = [await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://')) for url in urls]
    try:
        turn = detail['turns'][-1]
        row = await connections[0].fetchrow(
            'SELECT status, assistant_content, report, settings FROM agent_turns WHERE id=$1 AND session_id=$2',
            turn['id'], session_id)
        assert row['status'] == expected
        assert row['assistant_content'] == turn['assistant_content']
        assert row['report'] == turn['report']
        settings = json.loads(row['settings'])
        task_id = settings['agent_task_id']
        task = await connections[1].fetchrow('SELECT current_run_id FROM agent_tasks WHERE task_id=$1', task_id)
        runs = await connections[1].fetch('SELECT status, report_json FROM agent_runs WHERE task_id=$1 ORDER BY attempt', task_id)
        report = json.loads(runs[-1]['report_json'])
        assert report['run_id'] == task['current_run_id']
        assert report['result']['final_text'] == turn['assistant_content']
        assert (report['result'].get('output') or {}).get('report') == turn['report']
        count = await connections[1].fetchval('SELECT count(*) FROM agent_run_events WHERE task_id=$1', task_id)
        assert count > 0
        return {'session_id': session_id, 'turn_id': turn['id'], 'task_id': task_id,
                'run_count': len(runs), 'event_count': count, 'status': expected, 'sql_matches': True}
    finally:
        for connection in connections:
            await connection.close()


async def scenario(client, prompt, mode, expected):
    body = {'prompt': prompt, 'mode': mode, 'model': 'demo/m1', 'attachments': [], 'skills': []}
    session = data(await client.post('/api/v1/agent/sessions', json=body))
    session_id = session['id']
    key = str(uuid.uuid4())
    run_id = None
    # Close the original subscription once execution is accepted; attach without resubmitting.
    async with client.stream('POST', f'/api/v1/agent/sessions/{session_id}/run', json=body,
                             headers={'Idempotency-Key': key}) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.startswith('data: ') and run_id is None:
                run_id = json.loads(line[6:])['run_id']
            if (run_id and expected != 'stopped') or (expected == 'stopped' and line == 'event: meta'):
                break
    if expected == 'stopped':
        data(await client.post(f'/api/v1/agent/run/{run_id}/stop'))
    replay = events((await client.get(f'/api/v1/agent/sessions/{session_id}/run/stream?after=0')).text)
    assert [index for index, _, _ in replay] == list(range(len(replay)))
    final = [payload for _, name, payload in replay if name == 'result']
    assert len(final) == 1 and final[0]['status'] == expected
    detail = data(await client.get(f'/api/v1/agent/sessions/{session_id}'))
    assert len(detail['turns']) == 1
    turn = detail['turns'][0]
    assert turn['status'] == expected and turn['assistant_content'] == final[0]['final_text']
    assert any('Mock' in warning for warning in turn['warnings'])
    if mode == 'deep':
        assert 'Mock 演示研究报告' in turn['report']
        path = final[0]['output']['report_path']
        file_response = await client.get(f'/api/v1/agent/session/{session_id}/file', params={'path': path})
        file_response.raise_for_status()
        assert file_response.content.decode('utf-8') == turn['report']
    repeated = await client.post(f'/api/v1/agent/sessions/{session_id}/run', json=body,
                                 headers={'Idempotency-Key': key})
    assert events(repeated.text) == replay
    assert len(data(await client.get(f'/api/v1/agent/sessions/{session_id}'))['turns']) == 1
    result = await verify_sql(session_id, detail, expected)
    result.update(reconnect=True, unique_result=True, idempotent=True, file_matches=mode == 'deep')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:13000', timeout=90, trust_env=False) as client:
        data(await client.get('/api/v1/identity/bootstrap'))
        config = data(await client.get('/api/v1/agent/config'))
        assert config['default_model'] == 'demo/m1', '拒绝执行：只允许 Mock 演示环境'
        results = []
        for prompt, mode, expected in [
            ('M1 Mock 自动验收：对比 LoRA 与 QLoRA', 'deep', 'done'),
            ('[超时] M1 Mock 自动验收', 'fast', 'timeout'),
            ('M1 Mock 自动验收：手动停止', 'fast', 'stopped'),
        ]:
            results.append(await scenario(client, prompt, mode, expected))
        async with httpx.AsyncClient(base_url='http://127.0.0.1:13000', trust_env=False) as other:
            assert (await other.get('/api/v1/agent/sessions/' + results[0]['session_id'])).status_code == 404
        assert len(data(await client.get('/api/v1/agent/sessions'))['sessions']) >= 2
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / 'smoke.json').write_text(json.dumps({'scenarios': results, 'other_owner_404': True},
                                                   ensure_ascii=False, indent=2), encoding='utf-8')
        print('PASS: Web BFF → Backend → Agent API / Mock Worker → PostgreSQL → SSE / history', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
