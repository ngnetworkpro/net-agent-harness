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
