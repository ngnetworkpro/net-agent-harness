from net_agent_harness.tools.evaluation import evaluate_intent_state


def test_evaluate_ensure_absent_returns_apply_when_vlan_exists():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_absent",
                    "attributes": {"vlan_id": 11, "name": "users"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "apply"
    assert decision.diff
    assert decision.diff[0].changes.vlans_to_remove
    assert decision.diff[0].changes.vlans_to_remove[0].id == 11


def test_evaluate_blocks_when_netbox_vlan_state_is_unavailable(monkeypatch):
    def _fake_lookup_device_context_sync(inventory_source: str, site: str | None, device_name: str | None):
        return {
            "source": "netbox",
            "device": {
                "name": device_name,
                "vendor": "juniper",
                "role": "access-switch",
                "site": site,
                "platform": "mist",
            },
            "interfaces": [],
            "ip_addresses": [],
        }

    monkeypatch.setattr(
        "net_agent_harness.tools.inventory_tools.lookup_device_context_sync",
        _fake_lookup_device_context_sync,
    )

    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 220, "name": "Engineering"},
                }
            ]
        },
        inventory_source="netbox",
    )
    assert decision.decision.value == "blocked"
    assert "unavailable" in decision.reason.lower()


def test_evaluate_multi_device_both_apply():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1", "fw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 23, "name": "printers3"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "apply"
    assert len(decision.diff) == 2
    assert {d.device for d in decision.diff} == {"sw1", "fw1"}
    assert "sw1" in decision.reason
    assert "fw1" in decision.reason


def test_evaluate_multi_device_one_apply_one_noop(monkeypatch):
    def _fake_lookup_device_context_sync(inventory_source: str, site: str | None, device_name: str | None):
        vlans = [{"id": 1, "name": "default"}]
        if device_name == "sw1":
            vlans.append({"id": 23, "name": "printers3"})
        return {
            "source": "mock",
            "device": {
                "name": device_name,
                "vendor": "juniper" if device_name == "sw1" else "meraki",
                "role": "access-switch" if device_name == "sw1" else "firewall",
                "site": site,
                "platform": "mist" if device_name == "sw1" else "meraki",
                "vlans": vlans,
            },
            "interfaces": [],
            "ip_addresses": [],
        }

    monkeypatch.setattr(
        "net_agent_harness.tools.inventory_tools.lookup_device_context_sync",
        _fake_lookup_device_context_sync,
    )

    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1", "fw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 23, "name": "printers3"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "apply"
    assert len(decision.diff) == 1
    assert decision.diff[0].device == "fw1"
    assert "fw1" in decision.reason
    assert "sw1" not in decision.reason


def test_evaluate_multi_device_one_blocked(monkeypatch):
    def _fake_lookup_device_context_sync(inventory_source: str, site: str | None, device_name: str | None):
        if device_name == "sw1":
            return {"source": "mock", "device": None}
        return {
            "source": "mock",
            "device": {
                "name": device_name,
                "vendor": "meraki",
                "role": "firewall",
                "site": site,
                "platform": "meraki",
                "vlans": [],
            },
            "interfaces": [],
            "ip_addresses": [],
        }

    monkeypatch.setattr(
        "net_agent_harness.tools.inventory_tools.lookup_device_context_sync",
        _fake_lookup_device_context_sync,
    )

    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1", "fw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 23, "name": "printers3"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "blocked"
    assert "sw1" in decision.reason


def test_evaluate_multi_device_target_device_filtering():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1", "fw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 23, "name": "printers3"},
                    "target_devices": ["sw1", "fw1"]
                },
                {
                    "object_type": "svi",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 23, "ip_address": "10.23.0.1", "prefix_length": 24},
                    "target_device": "fw1"
                },
                {
                    "object_type": "interface",
                    "operation": "set_access_vlan",
                    "attributes": {"name": "ge-0/0/13", "access_vlan": 23},
                    "target_device": "sw1"
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "apply"
    
    # We expect 2 device changes
    assert len(decision.diff) == 2
    diff_map = {d.device: d.changes.operations for d in decision.diff}
    
    # sw1 changes should have vlan and interface, no svi
    sw1_ops = diff_map["sw1"]
    assert any(op.change_type == "vlan" for op in sw1_ops)
    assert any(op.change_type == "interface" for op in sw1_ops)
    assert not any(op.change_type == "svi" for op in sw1_ops)
    
    # fw1 changes should have vlan and svi, no interface
    fw1_ops = diff_map["fw1"]
    assert any(op.change_type == "vlan" for op in fw1_ops)
    assert any(op.change_type == "svi" for op in fw1_ops)
    assert not any(op.change_type == "interface" for op in fw1_ops)


