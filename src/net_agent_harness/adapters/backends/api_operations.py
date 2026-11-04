"""Vendor-aware API snippet generator.

Provides a registry of vendor-specific API strategies that produce
deterministic API operations from structured plan data.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any  # Any is used for heterogeneous JSON API operation payloads

from net_agent_harness.models.artifacts import ApiRequestPayload, ConfigSnippet
from net_agent_harness.models.changes import PortSpec, SviChangeOperation
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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[dict[str, Any]]:
        """Return an ordered list of API operations for the given plan diff.

        Parameters
        ----------
        vlan_additions:
            Mapping of ``{vlan_name: vlan_id}`` for VLANs to create.
        port_changes:
            Interface-level changes from the plan diff.
        vlan_removals:
            VLAN IDs to remove.
        svi_changes:
            SVI create/remove operations from the plan diff.
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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[dict[str, Any]]:
        operations: list[dict[str, Any]] = []
        for vlan_name, vlan_id in vlan_additions.items():
            operations.append({
                "action": "create_vlan",
                "endpoint": "/sites/{site_id}/vlans",
                "payload": {"vlan_id": int(vlan_id), "name": vlan_name}
            })
        for removed_vlan_id in vlan_removals:
            operations.append({
                "action": "delete_vlan",
                "endpoint": f"/sites/{{site_id}}/vlans/{int(removed_vlan_id)}",
                "payload": {"vlan_id": int(removed_vlan_id)}
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
                payload: dict[str, object] = {"mode": "trunk", "allowed_vlans": "all"}
                native_vlan = getattr(port, "native_vlan", None)
                if native_vlan is not None:
                    payload["native_vlan"] = native_vlan
                operations.append({
                    "action": "update_port",
                    "port": port.interface,
                    "payload": payload
                })
        for svi in svi_changes:
            if svi.status != "apply":
                continue
            if svi.op == "create":
                operations.append({
                    "action": "create_svi",
                    "endpoint": "/sites/{site_id}/Setting",
                    "interface": svi.interface or f"irb.{svi.vlan_id}",
                    "payload": {
                        "vlan_id": svi.vlan_id,
                        "ip_address": svi.ip_address,
                        "prefix_length": svi.prefix_length,
                    }
                })
            elif svi.op == "remove":
                operations.append({
                    "action": "delete_svi",
                    "endpoint": "/sites/{site_id}/Setting",
                    "interface": svi.interface or f"irb.{svi.vlan_id}",
                    "payload": {"vlan_id": svi.vlan_id}
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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[dict[str, Any]]:
        operations: list[dict[str, Any]] = []
        for vlan_name, vlan_id in vlan_additions.items():
            operations.append({
                "action": "create_vlan",
                "endpoint": "/networks/{networkId}/vlans",
                "payload": {"id": int(vlan_id), "name": vlan_name}
            })
        for removed_vlan_id in vlan_removals:
            operations.append({
                "action": "delete_vlan",
                "endpoint": f"/networks/{{networkId}}/vlans/{int(removed_vlan_id)}",
                "payload": {"id": int(removed_vlan_id)}
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
                payload: dict[str, object] = {"type": "trunk", "allowedVlans": "all"}
                native_vlan = getattr(port, "native_vlan", None)
                if native_vlan is not None:
                    payload["vlan"] = native_vlan
                operations.append({
                    "action": "update_port",
                    "endpoint": f"/devices/{{serial}}/switch/ports/{port.interface}",
                    "payload": payload
                })
        for svi in svi_changes:
            if svi.status != "apply":
                continue
            if svi.op == "create":
                operations.append({
                    "action": "update_vlan_svi",
                    "endpoint": f"/networks/{{networkId}}/appliance/vlans/{svi.vlan_id}",
                    "payload": {
                        "id": svi.vlan_id,
                        "applianceIp": svi.ip_address,
                        "prefix_length": svi.prefix_length,
                    }
                })
            elif svi.op == "remove":
                operations.append({
                    "action": "delete_vlan_svi",
                    "endpoint": f"/networks/{{networkId}}/appliance/vlans/{svi.vlan_id}",
                    "payload": {"id": svi.vlan_id}
                })
        return operations

# ---------------------------------------------------------------------------
# Stubs for unsupported vendors
# ---------------------------------------------------------------------------

class UnsupportedApiStrategy(VendorApiStrategy):
    def __init__(self, vendor_name: str) -> None:
        self.vendor_name = vendor_name

    def build_vlan_operations(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(f"API rendering not yet supported for {self.vendor_name}")

class AristaApiStrategy(UnsupportedApiStrategy):
    def __init__(self) -> None:
        super().__init__("Arista")

class PaloAltoApiStrategy(UnsupportedApiStrategy):
    def __init__(self) -> None:
        super().__init__("Palo Alto")

class FortinetApiStrategy(UnsupportedApiStrategy):
    def __init__(self) -> None:
        super().__init__("Fortinet")

class CiscoIosApiStrategy(UnsupportedApiStrategy):
    def __init__(self) -> None:
        super().__init__("Cisco IOS")

class CiscoNxosApiStrategy(UnsupportedApiStrategy):
    def __init__(self) -> None:
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
    vlan_removals: Sequence[int] = (),
    svi_changes: Sequence[SviChangeOperation] = (),
) -> ConfigSnippet:
    strategy = _resolve_strategy(vendor, platform)
    operations = strategy.build_vlan_operations(
        vlan_additions,
        list(port_changes),
        vlan_removals=vlan_removals,
        svi_changes=svi_changes,
    )

    api_payload = ApiRequestPayload(
        method="POST",
        path="/operations/batch",
        body={"operations": operations},
    )
    rendered_text = json.dumps(api_payload.model_dump(), indent=2)

    return ConfigSnippet(
        device_name=device_name,
        backend_type=RenderBackendType.API,
        render_role=RenderRole.PRIMARY,
        api_payload=api_payload,
        rendered_text=rendered_text,
        commands=[],
    )
