from typing import Any
import httpx
from ..config import settings


class NetBoxAdapter:
    def __init__(self, base_url: str, token: str, timeout_seconds: int = 10, verify_tls: bool = True):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {'Authorization': f'Token {self.token}'}
        with httpx.Client(timeout=self.timeout_seconds, verify=self.verify_tls, headers=headers) as client:
            response = client.get(f'{self.base_url}{path}', params=params or {})
            response.raise_for_status()
            return response.json()

    def get_devices(self, site: str | None = None, name: str | None = None, limit: int = 20) -> dict[str, Any]:
        params: dict[str, Any] = {'limit': limit}
        if site:
            params['site'] = site
        if name:
            params['name'] = name
        return self._get('/api/dcim/devices/', params)

    def get_interfaces(self, device_id: int, limit: int = 100) -> dict[str, Any]:
        return self._get('/api/dcim/interfaces/', {'device_id': device_id, 'limit': limit})

    def get_ip_addresses(self, device_id: int, limit: int = 100) -> dict[str, Any]:
        return self._get('/api/ipam/ip-addresses/', {'device_id': device_id, 'limit': limit})


def build_netbox_adapter_from_settings() -> NetBoxAdapter:
    if not settings.netbox_url or not settings.netbox_token:
        raise ValueError('NetBox settings are incomplete. Set NET_AGENT_NETBOX_URL and NET_AGENT_NETBOX_TOKEN.')
    return NetBoxAdapter(
        base_url=settings.netbox_url,
        token=settings.netbox_token.get_secret_value(),
        timeout_seconds=settings.netbox_timeout_seconds,
        verify_tls=settings.netbox_verify_tls,
    )
