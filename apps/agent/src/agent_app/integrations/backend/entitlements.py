"""Authenticated Control -> Backend boundary; Worker never holds this client."""
import os

import httpx

from agent_app.control.metering import GateDenied


class EntitlementClient:
    def __init__(self, *, transport=None):
        self.base_url = os.getenv('BACKEND_ENTITLEMENTS_URL', '').rstrip('/')
        self.token = os.getenv('AGENT_CONTROL_TOKEN', '').strip()
        self.transport = transport

    async def request(self, method, path, payload=None):
        if not self.base_url or not self.token:
            raise GateDenied('BACKEND_UNAVAILABLE', 503)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=20, transport=self.transport,
                    headers={'Authorization': f'Bearer {self.token}'}) as client:
                response = await client.request(method, '/api/v2/agent/internal' + path, json=payload)
            if response.is_error:
                raise GateDenied('BACKEND_AUTHORIZATION_REJECTED', response.status_code)
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GateDenied('BACKEND_UNAVAILABLE', 503) from exc
