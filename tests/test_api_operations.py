import json

import pytest

from net_agent_harness.adapters.backends.api_operations import (
    MerakiApiStrategy,
    MistApiStrategy,
    build_api_primary_snippet,
)
from net_agent_harness.models.artifacts import ApiRequestPayload
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


def test_mist_api_strategy_vlan_creation():
    strategy = MistApiStrategy()
    ops = strategy.build_vlan_operations(
        vlan_additions={"users": "10"},
        port_changes=[PortSpec(interface="ge-0/0/1", vlan_id=10, mode="access")]
    )
    
    assert len(ops) == 2
    assert ops[0]["action"] == "create_vlan"
    assert ops[0]["payload"]["vlan_id"] == 10
    assert ops[0]["payload"]["name"] == "users"
    
    assert ops[1]["action"] == "update_port"
    assert ops[1]["port"] == "ge-0/0/1"
    assert ops[1]["payload"]["mode"] == "access"
    assert ops[1]["payload"]["vlan_id"] == 10

def test_meraki_api_strategy_vlan_creation():
    strategy = MerakiApiStrategy()
    ops = strategy.build_vlan_operations(
        vlan_additions={"servers": "20"},
        port_changes=[PortSpec(interface="2", vlan_id=20, mode="trunk")]
    )
    
    assert len(ops) == 2
    assert ops[0]["action"] == "create_vlan"
    assert ops[0]["payload"]["id"] == 20
    assert ops[0]["payload"]["name"] == "servers"
    
    assert ops[1]["action"] == "update_port"
    assert ops[1]["endpoint"] == "/devices/{serial}/switch/ports/2"
    assert ops[1]["payload"]["type"] == "trunk"
    assert ops[1]["payload"]["allowedVlans"] == "all"

def test_build_api_primary_snippet_returns_correct_backendtype():
    snippet = build_api_primary_snippet(
        device_name="sw1",
        vendor=DeviceVendor.JUNIPER,
        platform="mist",
        vlan_additions={"guests": "30"},
        port_changes=[]
    )
    
    assert snippet.device_name == "sw1"
    assert snippet.backend_type == RenderBackendType.API
    assert snippet.render_role == RenderRole.PRIMARY
    assert snippet.api_payload is not None
    assert isinstance(snippet.api_payload, ApiRequestPayload)
    assert snippet.api_payload.method == "POST"
    assert snippet.api_payload.path == "/operations/batch"
    assert snippet.api_payload.body is not None
    assert len(snippet.api_payload.body["operations"]) == 1
    
    # rendered_text should be human-readable JSON
    rendered_json = json.loads(snippet.rendered_text)
    assert rendered_json == snippet.api_payload.model_dump()

def test_build_api_primary_snippet_has_empty_commands():
    snippet = build_api_primary_snippet(
        device_name="sw2",
        vendor=DeviceVendor.MERAKI,
        vlan_additions={"test": "40"},
        port_changes=[]
    )
    
    assert snippet.commands == []

def test_unsupported_vendor_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="API rendering not yet supported"):
        build_api_primary_snippet(
            device_name="sw3",
            vendor=DeviceVendor.ARISTA,
            vlan_additions={"unsupported": "50"},
            port_changes=[]
        )


def test_mist_api_strategy_vlan_removals_native_vlan_and_svi():
    strategy = MistApiStrategy()
    ops = strategy.build_vlan_operations(
        vlan_additions={},
        port_changes=[_trunk_port("ge-0/0/10", vlan_id=1, native_vlan=99)],
        vlan_removals=[200],
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
                vlan_id=200,
                interface="irb.200",
                status="apply",
            ),
            SviChangeOperation(
                op="create",
                vlan_id=300,
                ip_address="10.300.0.1",
                prefix_length=24,
                status="skip",
            ),
        ],
    )

    assert len(ops) == 4
    assert ops[0] == {
        "action": "delete_vlan",
        "endpoint": "/sites/{site_id}/vlans/200",
        "payload": {"vlan_id": 200},
    }
    assert ops[1] == {
        "action": "update_port",
        "port": "ge-0/0/10",
        "payload": {"mode": "trunk", "allowed_vlans": "all", "native_vlan": 99},
    }
    assert ops[2] == {
        "action": "create_svi",
        "endpoint": "/sites/{site_id}/Setting",
        "interface": "irb.100",
        "payload": {"vlan_id": 100, "ip_address": "10.100.0.1", "prefix_length": 24},
    }
    assert ops[3] == {
        "action": "delete_svi",
        "endpoint": "/sites/{site_id}/Setting",
        "interface": "irb.200",
        "payload": {"vlan_id": 200},
    }


def test_meraki_api_strategy_vlan_removals_native_vlan_and_svi():
    strategy = MerakiApiStrategy()
    ops = strategy.build_vlan_operations(
        vlan_additions={},
        port_changes=[_trunk_port("5", vlan_id=1, native_vlan=50)],
        vlan_removals=[300],
        svi_changes=[
            SviChangeOperation(
                op="create",
                vlan_id=100,
                ip_address="192.168.100.1",
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

    assert len(ops) == 4
    assert ops[0] == {
        "action": "delete_vlan",
        "endpoint": "/networks/{networkId}/vlans/300",
        "payload": {"id": 300},
    }
    assert ops[1] == {
        "action": "update_port",
        "endpoint": "/devices/{serial}/switch/ports/5",
        "payload": {"type": "trunk", "allowedVlans": "all", "vlan": 50},
    }
    assert ops[2] == {
        "action": "update_vlan_svi",
        "endpoint": "/networks/{networkId}/appliance/vlans/100",
        "payload": {"id": 100, "applianceIp": "192.168.100.1", "prefix_length": 24},
    }
    assert ops[3] == {
        "action": "delete_vlan_svi",
        "endpoint": "/networks/{networkId}/appliance/vlans/300",
        "payload": {"id": 300},
    }


def test_build_api_primary_snippet_forwards_removals_and_svi():
    snippet = build_api_primary_snippet(
        device_name="sw1",
        vendor=DeviceVendor.JUNIPER,
        platform="mist",
        vlan_additions={},
        port_changes=[],
        vlan_removals=[400],
        svi_changes=[
            SviChangeOperation(
                op="remove",
                vlan_id=400,
                status="apply",
            )
        ],
    )
    assert snippet.api_payload is not None
    assert snippet.api_payload.body is not None
    ops = snippet.api_payload.body["operations"]
    assert len(ops) == 2
    assert ops[0]["action"] == "delete_vlan"
    assert ops[1]["action"] == "delete_svi"

