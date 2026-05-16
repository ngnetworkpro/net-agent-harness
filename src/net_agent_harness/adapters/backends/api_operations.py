"""Vendor-aware API snippet generator.

Provides a registry of vendor-specific API strategies that produce
deterministic API operations from structured plan data.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
import json

from net_agent_harness.models.artifacts import ConfigSnippet
from net_agent_harness.models.changes import PortSpec
from net_agent_harness.models.enums import DeviceVendor, RenderBackendType, RenderRole

# ---------------------------------------------------------------------------
# Base strategy
# ---------------------------------------------------------------------------

class VendorApiStrategy(ABC):
    """Abstract base class for vendor-specific API operation generation."""

    @abstractmethod
    def build_vlan_operations(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[dict]:
        """Return an ordered list of API operations for the given plan diff.

        Parameters
        ----------
        vlan_additions:
            Mapping of ``{vlan_name: vlan_id}`` for VLANs to create.
        port_changes:
            Interface-level changes from the plan diff.
        """

# ---------------------------------------------------------------------------
# Juniper Mist
# ---------------------------------------------------------------------------

class MistApiStrategy(VendorApiStrategy):
    """Juniper Mist API operations."""

    def build_vlan_operations(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[dict]:
        operations = []
        for vlan_name, vlan_id in vlan_additions.items():
            operations.append({
                "action": "create_vlan",
                "endpoint": "/sites/{site_id}/vlans",
                "payload": {"vlan_id": int(vlan_id), "name": vlan_name}
            })
        for port in port_changes:
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            if mode == "access":
                operations.append({
                    "action": "update_port",
                    "port": port.interface,
                    "payload": {"mode": "access", "vlan_id": port.vlan_id}
                })
            elif mode == "trunk":
                operations.append({
                    "action": "update_port",
                    "port": port.interface,
                    "payload": {"mode": "trunk", "allowed_vlans": "all"}
                })
        return operations

# ---------------------------------------------------------------------------
# Cisco Meraki
# ---------------------------------------------------------------------------

class MerakiApiStrategy(VendorApiStrategy):
    """Cisco Meraki Dashboard API operations."""

    def build_vlan_operations(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[dict]:
        operations = []
        for vlan_name, vlan_id in vlan_additions.items():
            operations.append({
                "action": "create_vlan",
                "endpoint": "/networks/{networkId}/vlans",
                "payload": {"id": int(vlan_id), "name": vlan_name}
            })
        for port in port_changes:
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            if mode == "access":
                operations.append({
                    "action": "update_port",
                    "endpoint": f"/devices/{{serial}}/switch/ports/{port.interface}",
                    "payload": {"type": "access", "vlan": port.vlan_id}
                })
            elif mode == "trunk":
                operations.append({
                    "action": "update_port",
                    "endpoint": f"/devices/{{serial}}/switch/ports/{port.interface}",
                    "payload": {"type": "trunk", "allowedVlans": "all"}
                })
        return operations

# ---------------------------------------------------------------------------
# Stubs for unsupported vendors
# ---------------------------------------------------------------------------

class UnsupportedApiStrategy(VendorApiStrategy):
    def __init__(self, vendor_name: str):
        self.vendor_name = vendor_name

    def build_vlan_operations(self, vlan_additions, port_changes):
        raise NotImplementedError(f"API rendering not yet supported for {self.vendor_name}")

class AristaApiStrategy(UnsupportedApiStrategy):
    def __init__(self):
        super().__init__("Arista")

class PaloAltoApiStrategy(UnsupportedApiStrategy):
    def __init__(self):
        super().__init__("Palo Alto")

class FortinetApiStrategy(UnsupportedApiStrategy):
    def __init__(self):
        super().__init__("Fortinet")

class CiscoIosApiStrategy(UnsupportedApiStrategy):
    def __init__(self):
        super().__init__("Cisco IOS")

class CiscoNxosApiStrategy(UnsupportedApiStrategy):
    def __init__(self):
        super().__init__("Cisco NX-OS")

# ---------------------------------------------------------------------------
# Registry and dispatch
# ---------------------------------------------------------------------------

_VENDOR_REGISTRY: dict[DeviceVendor, type[VendorApiStrategy]] = {
    DeviceVendor.JUNIPER: MistApiStrategy,
    DeviceVendor.MERAKI: MerakiApiStrategy,
    DeviceVendor.CISCO: CiscoIosApiStrategy,
    DeviceVendor.ARISTA: AristaApiStrategy,
    DeviceVendor.PALO_ALTO: PaloAltoApiStrategy,
    DeviceVendor.FORTINET: FortinetApiStrategy,
}

_CISCO_PLATFORM_MAP: dict[str, type[VendorApiStrategy]] = {
    "ios": CiscoIosApiStrategy,
    "ios-xe": CiscoIosApiStrategy,
    "nxos": CiscoNxosApiStrategy,
    "nx-os": CiscoNxosApiStrategy,
}

_PLATFORM_VENDOR_MAP: dict[str, DeviceVendor] = {
    "mist": DeviceVendor.JUNIPER,
    "junos": DeviceVendor.JUNIPER,
    "ios": DeviceVendor.CISCO,
    "ios-xe": DeviceVendor.CISCO,
    "ios-xr": DeviceVendor.CISCO,
    "nxos": DeviceVendor.CISCO,
    "nx-os": DeviceVendor.CISCO,
    "eos": DeviceVendor.ARISTA,
    "meraki": DeviceVendor.MERAKI,
    "panos": DeviceVendor.PALO_ALTO,
}

def _resolve_strategy(
    vendor: DeviceVendor | None,
    platform: str | None = None,
) -> VendorApiStrategy:
    effective_vendor = vendor
    if (effective_vendor is None or effective_vendor == DeviceVendor.OTHER) and platform:
        effective_vendor = _PLATFORM_VENDOR_MAP.get(platform.lower(), effective_vendor)

    if effective_vendor == DeviceVendor.CISCO and platform:
        strategy_cls = _CISCO_PLATFORM_MAP.get(platform.lower())
        if strategy_cls:
            return strategy_cls()

    strategy_cls = _VENDOR_REGISTRY.get(effective_vendor or DeviceVendor.OTHER)
    if strategy_cls is None:
        raise NotImplementedError(f"API rendering not yet supported for vendor {effective_vendor}")
    return strategy_cls()

def build_api_primary_snippet(
    device_name: str,
    vendor: DeviceVendor | None,
    vlan_additions: dict[str, str],
    port_changes: Sequence[PortSpec],
    platform: str | None = None,
) -> ConfigSnippet:
    strategy = _resolve_strategy(vendor, platform)
    operations = strategy.build_vlan_operations(vlan_additions, list(port_changes))
    
    api_payload = {"operations": operations}
    rendered_text = json.dumps(api_payload, indent=2)

    return ConfigSnippet(
        device_name=device_name,
        backend_type=RenderBackendType.API,
        render_role=RenderRole.PRIMARY,
        api_payload=api_payload,
        rendered_text=rendered_text,
        commands=[]
    )
