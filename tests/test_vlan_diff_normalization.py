"""Tests for authoritative VLAN diff normalization.

Covers:
- duplicate VLAN ID collapse
- empty-name VLAN rejection when a valid name exists
- preservation of valid interface updates
- end-to-end evaluation producing a normalized diff
"""

from net_agent_harness.models.changes import (
    DeviceChange,
    InterfaceDesiredStateOperation,
    InterfaceAttributes,
    InterfaceChangeOperation,
    SviChangeOperation,
    VlanChange,
    VlanSpec,
    PortSpec,
)
from net_agent_harness.models.enums import NetworkDomain
from net_agent_harness.tools.evaluation import (
    normalize_vlan_diff,
    _merge_device_changes,
    _op_matches_device,
)


# ── normalize_vlan_diff unit tests ───────────────────────────────────────────


class TestNormalizeVlanDiff:
    def test_duplicate_vlan_id_collapsed(self):
        """Two VlanSpec entries with the same ID produce exactly one."""
        vlans = [
            VlanSpec(id=12, name="users2"),
            VlanSpec(id=12, name="users2"),
        ]
        result = normalize_vlan_diff(vlans)
        assert len(result) == 1
        assert result[0].id == 12
        assert result[0].name == "users2"

    def test_empty_name_replaced_by_valid_name(self):
        """Empty-name entry first, then valid name → keeps valid name."""
        vlans = [
            VlanSpec(id=12, name=""),
            VlanSpec(id=12, name="users2"),
        ]
        result = normalize_vlan_diff(vlans)
        assert len(result) == 1
        assert result[0].id == 12
        assert result[0].name == "users2"

    def test_valid_name_preserved_over_empty(self):
        """Valid name first, then empty-name → keeps valid name."""
        vlans = [
            VlanSpec(id=12, name="users2"),
            VlanSpec(id=12, name=""),
        ]
        result = normalize_vlan_diff(vlans)
        assert len(result) == 1
        assert result[0].id == 12
        assert result[0].name == "users2"

    def test_all_empty_names_keep_one(self):
        """Two entries with empty names for the same ID → exactly one kept."""
        vlans = [
            VlanSpec(id=12, name=""),
            VlanSpec(id=12, name=""),
        ]
        result = normalize_vlan_diff(vlans)
        assert len(result) == 1
        assert result[0].id == 12

    def test_distinct_vlan_ids_preserved(self):
        """Distinct VLAN IDs are all preserved."""
        vlans = [
            VlanSpec(id=10, name="mgmt"),
            VlanSpec(id=12, name="users2"),
        ]
        result = normalize_vlan_diff(vlans)
        assert len(result) == 2
        assert result[0].id == 10
        assert result[0].name == "mgmt"
        assert result[1].id == 12
        assert result[1].name == "users2"

    def test_empty_input(self):
        """Empty list produces empty list."""
        assert normalize_vlan_diff([]) == []

    def test_single_entry_passthrough(self):
        """Single entry is returned as-is."""
        vlans = [VlanSpec(id=100, name="servers")]
        result = normalize_vlan_diff(vlans)
        assert len(result) == 1
        assert result[0].id == 100
        assert result[0].name == "servers"

    def test_ordering_by_vlan_id(self):
        """Output is sorted by VLAN ID regardless of input order."""
        vlans = [
            VlanSpec(id=200, name="guest"),
            VlanSpec(id=10, name="mgmt"),
            VlanSpec(id=50, name="voice"),
        ]
        result = normalize_vlan_diff(vlans)
        assert [v.id for v in result] == [10, 50, 200]


# ── _merge_device_changes integration ───────────────────────────────────────


class TestMergeDeviceChanges:
    def test_merge_deduplicates_vlans(self):
        """Two DeviceChange objects with overlapping VLAN IDs → one per ID."""
        changes = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    vlans_to_create=[VlanSpec(id=12, name="users2")],
                    ports_to_update=[],
                ),
            ),
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    vlans_to_create=[VlanSpec(id=12, name="")],
                    ports_to_update=[
                        PortSpec(interface="ge-0/0/13", vlan_id=12, mode="access"),
                    ],
                ),
            ),
        ]
        merged = _merge_device_changes(changes)
        assert len(merged) == 1
        vlans = merged[0].changes.vlans_to_create
        assert len(vlans) == 1
        assert vlans[0].id == 12
        assert vlans[0].name == "users2"

    def test_merge_preserves_port_updates(self):
        """Port updates from all DeviceChange entries survive merge."""
        changes = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    vlans_to_create=[VlanSpec(id=12, name="users2")],
                    ports_to_update=[],
                ),
            ),
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    vlans_to_create=[],
                    ports_to_update=[
                        PortSpec(interface="ge-0/0/13", vlan_id=12, mode="access"),
                    ],
                ),
            ),
        ]
        merged = _merge_device_changes(changes)
        ports = merged[0].changes.ports_to_update
        assert len(ports) == 1
        assert ports[0].interface == "ge-0/0/13"
        assert ports[0].vlan_id == 12

    def test_single_change_normalized(self):
        """A single DeviceChange with duplicate VLANs is still normalized."""
        changes = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    vlans_to_create=[
                        VlanSpec(id=12, name=""),
                        VlanSpec(id=12, name="users2"),
                    ],
                    ports_to_update=[],
                ),
            ),
        ]
        merged = _merge_device_changes(changes)
        vlans = merged[0].changes.vlans_to_create
        assert len(vlans) == 1
        assert vlans[0].name == "users2"

    def test_merge_prefers_apply_over_skip_for_same_operation(self):
        changes = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        InterfaceChangeOperation(
                            op="set_access_vlan",
                            interface="ge-0/0/13",
                            vlan_id=12,
                            status="skip",
                        )
                    ]
                ),
            ),
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        InterfaceChangeOperation(
                            op="set_access_vlan",
                            interface="ge-0/0/13",
                            vlan_id=12,
                            status="apply",
                        )
                    ]
                ),
            ),
        ]
        merged = _merge_device_changes(changes)
        ops = merged[0].changes.operations
        assert len(ops) == 1
        assert isinstance(ops[0], InterfaceChangeOperation)
        assert ops[0].status == "apply"

    def test_merge_keeps_distinct_svi_targets(self):
        changes = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        SviChangeOperation(
                            op="create",
                            vlan_id=11,
                            ip_address="10.11.0.1",
                            prefix_length=24,
                            interface="irb.11",
                            status="apply",
                        )
                    ]
                ),
            ),
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        SviChangeOperation(
                            op="create",
                            vlan_id=11,
                            ip_address="10.11.0.2",
                            prefix_length=24,
                            interface="irb.11",
                            status="apply",
                        )
                    ]
                ),
            ),
        ]
        merged = _merge_device_changes(changes)
        svi_ops = [op for op in merged[0].changes.operations if isinstance(op, SviChangeOperation)]
        assert len(svi_ops) == 2


class TestDeviceOpMatch:
    def test_matches_pydantic_operation_targeting(self):
        op = InterfaceDesiredStateOperation(
            object_type="interface",
            operation="set_access_vlan",
            attributes=InterfaceAttributes(name="ge-0/0/1", access_vlan=12),
            target_devices=["sw1"],
        )
        assert _op_matches_device(op, "sw1")
        assert not _op_matches_device(op, "sw2")


# ── End-to-end evaluation integration ───────────────────────────────────────


class TestEvaluateProvisionAccessPort:
    """Integration test simulating the exact scenario from the issue:
    provision_access_port for VLAN 12 named 'users2' on sw1, interface ge-0/0/13.
    """

    def test_normalized_diff_single_vlan_create(self):
        """ensure_present + set_access_vlan for same VLAN ID → exactly one
        VLAN create entry with the correct name, plus one interface update."""
        from net_agent_harness.tools.evaluation import evaluate_intent_state

        desired_state = {
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 12, "name": "users2"},
                },
                {
                    "object_type": "interface",
                    "operation": "set_access_vlan",
                    "attributes": {"name": "ge-0/0/13", "access_vlan": 12},
                },
            ]
        }

        decision = evaluate_intent_state(
            run_id="test-run",
            domain="vlan",
            site="HQ",
            device_names=["sw1"],
            desired_state=desired_state,
            inventory_source="mock",
        )

        assert decision.decision.value == "apply"

        # Exactly one DeviceChange
        assert len(decision.diff) == 1
        dc = decision.diff[0]

        # Exactly one VLAN create entry
        vlans = dc.changes.vlans_to_create
        assert len(vlans) == 1
        assert vlans[0].id == 12
        assert vlans[0].name == "users2"

        # No empty-name VLAN entries
        assert all(v.name != "" for v in vlans if v.id == 12)

        # Interface update preserved
        ports = dc.changes.ports_to_update
        assert any(
            p.interface == "ge-0/0/13" and p.vlan_id == 12
            for p in ports
        )
