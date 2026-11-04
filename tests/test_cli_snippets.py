import pytest

from net_agent_harness.adapters.backends.cli_snippets import (
    AristaCliStrategy,
    CiscoIosCliStrategy,
    CiscoNxosCliStrategy,
    FortinetCliStrategy,
    GenericCliStrategy,
    JuniperCliStrategy,
    MerakiCliStrategy,
    PaloAltoCliStrategy,
    build_cli_fallback_snippet,
)
from net_agent_harness.models.changes import PortSpec, SviChangeOperation
from net_agent_harness.models.enums import (
    DeviceVendor,
    RenderBackendType,
    RenderRole,
    SwitchportMode,
)


def _trunk_port(interface: str, vlan_id: int, native_vlan: int | None = None) -> PortSpec:
    return PortSpec(
        interface=interface,
        vlan_id=vlan_id,
        mode=SwitchportMode.TRUNK,
        native_vlan=native_vlan,
    )

# ---------------------------------------------------------------------------
# Juniper
# ---------------------------------------------------------------------------

class TestJuniperCliStrategy:
    def test_vlan_creation(self):
        strategy = JuniperCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={"Engineering": "220"},
            port_changes=[],
        )
        assert "set vlans Engineering vlan-id 220" in cmds

    def test_access_port(self):
        strategy = JuniperCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="ge-0/0/1", vlan_id=220, mode="access")],
        )
        assert any("vlan members 220" in c for c in cmds)
        assert any("interface-mode access" in c for c in cmds)

    def test_trunk_port(self):
        strategy = JuniperCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="ge-0/0/2", vlan_id=100, mode="trunk")],
        )
        assert any("interface-mode trunk" in c for c in cmds)
        assert any("vlan members all" in c for c in cmds)

    def test_combined_vlan_and_port(self):
        strategy = JuniperCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={"Voice": "221"},
            port_changes=[PortSpec(interface="ge-0/0/5", vlan_id=221, mode="access")],
        )
        assert "set vlans Voice vlan-id 221" in cmds
        assert any("vlan members 221" in c for c in cmds)


# ---------------------------------------------------------------------------
# Meraki
# ---------------------------------------------------------------------------

class TestMerakiCliStrategy:
    def test_vlan_creation(self):
        strategy = MerakiCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={"Guest": "300"},
            port_changes=[],
        )
        assert len(cmds) == 1
        assert "POST" in cmds[0]
        assert "300" in cmds[0]
        assert "Guest" in cmds[0]

    def test_access_port(self):
        strategy = MerakiCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="5", vlan_id=300, mode="access")],
        )
        assert len(cmds) == 1
        assert "PUT" in cmds[0]
        assert "access" in cmds[0]
        assert "300" in cmds[0]

    def test_trunk_port(self):
        strategy = MerakiCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="9", vlan_id=100, mode="trunk")],
        )
        assert len(cmds) == 1
        assert "PUT" in cmds[0]
        assert "trunk" in cmds[0]
        assert "all" in cmds[0]

    def test_comment_banner(self):
        strategy = MerakiCliStrategy()
        banner = strategy.render_comment_banner("fw1")
        assert "Meraki" in banner
        assert "fw1" in banner
        assert "no SSH CLI" in banner


# ---------------------------------------------------------------------------
# Cisco IOS
# ---------------------------------------------------------------------------

class TestCiscoIosCliStrategy:
    def test_vlan_creation(self):
        strategy = CiscoIosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={"Data": "100"},
            port_changes=[],
        )
        assert "vlan 100" in cmds
        assert " name Data" in cmds
        assert "exit" in cmds

    def test_access_port(self):
        strategy = CiscoIosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="GigabitEthernet0/1", vlan_id=100, mode="access")],
        )
        assert "interface GigabitEthernet0/1" in cmds
        assert " switchport mode access" in cmds
        assert " switchport access vlan 100" in cmds

    def test_trunk_port(self):
        strategy = CiscoIosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="GigabitEthernet0/2", vlan_id=100, mode="trunk")],
        )
        assert "interface GigabitEthernet0/2" in cmds
        assert " switchport mode trunk" in cmds
        assert " switchport trunk allowed vlan all" in cmds


# ---------------------------------------------------------------------------
# Cisco NX-OS
# ---------------------------------------------------------------------------

class TestCiscoNxosCliStrategy:
    def test_vlan_creation(self):
        strategy = CiscoNxosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={"Servers": "500"},
            port_changes=[],
        )
        assert "vlan 500" in cmds
        assert "  name Servers" in cmds

    def test_access_port(self):
        strategy = CiscoNxosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="Ethernet1/1", vlan_id=500, mode="access")],
        )
        assert "interface Ethernet1/1" in cmds
        assert "  switchport" in cmds
        assert "  switchport mode access" in cmds
        assert "  switchport access vlan 500" in cmds

    def test_trunk_port(self):
        strategy = CiscoNxosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[PortSpec(interface="Ethernet1/2", vlan_id=500, mode="trunk")],
        )
        assert "interface Ethernet1/2" in cmds
        assert "  switchport" in cmds
        assert "  switchport mode trunk" in cmds
        assert "  switchport trunk allowed vlan all" in cmds


# ---------------------------------------------------------------------------
# Platform-based Cisco dispatch
# ---------------------------------------------------------------------------

class TestCiscoPlatformDispatch:
    def test_ios_platform_produces_ios_commands(self):
        snippet = build_cli_fallback_snippet(
            device_name="sw1",
            vendor=DeviceVendor.CISCO,
            vlan_additions={"Data": "10"},
            port_changes=[],
            platform="ios",
        )
        # IOS uses single-space indented " name"
        assert " name Data" in snippet.commands

    def test_nxos_platform_produces_nxos_commands(self):
        snippet = build_cli_fallback_snippet(
            device_name="n9k-1",
            vendor=DeviceVendor.CISCO,
            vlan_additions={"Servers": "500"},
            port_changes=[PortSpec(interface="Ethernet1/1", vlan_id=500, mode="access")],
            platform="nxos",
        )
        # NX-OS uses double-space indented "  switchport"
        assert "  switchport" in snippet.commands
        assert "  switchport mode access" in snippet.commands

    def test_unknown_cisco_platform_defaults_to_ios(self):
        snippet = build_cli_fallback_snippet(
            device_name="c3750",
            vendor=DeviceVendor.CISCO,
            vlan_additions={"Test": "99"},
            port_changes=[],
            platform="unknown-platform",
        )
        # Should fall back to IOS (default Cisco strategy)
        assert " name Test" in snippet.commands


# ---------------------------------------------------------------------------
# Unsupported / stub vendors
# ---------------------------------------------------------------------------

class TestUnsupportedVendors:
    def test_arista_raises(self):
        strategy = AristaCliStrategy()
        with pytest.raises(NotImplementedError, match="Arista"):
            strategy.render_vlan_commands({}, [])

    def test_palo_alto_raises(self):
        strategy = PaloAltoCliStrategy()
        with pytest.raises(NotImplementedError, match="Palo Alto"):
            strategy.render_vlan_commands({}, [])

    def test_fortinet_raises(self):
        strategy = FortinetCliStrategy()
        with pytest.raises(NotImplementedError, match="Fortinet"):
            strategy.render_vlan_commands({}, [])

    def test_other_vendor_uses_generic_strategy(self):
        snippet = build_cli_fallback_snippet(
            device_name="unknown-box",
            vendor=DeviceVendor.OTHER,
            vlan_additions={"x": "1"},
            port_changes=[],
        )
        assert snippet.backend_type == RenderBackendType.CLI
        assert snippet.render_role == RenderRole.FALLBACK
        assert "unknown-box" in snippet.rendered_text
        assert "# CREATE VLAN 1 name x" in snippet.commands

    def test_none_vendor_uses_generic_strategy(self):
        snippet = build_cli_fallback_snippet(
            device_name="mystery-box",
            vendor=None,
            vlan_additions={"mgmt": "99"},
            port_changes=[],
        )
        assert snippet.backend_type == RenderBackendType.CLI
        assert "mystery-box" in snippet.rendered_text
        assert "# CREATE VLAN 99 name mgmt" in snippet.commands

    def test_none_vendor_infers_from_mist_platform(self):
        snippet = build_cli_fallback_snippet(
            device_name="sw1",
            vendor=None,
            vlan_additions={"Engineering": "220"},
            port_changes=[],
            platform="mist",
        )
        # mist → JUNIPER strategy: expect JunOS-style "set vlans <name> vlan-id <id>" command
        assert "set vlans Engineering vlan-id 220" in snippet.commands

    def test_other_vendor_infers_from_ios_platform(self):
        snippet = build_cli_fallback_snippet(
            device_name="c2960",
            vendor=DeviceVendor.OTHER,
            vlan_additions={"Data": "10"},
            port_changes=[],
            platform="ios",
        )
        # ios → CISCO IOS strategy: expect IOS-style " name" command
        assert " name Data" in snippet.commands


# ---------------------------------------------------------------------------
# build_cli_fallback_snippet integration
# ---------------------------------------------------------------------------

class TestBuildCliFallbackSnippet:
    def test_returns_config_snippet_with_correct_metadata(self):
        snippet = build_cli_fallback_snippet(
            device_name="sw1",
            vendor=DeviceVendor.JUNIPER,
            vlan_additions={"users": "11"},
            port_changes=[],
        )
        assert snippet.device_name == "sw1"
        assert snippet.backend_type == RenderBackendType.CLI
        assert snippet.render_role == RenderRole.FALLBACK
        assert isinstance(snippet.commands, list)
        assert len(snippet.commands) > 0
        assert snippet.rendered_text is not None

    def test_rendered_text_includes_banner_and_commands(self):
        snippet = build_cli_fallback_snippet(
            device_name="sw1",
            vendor=DeviceVendor.JUNIPER,
            vlan_additions={"printers": "21"},
            port_changes=[],
        )
        assert "CLI fallback for sw1" in snippet.rendered_text
        assert "set vlans printers vlan-id 21" in snippet.rendered_text

    def test_meraki_snippet_uses_api_banner(self):
        snippet = build_cli_fallback_snippet(
            device_name="fw1",
            vendor=DeviceVendor.MERAKI,
            vlan_additions={"Guest": "300"},
            port_changes=[],
        )
        assert "Meraki API fallback" in snippet.rendered_text
        assert "POST" in snippet.rendered_text

    def test_forwards_vlan_removals_and_svi_changes(self):
        snippet = build_cli_fallback_snippet(
            device_name="sw1",
            vendor=DeviceVendor.JUNIPER,
            vlan_additions={},
            port_changes=[],
            vlan_removals=[220],
            svi_changes=[
                SviChangeOperation(
                    op="remove",
                    vlan_id=220,
                    status="apply",
                )
            ],
        )
        assert "delete vlans vlan-id 220" in snippet.commands
        assert "delete interfaces irb unit 220" in snippet.commands


class TestExtendedVlanRemovalsNativeVlanAndSvi:
    def test_juniper_removals_native_vlan_and_svi(self):
        strategy = JuniperCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[_trunk_port("ge-0/0/2", vlan_id=1, native_vlan=99)],
            vlan_removals=[220],
            svi_changes=[
                SviChangeOperation(
                    op="create",
                    vlan_id=100,
                    ip_address="10.100.0.1",
                    prefix_length=24,
                    status="apply",
                ),
                SviChangeOperation(
                    op="remove",
                    vlan_id=220,
                    status="apply",
                ),
            ],
        )
        assert "delete vlans vlan-id 220" in cmds
        assert (
            "set interfaces ge-0/0/2 unit 0 family ethernet-switching native-vlan-id 99"
            in cmds
        )
        assert (
            "set interfaces irb unit 100 family inet address 10.100.0.1/24"
            in cmds
        )
        assert "set vlans vlan-id 100 l3-interface irb.100" in cmds
        assert "delete interfaces irb unit 220" in cmds

    def test_meraki_removals_and_svi(self):
        strategy = MerakiCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[_trunk_port("9", vlan_id=100, native_vlan=50)],
            vlan_removals=[300],
            svi_changes=[
                SviChangeOperation(
                    op="create",
                    vlan_id=100,
                    ip_address="10.100.0.1",
                    prefix_length=24,
                    status="apply",
                ),
                SviChangeOperation(
                    op="remove",
                    vlan_id=300,
                    status="apply",
                ),
            ],
        )
        assert "meraki-api: DELETE /networks/{networkId}/vlans/300" in cmds
        assert (
            'meraki-api: PUT /devices/{serial}/switch/ports/9 '
            'body={"type": "trunk", "allowedVlans": "all", "vlan": 50}'
            in cmds
        )
        assert (
            'meraki-api: PUT /networks/{networkId}/appliance/vlans/100 '
            'body={"applianceIp": "10.100.0.1", "prefix_length": 24}'
            in cmds
        )
        assert "meraki-api: DELETE /networks/{networkId}/appliance/vlans/300" in cmds

    def test_cisco_ios_removals_native_vlan_and_svi(self):
        strategy = CiscoIosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[_trunk_port("GigabitEthernet0/2", vlan_id=1, native_vlan=99)],
            vlan_removals=[100],
            svi_changes=[
                SviChangeOperation(
                    op="create",
                    vlan_id=200,
                    ip_address="10.200.0.1",
                    prefix_length=24,
                    status="apply",
                ),
                SviChangeOperation(
                    op="remove",
                    vlan_id=100,
                    status="apply",
                ),
            ],
        )
        assert "no vlan 100" in cmds
        native_idx = cmds.index(" switchport trunk native vlan 99")
        assert cmds[native_idx + 1] == "exit"
        assert "interface Vlan200" in cmds
        assert " ip address 10.200.0.1 255.255.255.0" in cmds
        assert " no shutdown" in cmds
        assert "no interface Vlan100" in cmds

    def test_cisco_nxos_removals_native_vlan_and_svi(self):
        strategy = CiscoNxosCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[_trunk_port("Ethernet1/2", vlan_id=1, native_vlan=99)],
            vlan_removals=[500],
            svi_changes=[
                SviChangeOperation(
                    op="create",
                    vlan_id=200,
                    ip_address="10.200.0.1",
                    prefix_length=24,
                    status="apply",
                ),
                SviChangeOperation(
                    op="remove",
                    vlan_id=500,
                    status="apply",
                ),
            ],
        )
        assert "no vlan 500" in cmds
        native_idx = cmds.index("  switchport trunk native vlan 99")
        assert cmds[native_idx + 1] == "exit"
        assert "interface Vlan200" in cmds
        assert "  no shutdown" in cmds
        assert "  ip address 10.200.0.1/24" in cmds
        assert "no interface Vlan500" in cmds

    def test_generic_removals_and_svi(self):
        strategy = GenericCliStrategy()
        cmds = strategy.render_vlan_commands(
            vlan_additions={},
            port_changes=[_trunk_port("eth1", vlan_id=1, native_vlan=99)],
            vlan_removals=[99],
            svi_changes=[
                SviChangeOperation(
                    op="create",
                    vlan_id=100,
                    ip_address="10.100.0.1",
                    prefix_length=24,
                    status="apply",
                ),
                SviChangeOperation(
                    op="remove",
                    vlan_id=99,
                    status="apply",
                ),
            ],
        )
        assert "# REMOVE VLAN 99" in cmds
        assert "# SET interface eth1 mode trunk vlan 1 native_vlan 99" in cmds
        assert "# CREATE SVI vlan 100 ip 10.100.0.1/24" in cmds
        assert "# REMOVE SVI vlan 99" in cmds

