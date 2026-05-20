from net_agent_harness.models.changes import (
    DeviceChange,
    VlanChange,
    VlanChangeOperation,
    SviChangeOperation,
    InterfaceChangeOperation,
)
from net_agent_harness.models.enums import NetworkDomain, PlanDecisionType
from net_agent_harness.tools.evaluation import evaluate_intent_state


def test_svi_and_vlan_and_port_planning_on_switch():
    """Test successful VLAN, SVI, and port updates on a switch device."""
    desired_state = {
        "operations": [
            {
                "object_type": "vlan",
                "operation": "ensure_present",
                "attributes": {"vlan_id": 11, "name": "users"},
            },
            {
                "object_type": "svi",
                "operation": "ensure_present",
                "attributes": {
                    "vlan_id": 11,
                    "ip_address": "10.11.0.1",
                    "prefix_length": 24,
                },
            },
            {
                "object_type": "interface",
                "operation": "set_access_vlan",
                "attributes": {"name": "ge-0/0/12", "access_vlan": 11},
            },
        ]
    }

    decision = evaluate_intent_state(
        run_id="test-run-svi",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state=desired_state,
        inventory_source="mock",
    )

    # Since SVI for VLAN 11 is not configured, it should apply!
    assert decision.decision == PlanDecisionType.APPLY
    assert len(decision.diff) == 1
    dc = decision.diff[0]
    assert dc.device == "sw1"

    # Operations list should contain the SviChangeOperation
    ops = dc.changes.operations
    svi_ops = [op for op in ops if isinstance(op, SviChangeOperation)]
    assert len(svi_ops) == 1
    assert svi_ops[0].op == "create"
    assert svi_ops[0].vlan_id == 11
    assert svi_ops[0].ip_address == "10.11.0.1"
    assert svi_ops[0].prefix_length == 24
    assert svi_ops[0].interface == "irb.11"
    assert svi_ops[0].status == "apply"


def test_svi_planning_allowed_on_meraki_firewall():
    """Test SVI operations are allowed on Meraki firewalls (like fw1)."""
    desired_state = {
        "operations": [
            {
                "object_type": "svi",
                "operation": "ensure_present",
                "attributes": {
                    "vlan_id": 11,
                    "ip_address": "10.11.0.1",
                    "prefix_length": 24,
                },
            }
        ]
    }

    decision = evaluate_intent_state(
        run_id="test-run-svi-meraki",
        domain="vlan",
        site="HQ",
        device_names=["fw1"],
        desired_state=desired_state,
        inventory_source="mock",
    )

    # Since SVI for VLAN 11 is not configured, and fw1 is a Meraki firewall, it should apply!
    assert decision.decision == PlanDecisionType.APPLY
    assert len(decision.diff) == 1
    dc = decision.diff[0]
    assert dc.device == "fw1"
    
    ops = dc.changes.operations
    assert len(ops) == 1
    assert isinstance(ops[0], SviChangeOperation)
    assert ops[0].status == "apply"
    assert ops[0].interface == "vlan.11"


def test_svi_planning_blocked_on_palo_alto_firewall(monkeypatch):
    """Test SVI operations are blocked on Palo Alto firewalls."""
    def _fake_lookup_device_context_sync(inventory_source: str, site: str | None, device_name: str | None):
        return {
            "source": "mock",
            "device": {
                "name": "fw-palo",
                "vendor": "palo_alto",
                "role": "firewall",
                "site": site,
                "platform": "panos",
                "vlans": [],
            },
            "interfaces": [],
            "ip_addresses": [],
        }

    monkeypatch.setattr(
        "net_agent_harness.tools.inventory_tools.lookup_device_context_sync",
        _fake_lookup_device_context_sync,
    )

    desired_state = {
        "operations": [
            {
                "object_type": "svi",
                "operation": "ensure_present",
                "attributes": {
                    "vlan_id": 11,
                    "ip_address": "10.11.0.1",
                    "prefix_length": 24,
                },
            }
        ]
    }

    decision = evaluate_intent_state(
        run_id="test-run-svi-blocked",
        domain="vlan",
        site="HQ",
        device_names=["fw-palo"],
        desired_state=desired_state,
        inventory_source="mock",
    )

    assert decision.decision == PlanDecisionType.BLOCKED
    assert "SVI configuration is not supported on firewall devices" in decision.reason
    assert len(decision.diff) == 1
    dc = decision.diff[0]
    assert dc.device == "fw-palo"
    
    ops = dc.changes.operations
    assert len(ops) == 1
    assert isinstance(ops[0], SviChangeOperation)
    assert ops[0].status == "blocked"
    assert "SVI configuration is not supported on firewall devices" in ops[0].reason


def test_svi_planning_multidevice_keeps_diff(monkeypatch):
    """Test that blocked operations propagate to PlanDecision blocked status but diff list remains populated."""
    def _fake_lookup_device_context_sync(inventory_source: str, site: str | None, device_name: str | None):
        if device_name == "sw1":
            from net_agent_harness.adapters.mock_inventory_adapter import get_inventory_for_site
            snapshot = get_inventory_for_site(run_id="mock-run", site=site or "HQ")
            sw1_info = next(d for d in snapshot.devices if d.name == "sw1")
            return {
                "source": "mock",
                "device": sw1_info.model_dump(mode="json"),
                "interfaces": [i.model_dump(mode="json") for i in sw1_info.interfaces],
                "ip_addresses": [],
            }
        return {
            "source": "mock",
            "device": {
                "name": "fw-palo",
                "vendor": "palo_alto",
                "role": "firewall",
                "site": site,
                "platform": "panos",
                "vlans": [],
            },
            "interfaces": [],
            "ip_addresses": [],
        }

    monkeypatch.setattr(
        "net_agent_harness.tools.inventory_tools.lookup_device_context_sync",
        _fake_lookup_device_context_sync,
    )

    desired_state = {
        "operations": [
            {
                "object_type": "svi",
                "operation": "ensure_present",
                "attributes": {
                    "vlan_id": 11,
                    "ip_address": "10.11.0.1",
                    "prefix_length": 24,
                },
            }
        ]
    }

    decision = evaluate_intent_state(
        run_id="test-run-multidevice",
        domain="vlan",
        site="HQ",
        device_names=["sw1", "fw-palo"],
        desired_state=desired_state,
        inventory_source="mock",
    )

    # Overall decision should be blocked due to fw-palo
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "SVI configuration is not supported on firewall devices" in decision.reason

    # Diffs for both devices must be populated
    assert len(decision.diff) == 2
    
    sw1_change = [dc for dc in decision.diff if dc.device == "sw1"][0]
    fw_palo_change = [dc for dc in decision.diff if dc.device == "fw-palo"][0]

    # sw1 should have an apply/create operation
    sw1_ops = sw1_change.changes.operations
    assert len(sw1_ops) == 1
    assert sw1_ops[0].status == "apply"
    assert sw1_ops[0].interface == "irb.11"

    # fw-palo should have a blocked operation
    fw_palo_ops = fw_palo_change.changes.operations
    assert len(fw_palo_ops) == 1
    assert fw_palo_ops[0].status == "blocked"
