"""Vendor-aware CLI snippet generator.

Provides a registry of vendor-specific CLI strategies that produce
deterministic CLI commands from structured plan data.  Each strategy
translates VLAN and interface operations into the appropriate CLI syntax
for a given vendor/platform combination.
"""

import ipaddress
from abc import ABC, abstractmethod
from collections.abc import Sequence

from net_agent_harness.models.artifacts import ConfigSnippet
from net_agent_harness.models.changes import PortSpec, SviChangeOperation
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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        """Return an ordered list of CLI commands for the given plan diff.

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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(f"set vlans {vlan_name} vlan-id {vlan_id}")

        for removed_vlan_id in vlan_removals:
            commands.append(f"delete vlans vlan-id {removed_vlan_id}")

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
                if getattr(port, "native_vlan", None) is not None:
                    commands.append(
                        f"set interfaces {iface} unit 0 family ethernet-switching "
                        f"native-vlan-id {port.native_vlan}"
                    )

        for svi in svi_changes:
            if svi.status != "apply":
                continue
            if svi.op == "create":
                if svi.ip_address and svi.prefix_length is not None:
                    commands.append(
                        f"set interfaces irb unit {svi.vlan_id} family inet "
                        f"address {svi.ip_address}/{svi.prefix_length}"
                    )
                    commands.append(
                        f"set vlans vlan-id {svi.vlan_id} l3-interface irb.{svi.vlan_id}"
                    )
            elif svi.op == "remove":
                commands.append(f"delete interfaces irb unit {svi.vlan_id}")

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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(
                f"meraki-api: POST /networks/{{networkId}}/vlans "
                f"body={{\"id\": {vlan_id}, \"name\": \"{vlan_name}\"}}"
            )

        for removed_vlan_id in vlan_removals:
            commands.append(
                f"meraki-api: DELETE /networks/{{networkId}}/vlans/{removed_vlan_id}"
            )

        for port in port_changes:
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            if mode == "access":
                commands.append(
                    f"meraki-api: PUT /devices/{{serial}}/switch/ports/{port.interface} "
                    f"body={{\"type\": \"access\", \"vlan\": {port.vlan_id}}}"
                )
            elif mode == "trunk":
                if getattr(port, "native_vlan", None) is not None:
                    commands.append(
                        f"meraki-api: PUT /devices/{{serial}}/switch/ports/{port.interface} "
                        f"body={{\"type\": \"trunk\", \"allowedVlans\": \"all\", \"vlan\": {port.native_vlan}}}"
                    )
                else:
                    commands.append(
                        f"meraki-api: PUT /devices/{{serial}}/switch/ports/{port.interface} "
                        f"body={{\"type\": \"trunk\", \"allowedVlans\": \"all\"}}"
                    )

        for svi in svi_changes:
            if svi.status != "apply":
                continue
            if svi.op == "create":
                if svi.ip_address and svi.prefix_length is not None:
                    commands.append(
                        f"meraki-api: PUT /networks/{{networkId}}/appliance/vlans/{svi.vlan_id} "
                        f"body={{\"applianceIp\": \"{svi.ip_address}\", \"prefix_length\": {svi.prefix_length}}}"
                    )
            elif svi.op == "remove":
                commands.append(
                    f"meraki-api: DELETE /networks/{{networkId}}/appliance/vlans/{svi.vlan_id}"
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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(f"vlan {vlan_id}")
            commands.append(f" name {vlan_name}")
            commands.append("exit")

        for removed_vlan_id in vlan_removals:
            commands.append(f"no vlan {removed_vlan_id}")

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
                if getattr(port, "native_vlan", None) is not None:
                    commands.append(f" switchport trunk native vlan {port.native_vlan}")
            commands.append("exit")

        for svi in svi_changes:
            if svi.status != "apply":
                continue
            if svi.op == "create":
                if svi.ip_address and svi.prefix_length is not None:
                    netmask = ipaddress.IPv4Network(f"0.0.0.0/{svi.prefix_length}").netmask
                    commands.append(f"interface {svi.interface or f'Vlan{svi.vlan_id}'}")
                    commands.append(f" ip address {svi.ip_address} {netmask}")
                    commands.append(" no shutdown")
                    commands.append("exit")
            elif svi.op == "remove":
                commands.append(f"no interface {svi.interface or f'Vlan{svi.vlan_id}'}")

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
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        commands: list[str] = []

        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(f"vlan {vlan_id}")
            commands.append(f"  name {vlan_name}")
            commands.append("exit")

        for removed_vlan_id in vlan_removals:
            commands.append(f"no vlan {removed_vlan_id}")

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
                if getattr(port, "native_vlan", None) is not None:
                    commands.append(f"  switchport trunk native vlan {port.native_vlan}")
            commands.append("exit")

        for svi in svi_changes:
            if svi.status != "apply":
                continue
            if svi.op == "create":
                if svi.ip_address and svi.prefix_length is not None:
                    commands.append(f"interface {svi.interface or f'Vlan{svi.vlan_id}'}")
                    commands.append("  no shutdown")
                    commands.append(f"  ip address {svi.ip_address}/{svi.prefix_length}")
                    commands.append("exit")
            elif svi.op == "remove":
                commands.append(f"no interface {svi.interface or f'Vlan{svi.vlan_id}'}")

        return commands


# ---------------------------------------------------------------------------
# Stubs for vendors without implementation
# ---------------------------------------------------------------------------

class AristaCliStrategy(VendorCliStrategy):
    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        raise NotImplementedError("CLI rendering not yet supported for Arista")


class PaloAltoCliStrategy(VendorCliStrategy):
    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        raise NotImplementedError("CLI rendering not yet supported for Palo Alto")


class FortinetCliStrategy(VendorCliStrategy):
    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        raise NotImplementedError("CLI rendering not yet supported for Fortinet")


class GenericCliStrategy(VendorCliStrategy):
    """Fallback strategy for unknown or unrecognized vendors.

    Produces human-readable comment lines that identify the required changes
    without vendor-specific syntax, so a human operator can act on them.
    """

    def render_vlan_commands(
        self,
        vlan_additions: dict[str, str],
        port_changes: list[PortSpec],
        vlan_removals: Sequence[int] = (),
        svi_changes: Sequence[SviChangeOperation] = (),
    ) -> list[str]:
        commands: list[str] = []
        for vlan_name, vlan_id in vlan_additions.items():
            commands.append(f"# CREATE VLAN {vlan_id} name {vlan_name}")
        for removed_vlan_id in vlan_removals:
            commands.append(f"# REMOVE VLAN {removed_vlan_id}")
        for port in port_changes:
            mode = port.mode.value if hasattr(port.mode, "value") else port.mode
            line = f"# SET interface {port.interface} mode {mode} vlan {port.vlan_id}"
            if mode == "trunk" and getattr(port, "native_vlan", None) is not None:
                line += f" native_vlan {port.native_vlan}"
            commands.append(line)
        for svi in svi_changes:
            if svi.status != "apply":
                continue
            if svi.op == "create":
                if svi.ip_address and svi.prefix_length is not None:
                    commands.append(
                        f"# CREATE SVI vlan {svi.vlan_id} ip {svi.ip_address}/{svi.prefix_length}"
                    )
            elif svi.op == "remove":
                commands.append(f"# REMOVE SVI vlan {svi.vlan_id}")
        return commands

    def render_comment_banner(self, device_name: str) -> str:
        return (
            f"# CLI fallback for {device_name} "
            f"(vendor/platform unknown — commands require manual review)"
        )


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
    DeviceVendor.OTHER: GenericCliStrategy,
}

# Cisco platform disambiguation: map platform strings to strategy classes
_CISCO_PLATFORM_MAP: dict[str, type[VendorCliStrategy]] = {
    "ios": CiscoIosCliStrategy,
    "ios-xe": CiscoIosCliStrategy,
    "nxos": CiscoNxosCliStrategy,
    "nx-os": CiscoNxosCliStrategy,
}

# Platform-to-vendor inference: used when vendor is OTHER or absent
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
) -> VendorCliStrategy:
    """Look up the correct CLI strategy for a vendor/platform pair.

    When ``vendor`` is ``None`` or ``OTHER``, the platform string is used to
    infer the vendor before falling back to the generic strategy.
    """
    effective_vendor = vendor

    # Infer vendor from platform when vendor is absent or unspecified
    if (effective_vendor is None or effective_vendor == DeviceVendor.OTHER) and platform:
        effective_vendor = _PLATFORM_VENDOR_MAP.get(platform.lower(), effective_vendor)

    if effective_vendor == DeviceVendor.CISCO and platform:
        strategy_cls = _CISCO_PLATFORM_MAP.get(platform.lower())
        if strategy_cls:
            return strategy_cls()

    strategy_cls = _VENDOR_REGISTRY.get(effective_vendor or DeviceVendor.OTHER)
    if strategy_cls is None:
        return GenericCliStrategy()
    return strategy_cls()


def build_cli_fallback_snippet(
    *,
    device_name: str,
    vendor: DeviceVendor | None,
    vlan_additions: dict[str, str],
    port_changes: Sequence[PortSpec] = (),
    platform: str | None = None,
    vlan_removals: Sequence[int] = (),
    svi_changes: Sequence[SviChangeOperation] = (),
) -> ConfigSnippet:
    """Build a CLI fallback ConfigSnippet using the appropriate vendor strategy.

    Parameters
    ----------
    device_name:
        Target device hostname.
    vendor:
        Device vendor enum value used to select the strategy.  When ``None``
        or ``DeviceVendor.OTHER``, the ``platform`` string is consulted for
        vendor inference before falling back to the generic strategy.
    vlan_additions:
        Mapping of ``{vlan_name: vlan_id}`` for VLANs to create.
    port_changes:
        Interface-level changes from the plan diff.
    platform:
        Optional platform string for vendor sub-disambiguation
        (e.g., ``"nxos"`` vs ``"ios"`` for Cisco).
    vlan_removals:
        VLAN IDs to remove.
    svi_changes:
        SVI create/remove operations from the plan diff.
    """
    strategy = _resolve_strategy(vendor, platform)
    cli_commands = strategy.render_vlan_commands(
        vlan_additions,
        list(port_changes),
        vlan_removals=vlan_removals,
        svi_changes=svi_changes,
    )
    banner = strategy.render_comment_banner(device_name)
    rendered_lines = [banner] + cli_commands

    return ConfigSnippet(
        device_name=device_name,
        backend_type=RenderBackendType.CLI,
        render_role=RenderRole.FALLBACK,
        commands=cli_commands,
        rendered_text="\n".join(rendered_lines),
    )
