"""Vendor-aware CLI snippet generator.

Provides a registry of vendor-specific CLI strategies that produce
deterministic CLI commands from structured plan data.  Each strategy
translates VLAN and interface operations into the appropriate CLI syntax
for a given vendor/platform combination.
"""

from abc import ABC, abstractmethod

from net_agent_harness.models.artifacts import ConfigSnippet
from net_agent_harness.models.changes import PortSpec
from net_agent_harness.models.enums import DeviceVendor, RenderBackendType, RenderRole


# ---------------------------------------------------------------------------
# Base strategy
# ---------------------------------------------------------------------------

class VendorCliStrategy(ABC):
    """Abstract base class for vendor-specific CLI command generation."""

    @abstractmethod
    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[str]:
        """Return an ordered list of CLI commands for the given plan diff.

        Parameters
        ----------
        vlan_additions:
            Mapping of ``{vlan_name: vlan_id}`` for VLANs to create.
        port_changes:
            Interface-level changes from the plan diff.
        """

    def render_comment_banner(self, device_name: str) -> str:
        """Return a comment line identifying the device and vendor."""
        return f"! CLI fallback for {device_name}"


# ---------------------------------------------------------------------------
# Juniper (JunOS / Mist-managed)
# ---------------------------------------------------------------------------

class JuniperCliStrategy(VendorCliStrategy):
    """JunOS ``set`` style commands (EX/QFX series, Mist-managed switches)."""

    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(f"set vlans {vlan_name} vlan-id {vlan_id}")

        for port in port_changes:
            iface = port.interface
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            if mode == "access":
                commands.append(
                    f"set interfaces {iface} unit 0 family ethernet-switching "
                    f"vlan members {port.vlan_id}"
                )
                commands.append(
                    f"set interfaces {iface} unit 0 family ethernet-switching "
                    f"interface-mode access"
                )
            elif mode == "trunk":
                commands.append(
                    f"set interfaces {iface} unit 0 family ethernet-switching "
                    f"interface-mode trunk"
                )
                commands.append(
                    f"set interfaces {iface} unit 0 family ethernet-switching "
                    f"vlan members all"
                )

        return commands


# ---------------------------------------------------------------------------
# Meraki (Dashboard API — no traditional SSH CLI)
# ---------------------------------------------------------------------------

class MerakiCliStrategy(VendorCliStrategy):
    """Meraki Dashboard API pseudo-commands.

    Meraki devices are managed exclusively through the Dashboard API;
    there is no SSH CLI for switch configuration.  These pseudo-commands
    mirror the API operations for human reviewability.
    """

    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(
                f"meraki-api: POST /networks/{{networkId}}/vlans "
                f"body={{\"id\": {vlan_id}, \"name\": \"{vlan_name}\"}}"
            )

        for port in port_changes:
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            if mode == "access":
                commands.append(
                    f"meraki-api: PUT /devices/{{serial}}/switch/ports/{port.interface} "
                    f"body={{\"type\": \"access\", \"vlan\": {port.vlan_id}}}"
                )
            elif mode == "trunk":
                commands.append(
                    f"meraki-api: PUT /devices/{{serial}}/switch/ports/{port.interface} "
                    f"body={{\"type\": \"trunk\", \"allowedVlans\": \"all\"}}"
                )

        return commands

    def render_comment_banner(self, device_name: str) -> str:
        return f"# Meraki API fallback for {device_name} (no SSH CLI available)"


# ---------------------------------------------------------------------------
# Cisco IOS
# ---------------------------------------------------------------------------

class CiscoIosCliStrategy(VendorCliStrategy):
    """Classic Cisco IOS configuration mode commands."""

    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(f"vlan {vlan_id}")
            commands.append(f" name {vlan_name}")
            commands.append("exit")

        for port in port_changes:
            iface = port.interface
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            commands.append(f"interface {iface}")
            if mode == "access":
                commands.append(" switchport mode access")
                commands.append(f" switchport access vlan {port.vlan_id}")
            elif mode == "trunk":
                commands.append(" switchport mode trunk")
                commands.append(" switchport trunk allowed vlan all")
            commands.append("exit")

        return commands


# ---------------------------------------------------------------------------
# Cisco NX-OS
# ---------------------------------------------------------------------------

class CiscoNxosCliStrategy(VendorCliStrategy):
    """Cisco NX-OS configuration mode commands."""

    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(f"vlan {vlan_id}")
            commands.append(f"  name {vlan_name}")
            commands.append("exit")

        for port in port_changes:
            iface = port.interface
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            commands.append(f"interface {iface}")
            if mode == "access":
                commands.append("  switchport")
                commands.append("  switchport mode access")
                commands.append(f"  switchport access vlan {port.vlan_id}")
            elif mode == "trunk":
                commands.append("  switchport")
                commands.append("  switchport mode trunk")
                commands.append("  switchport trunk allowed vlan all")
            commands.append("exit")

        return commands


# ---------------------------------------------------------------------------
# Stubs for vendors without implementation
# ---------------------------------------------------------------------------

class AristaCliStrategy(VendorCliStrategy):
    def render_vlan_commands(self, vlan_additions, port_changes):
        raise NotImplementedError("CLI rendering not yet supported for Arista")


class PaloAltoCliStrategy(VendorCliStrategy):
    def render_vlan_commands(self, vlan_additions, port_changes):
        raise NotImplementedError("CLI rendering not yet supported for Palo Alto")


class FortinetCliStrategy(VendorCliStrategy):
    def render_vlan_commands(self, vlan_additions, port_changes):
        raise NotImplementedError("CLI rendering not yet supported for Fortinet")


# ---------------------------------------------------------------------------
# Registry and dispatch
# ---------------------------------------------------------------------------

_VENDOR_REGISTRY: dict[DeviceVendor, type[VendorCliStrategy]] = {
    DeviceVendor.JUNIPER: JuniperCliStrategy,
    DeviceVendor.MERAKI: MerakiCliStrategy,
    DeviceVendor.CISCO: CiscoIosCliStrategy,  # default Cisco; platform overrides below
    DeviceVendor.ARISTA: AristaCliStrategy,
    DeviceVendor.PALO_ALTO: PaloAltoCliStrategy,
    DeviceVendor.FORTINET: FortinetCliStrategy,
}

# Cisco platform disambiguation: map platform strings to strategy classes
_CISCO_PLATFORM_MAP: dict[str, type[VendorCliStrategy]] = {
    "ios": CiscoIosCliStrategy,
    "ios-xe": CiscoIosCliStrategy,
    "nxos": CiscoNxosCliStrategy,
    "nx-os": CiscoNxosCliStrategy,
}


def _resolve_strategy(
    vendor: DeviceVendor,
    platform: str | None = None,
) -> VendorCliStrategy:
    """Look up the correct CLI strategy for a vendor/platform pair."""
    if vendor == DeviceVendor.CISCO and platform:
        strategy_cls = _CISCO_PLATFORM_MAP.get(platform.lower())
        if strategy_cls:
            return strategy_cls()

    strategy_cls = _VENDOR_REGISTRY.get(vendor)
    if strategy_cls is None:
        raise NotImplementedError(
            f"CLI rendering not yet supported for vendor '{vendor.value}'"
        )
    return strategy_cls()


def build_cli_fallback_snippet(
    *,
    device_name: str,
    vendor: DeviceVendor,
    vlan_additions: dict[str, str],
    port_changes: list[PortSpec] | list = (),
    platform: str | None = None,
) -> ConfigSnippet:
    """Build a CLI fallback ConfigSnippet using the appropriate vendor strategy.

    Parameters
    ----------
    device_name:
        Target device hostname.
    vendor:
        Device vendor enum value used to select the strategy.
    vlan_additions:
        Mapping of ``{vlan_name: vlan_id}`` for VLANs to create.
    port_changes:
        Interface-level changes from the plan diff.
    platform:
        Optional platform string for vendor sub-disambiguation
        (e.g., ``"nxos"`` vs ``"ios"`` for Cisco).
    """
    strategy = _resolve_strategy(vendor, platform)
    cli_commands = strategy.render_vlan_commands(vlan_additions, port_changes)
    banner = strategy.render_comment_banner(device_name)
    rendered_lines = [banner] + cli_commands

    return ConfigSnippet(
        device_name=device_name,
        backend_type=RenderBackendType.CLI,
        render_role=RenderRole.FALLBACK,
        commands=cli_commands,
        rendered_text="\n".join(rendered_lines),
    )
