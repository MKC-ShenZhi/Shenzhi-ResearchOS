import os
import httpx
from agent_contracts import AgentConfigWire
from pydantic import ValidationError
from app.core.errors import BusinessError


async def get_capabilities():
    origin = os.getenv('AGENT_INTERNAL_URL', '').rstrip('/')
    token = os.getenv('AGENT_SERVICE_TOKEN', '')
    if not origin or not token:
        raise BusinessError(10002, 'Agent 地址或服务凭据未配置', 503)
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(origin + '/internal/v1/config', headers={'Authorization': f'Bearer {token}'})
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or 'models' not in payload or 'skills' not in payload:
            raise ValueError('missing configuration')
        config = AgentConfigWire.model_validate(payload)
        if any(not isinstance(m.get('value'), str) or not isinstance(m.get('label'), str)
               or not isinstance(m.get('enabled'), bool) for m in config.models):
            raise ValueError('invalid model')
        if any(not s.get('name') for s in config.skills):
            raise ValueError('invalid skill')
    except (httpx.HTTPError, ValidationError, ValueError):
        raise BusinessError(10002, 'Agent 能力配置不可用或响应无效，请检查服务与凭据', 503) from None
    return {**config.model_dump(mode='json'), 'source': 'Agent /internal/v1/config',
            'tools_status': 'not_connected', 'read_only': True}
