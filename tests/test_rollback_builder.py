"""Tests for deterministic rollback step generation from forward diffs.

Covers:
- VLAN create → rollback has vlan remove step
- SVI create → rollback has svi remove step
- Interface set_access_vlan → rollback has reset_access_vlan step
- Multi-operation diff → reverse dependency order
- Only apply operations produce rollback steps
- Empty diff → empty rollback
- Multi-device diff → steps for all devices
- Both structured and text rollback steps populated
"""

from net_agent_harness.models.changes import (
    DeviceChange,
    InterfaceChangeOperation,
    PlanDecision,
    RollbackStep,
    SviChangeOperation,
    VlanChange,
    VlanChangeOperation,
)
from net_agent_harness.models.enums import NetworkDomain, PlanDecisionType
from net_agent_harness.orchestration.rollback_builder import build_rollback_plan


def _make_decision(diff: list[DeviceChange]) -> PlanDecision:
    return PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="test",
        diff=diff,
    )


class TestVlanRollback:
    def test_create_produces_remove(self) -> None:
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        VlanChangeOperation(
                            op="create",
                            vlan_id=23,
                            name="printers3",
                            status="apply",
                            reason="VLAN 23 does not exist.",
                        )
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.structured_rollback_steps) == 1
        step = plan.structured_rollback_steps[0]
        assert step.object_type == "vlan"
        assert step.operation == "remove"
        assert step.target_device == "sw1"
        assert step.attributes["vlan_id"] == 23
        assert "Remove VLAN 23" in step.description

    def test_remove_produces_create(self) -> None:
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        VlanChangeOperation(
                            op="remove",
                            vlan_id=11,
                            name="users",
                            status="apply",
                            reason="VLAN 11 must be removed.",
                        )
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.structured_rollback_steps) == 1
        assert plan.structured_rollback_steps[0].operation == "create"
        assert "Re-create VLAN 11" in plan.structured_rollback_steps[0].description


class TestSviRollback:
    def test_create_produces_remove(self) -> None:
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        SviChangeOperation(
                            op="create",
                            vlan_id=23,
                            ip_address="10.23.0.1",
                            prefix_length=24,
                            interface="irb.23",
                            status="apply",
                            reason="SVI must be created.",
                        )
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.structured_rollback_steps) == 1
        step = plan.structured_rollback_steps[0]
        assert step.object_type == "svi"
        assert step.operation == "remove"
        assert step.attributes["interface"] == "irb.23"
        assert "Remove SVI" in step.description


class TestInterfaceRollback:
    def test_set_access_vlan_produces_reset(self) -> None:
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        InterfaceChangeOperation(
                            op="set_access_vlan",
                            interface="ge-0/0/13",
                            vlan_id=23,
                            status="apply",
                            reason="Interface needs update.",
                        )
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.structured_rollback_steps) == 1
        step = plan.structured_rollback_steps[0]
        assert step.object_type == "interface"
        assert step.operation == "reset_access_vlan"
        assert step.attributes["interface"] == "ge-0/0/13"


class TestRollbackOrdering:
    def test_reverse_dependency_order(self) -> None:
        """Multi-operation diff → interface first, then SVI, then VLAN."""
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        VlanChangeOperation(
                            op="create", vlan_id=23, name="printers3",
                            status="apply", reason="test",
                        ),
                        InterfaceChangeOperation(
                            op="set_access_vlan", interface="ge-0/0/13",
                            vlan_id=23, status="apply", reason="test",
                        ),
                        SviChangeOperation(
                            op="create", vlan_id=23, ip_address="10.23.0.1",
                            prefix_length=24, interface="irb.23",
                            status="apply", reason="test",
                        ),
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        steps = plan.structured_rollback_steps
        assert len(steps) == 3
        # Order: interface (1) → SVI (2) → VLAN (3)
        assert steps[0].object_type == "interface"
        assert steps[1].object_type == "svi"
        assert steps[2].object_type == "vlan"
        assert steps[0].order == 1
        assert steps[1].order == 2
        assert steps[2].order == 3


class TestSkipAndBlockedExclusion:
    def test_skip_operations_excluded(self) -> None:
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        VlanChangeOperation(
                            op="create", vlan_id=23, name="printers3",
                            status="apply", reason="Needed",
                        ),
                        VlanChangeOperation(
                            op="create", vlan_id=11, name="users",
                            status="skip", reason="Already exists",
                        ),
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.structured_rollback_steps) == 1
        assert plan.structured_rollback_steps[0].attributes["vlan_id"] == 23

    def test_blocked_operations_excluded(self) -> None:
        diff = [
            DeviceChange(
                device="fw-palo",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        SviChangeOperation(
                            op="create", vlan_id=11, status="blocked",
                            reason="SVI not supported",
                        ),
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.structured_rollback_steps) == 0


class TestEmptyDiff:
    def test_empty_diff_produces_empty_rollback(self) -> None:
        plan = build_rollback_plan(_make_decision([]))
        assert len(plan.structured_rollback_steps) == 0
        assert "No operations" in plan.summary


class TestMultiDevice:
    def test_multi_device_rollback(self) -> None:
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        VlanChangeOperation(
                            op="create", vlan_id=23, name="printers3",
                            status="apply", reason="test",
                        ),
                    ]
                ),
            ),
            DeviceChange(
                device="fw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        VlanChangeOperation(
                            op="create", vlan_id=23, name="printers3",
                            status="apply", reason="test",
                        ),
                    ]
                ),
            ),
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.structured_rollback_steps) == 2
        devices = {s.target_device for s in plan.structured_rollback_steps}
        assert devices == {"sw1", "fw1"}


class TestTextStepsPopulated:
    def test_both_text_and_structured_populated(self) -> None:
        diff = [
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    operations=[
                        VlanChangeOperation(
                            op="create", vlan_id=23, name="printers3",
                            status="apply", reason="test",
                        ),
                    ]
                ),
            )
        ]
        plan = build_rollback_plan(_make_decision(diff))
        assert len(plan.rollback_steps) == 1
        assert len(plan.structured_rollback_steps) == 1
        assert plan.rollback_steps[0] == plan.structured_rollback_steps[0].description
