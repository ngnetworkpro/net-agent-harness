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


def test_evaluate_set_native_vlan_apply_when_differs():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "set_native_vlan",
                    "attributes": {"name": "mge-0/0/1", "native_vlan": 99},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "apply"
    assert len(decision.diff) == 1
    ports = decision.diff[0].changes.ports_to_update
    assert len(ports) == 1
    assert ports[0].interface == "mge-0/0/1"
    assert ports[0].native_vlan == 99


def test_evaluate_set_native_vlan_noop_when_matches():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "set_native_vlan",
                    "attributes": {"name": "mge-0/0/1", "native_vlan": 1},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "no_op"


def test_evaluate_update_trunk_allowed_vlans_noop_when_mode_all():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "update_trunk_allowed_vlans",
                    "attributes": {"name": "mge-0/0/1", "allowed_vlans": [11, 21]},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "no_op"


def test_evaluate_update_trunk_allowed_vlans_apply_when_list_missing_vlan(monkeypatch):
    def _fake_lookup_device_context_sync(
        inventory_source: str, site: str | None, device_name: str | None
    ):
        return {
            "source": "mock",
            "device": {
                "name": device_name,
                "vendor": "juniper",
                "role": "access-switch",
                "site": site,
                "platform": "mist",
                "vlans": [{"id": 1, "name": "default"}, {"id": 11, "name": "users"}],
                "interfaces": [
                    {
                        "name": "mge-0/0/1",
                        "mode": "trunk",
                        "native_vlan": 1,
                        "allowed_vlans_mode": "list",
                        "vlan_ids": [1, 11],
                    }
                ],
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
                    "object_type": "interface",
                    "operation": "update_trunk_allowed_vlans",
                    "attributes": {"name": "mge-0/0/1", "allowed_vlans": [11, 21]},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "apply"
    ports = decision.diff[0].changes.ports_to_update
    assert len(ports) == 1
    assert ports[0].interface == "mge-0/0/1"
    assert ports[0].allowed_vlans == [11, 21]


def test_evaluate_blocks_when_set_native_vlan_missing_native_vlan():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "set_native_vlan",
                    "attributes": {"name": "mge-0/0/1"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "blocked"
    assert "native_vlan" in decision.reason


def test_evaluate_blocks_when_update_trunk_allowed_vlans_missing_vlans():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "update_trunk_allowed_vlans",
                    "attributes": {"name": "mge-0/0/1"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "blocked"
    assert "allowed_vlans" in decision.reason


def test_evaluate_blocks_when_interface_not_found_on_device():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "set_access_vlan",
                    "attributes": {"name": "ge-0/0/99", "access_vlan": 11},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "blocked"
    assert "ge-0/0/99" in decision.reason


def test_evaluate_blocks_when_vlan_id_out_of_range():
    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "set_native_vlan",
                    "attributes": {"name": "mge-0/0/1", "native_vlan": 5000},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "blocked"
    assert "5000" in decision.reason


def test_evaluate_set_trunk_no_vlan_args_on_list_trunk_returns_noop(monkeypatch):
    def _fake_lookup_device_context_sync(
        inventory_source: str, site: str | None, device_name: str | None
    ):
        return {
            "source": "mock",
            "device": {
                "name": device_name,
                "vendor": "juniper",
                "role": "access-switch",
                "site": site,
                "platform": "mist",
                "vlans": [{"id": 11, "name": "users"}],
                "interfaces": [
                    {
                        "name": "mge-0/0/1",
                        "mode": "trunk",
                        "native_vlan": 1,
                        "allowed_vlans_mode": "list",
                        "vlan_ids": [11, 21],
                    }
                ],
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
                    "object_type": "interface",
                    "operation": "set_trunk",
                    "attributes": {"name": "mge-0/0/1"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "no_op"


def test_rollback_builder_preserves_native_and_allowed_vlans():
    from net_agent_harness.orchestration.rollback_builder import build_rollback_plan

    decision = evaluate_intent_state(
        run_id="run-1",
        domain="vlan",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "interface",
                    "operation": "set_trunk",
                    "attributes": {
                        "name": "mge-0/0/1",
                        "native_vlan": 99,
                        "allowed_vlans": [11, 21],
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision.value == "apply"
    rollback = build_rollback_plan(decision)
    assert len(rollback.structured_rollback_steps) == 1
    step = rollback.structured_rollback_steps[0]
    assert step.operation == "reset_trunk"
    assert step.attributes["native_vlan"] == 99
    assert step.attributes["allowed_vlans"] == [11, 21]


def test_evaluate_mist_unnamed_vlan_defaults_name_to_vlan_id():
    for attrs in ({"vlan_id": 123, "name": ""}, {"vlan_id": 123}):
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
                        "attributes": attrs,
                    }
                ]
            },
            inventory_source="mock",
        )
        assert decision.decision.value == "apply"
        assert len(decision.diff) == 1
        assert decision.diff[0].changes.vlans_to_create[0].id == 123
        assert decision.diff[0].changes.vlans_to_create[0].name == "123"
        op = decision.diff[0].changes.operations[0]
        assert op.status == "apply"
        assert op.name == "123"


