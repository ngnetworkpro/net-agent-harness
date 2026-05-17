import pytest
import json

from net_agent_harness.adapters.backends.api_operations import (
    MistApiStrategy,
    MerakiApiStrategy,
    build_api_primary_snippet,
)
from net_agent_harness.models.artifacts import ApiRequestPayload
from net_agent_harness.models.changes import PortSpec
from net_agent_harness.models.enums import DeviceVendor, RenderBackendType, RenderRole

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
