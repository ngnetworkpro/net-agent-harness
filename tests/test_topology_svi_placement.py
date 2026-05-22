"""Regression test: topology-driven SVI placement.

Locks in the rule that when the topology designates fw1 as the Layer 3
gateway, the SVI is created on fw1, not sw1.  The VLAN is created on both
devices and the access-port assignment stays on sw1.

Uses the real VLAN 23 / HQ / sw1 + fw1 topology from the mock inventory.
Verifies that placement is deterministic and based on the ``target_device``
field in the desired-state operations — not prompt wording.
"""

from net_agent_harness.models.changes import (
    InterfaceChangeOperation,
    SviChangeOperation,
    VlanChangeOperation,
)
from net_agent_harness.models.enums import PlanDecisionType
from net_agent_harness.orchestration.rollback_builder import build_rollback_plan
from net_agent_harness.tools.evaluation import evaluate_intent_state


# ── The canonical desired_state from the VLAN-23 / HQ topology ──────────────
# This mirrors the exact operations from run-c570bcdd/change_request.json:
#   - VLAN 23 on both sw1 and fw1
#   - SVI on fw1 only (the topology-designated gateway)
#   - Access port ge-0/0/13 on sw1 only
_DESIRED_STATE = {
    "operations": [
        {
            "object_type": "vlan",
            "operation": "ensure_present",
            "attributes": {"vlan_id": 23, "name": "printers3"},
            "target_devices": ["sw1", "fw1"],
        },
        {
            "object_type": "svi",
            "operation": "ensure_present",
            "attributes": {
                "vlan_id": 23,
                "ip_address": "10.23.0.1",
                "prefix_length": 24,
            },
            "target_device": "fw1",
        },
        {
            "object_type": "interface",
            "operation": "set_access_vlan",
            "attributes": {"name": "ge-0/0/13", "access_vlan": 23},
            "target_device": "sw1",
        },
    ],
}


class TestTopologyDrivenSviPlacement:
    """Regression suite for SVI placement on the topology gateway."""

    def _evaluate(self):
        """Shared helper — run the canonical VLAN-23 scenario."""
        return evaluate_intent_state(
            run_id="test-run-topo-svi",
            domain="vlan",
            site="HQ",
            device_names=["sw1", "fw1"],
            desired_state=_DESIRED_STATE,
            inventory_source="mock",
        )

    # ── Core placement assertions ────────────────────────────────────────

    def test_decision_is_apply(self) -> None:
        decision = self._evaluate()
        assert decision.decision == PlanDecisionType.APPLY

    def test_svi_placed_on_fw1_not_sw1(self) -> None:
        """The SVI must appear on fw1 (the gateway), never on sw1."""
        decision = self._evaluate()
        diff_map = {dc.device: dc.changes.operations for dc in decision.diff}

        # fw1 must have an SVI operation
        fw1_svi_ops = [
            op for op in diff_map["fw1"] if isinstance(op, SviChangeOperation)
        ]
        assert len(fw1_svi_ops) == 1, "Expected exactly one SVI operation on fw1"
        assert fw1_svi_ops[0].status == "apply"
        assert fw1_svi_ops[0].vlan_id == 23
        assert fw1_svi_ops[0].ip_address == "10.23.0.1"
        assert fw1_svi_ops[0].prefix_length == 24
        # Meraki gateway → interface name "vlan.23"
        assert fw1_svi_ops[0].interface == "vlan.23"

        # sw1 must NOT have any SVI operation
        sw1_svi_ops = [
            op for op in diff_map["sw1"] if isinstance(op, SviChangeOperation)
        ]
        assert len(sw1_svi_ops) == 0, "SVI must not be placed on sw1"

    def test_vlan_created_on_both_devices(self) -> None:
        """VLAN 23 must be created on both sw1 and fw1."""
        decision = self._evaluate()
        diff_map = {dc.device: dc.changes.operations for dc in decision.diff}

        for device_name in ("sw1", "fw1"):
            vlan_ops = [
                op
                for op in diff_map[device_name]
                if isinstance(op, VlanChangeOperation) and op.op == "create"
            ]
            assert len(vlan_ops) == 1, (
                f"Expected exactly one VLAN create operation on {device_name}"
            )
            assert vlan_ops[0].vlan_id == 23
            assert vlan_ops[0].status == "apply"
            assert vlan_ops[0].reason is not None

    def test_access_port_assigned_on_sw1_only(self) -> None:
        """Access-port ge-0/0/13 must be assigned on sw1, not fw1."""
        decision = self._evaluate()
        diff_map = {dc.device: dc.changes.operations for dc in decision.diff}

        # sw1 must have the interface operation
        sw1_iface_ops = [
            op
            for op in diff_map["sw1"]
            if isinstance(op, InterfaceChangeOperation)
        ]
        assert len(sw1_iface_ops) == 1
        assert sw1_iface_ops[0].interface == "ge-0/0/13"
        assert sw1_iface_ops[0].vlan_id == 23
        assert sw1_iface_ops[0].status == "apply"

        # fw1 must NOT have any interface operation
        fw1_iface_ops = [
            op
            for op in diff_map["fw1"]
            if isinstance(op, InterfaceChangeOperation)
        ]
        assert len(fw1_iface_ops) == 0, (
            "Interface assignment must not appear on fw1"
        )

    # ── Rollback alignment ───────────────────────────────────────────────

    def test_rollback_aligns_with_forward_plan(self) -> None:
        """Structured rollback must mirror the forward plan in reverse."""
        decision = self._evaluate()
        rollback = build_rollback_plan(decision)

        steps = rollback.structured_rollback_steps
        assert len(steps) == 4, (
            "Expected 4 rollback steps: 1 interface + 1 SVI + 2 VLANs"
        )

        # Reverse dependency ordering: interface → SVI → VLAN
        assert steps[0].object_type == "interface"
        assert steps[0].target_device == "sw1"
        assert steps[0].operation == "reset_access_vlan"

        assert steps[1].object_type == "svi"
        assert steps[1].target_device == "fw1"
        assert steps[1].operation == "remove"
        assert steps[1].attributes.get("vlan_id") == 23

        assert steps[2].object_type == "vlan"
        assert steps[2].operation == "remove"

        assert steps[3].object_type == "vlan"
        assert steps[3].operation == "remove"

        # Both devices represented in VLAN rollback
        vlan_rollback_devices = {
            s.target_device for s in steps if s.object_type == "vlan"
        }
        assert vlan_rollback_devices == {"sw1", "fw1"}

        # Text rollback must also be populated and aligned
        assert len(rollback.rollback_steps) == 4
        for step, text in zip(steps, rollback.rollback_steps):
            assert step.description == text

    # ── Determinism ──────────────────────────────────────────────────────

    def test_placement_is_deterministic(self) -> None:
        """Running the same evaluation twice produces identical results."""
        d1 = self._evaluate()
        d2 = self._evaluate()

        assert d1.decision == d2.decision
        assert len(d1.diff) == len(d2.diff)

        for dc1, dc2 in zip(d1.diff, d2.diff):
            assert dc1.device == dc2.device
            assert len(dc1.changes.operations) == len(dc2.changes.operations)
            for op1, op2 in zip(dc1.changes.operations, dc2.changes.operations):
                assert op1.change_type == op2.change_type
                assert op1.op == op2.op
                assert op1.status == op2.status

    def test_svi_reason_mentions_fw1(self) -> None:
        """The SVI reason must mention fw1, confirming placement awareness."""
        decision = self._evaluate()
        fw1_change = next(dc for dc in decision.diff if dc.device == "fw1")
        svi_op = next(
            op
            for op in fw1_change.changes.operations
            if isinstance(op, SviChangeOperation)
        )
        assert svi_op.reason is not None
        assert "fw1" in svi_op.reason
