"""Tests for PrefixAllocationPlan and IPAssignmentPlan models (Issue #61)."""
import pytest
from pydantic import ValidationError

from net_agent_harness.models.common import ArtifactMeta
from net_agent_harness.models.enums import PlanDecisionType, ResourceLifecycleState
from net_agent_harness.models.ipam import IPAssignmentPlan, IpamSnapshot, PrefixAllocationPlan


def _meta(run_id: str = "run-ipam-1") -> ArtifactMeta:
    return ArtifactMeta(run_id=run_id, artifact_id=f"art-{run_id}", created_by="test")


class TestPrefixAllocationPlan:
    def test_defaults_to_blocked(self):
        plan = PrefixAllocationPlan(
            meta=_meta(),
            parent_prefix="10.10.0.0/16",
            requested_prefix_length=24,
        )
        assert plan.decision == PlanDecisionType.BLOCKED
        assert plan.proposed_prefix is None
        assert plan.overlap_check_passed is False
        assert plan.policy_check_passed is False
        assert plan.lifecycle_state == ResourceLifecycleState.PLANNED

    def test_apply_decision_with_proposed_prefix(self):
        plan = PrefixAllocationPlan(
            meta=_meta(),
            parent_prefix="10.10.0.0/16",
            requested_prefix_length=24,
            proposed_prefix="10.10.5.0/24",
            overlap_check_passed=True,
            policy_check_passed=True,
            decision=PlanDecisionType.APPLY,
            site="HQ",
            purpose="servers",
        )
        assert plan.decision == PlanDecisionType.APPLY
        assert plan.proposed_prefix == "10.10.5.0/24"
        assert plan.site == "HQ"
        assert plan.purpose == "servers"

    def test_blocked_with_reason(self):
        plan = PrefixAllocationPlan(
            meta=_meta(),
            parent_prefix="10.10.0.0/16",
            requested_prefix_length=24,
            decision=PlanDecisionType.BLOCKED,
            blocking_reason="Parent prefix is fully allocated",
        )
        assert plan.blocking_reason == "Parent prefix is fully allocated"

    def test_rejects_invalid_prefix_length(self):
        with pytest.raises(ValidationError):
            PrefixAllocationPlan(
                meta=_meta(),
                parent_prefix="10.10.0.0/16",
                requested_prefix_length=0,  # must be >= 1
            )

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            PrefixAllocationPlan(
                meta=_meta(),
                parent_prefix="10.10.0.0/16",
                requested_prefix_length=24,
                unexpected="nope",  # type: ignore[call-arg]
            )

    def test_lifecycle_state_is_planned_by_default(self):
        plan = PrefixAllocationPlan(
            meta=_meta(),
            parent_prefix="10.10.0.0/16",
            requested_prefix_length=24,
        )
        assert plan.lifecycle_state == ResourceLifecycleState.PLANNED

    def test_lifecycle_state_can_be_approved(self):
        plan = PrefixAllocationPlan(
            meta=_meta(),
            parent_prefix="10.10.0.0/16",
            requested_prefix_length=24,
            proposed_prefix="10.10.5.0/24",
            decision=PlanDecisionType.APPLY,
            lifecycle_state=ResourceLifecycleState.APPROVED,
        )
        assert plan.lifecycle_state == ResourceLifecycleState.APPROVED


class TestIPAssignmentPlan:
    def test_defaults_to_blocked(self):
        plan = IPAssignmentPlan(
            meta=_meta(),
            device_name="sw1",
            parent_prefix="10.10.5.0/24",
        )
        assert plan.decision == PlanDecisionType.BLOCKED
        assert plan.proposed_address is None
        assert plan.lifecycle_state == ResourceLifecycleState.PLANNED

    def test_apply_decision_with_address(self):
        plan = IPAssignmentPlan(
            meta=_meta(),
            device_name="sw1",
            interface="ge-0/0/0",
            parent_prefix="10.10.5.0/24",
            proposed_address="10.10.5.10/24",
            decision=PlanDecisionType.APPLY,
        )
        assert plan.decision == PlanDecisionType.APPLY
        assert plan.proposed_address == "10.10.5.10/24"
        assert plan.interface == "ge-0/0/0"

    def test_blocked_with_reason(self):
        plan = IPAssignmentPlan(
            meta=_meta(),
            device_name="sw1",
            parent_prefix="10.10.5.0/24",
            blocking_reason="No available addresses in parent prefix",
        )
        assert plan.blocking_reason == "No available addresses in parent prefix"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            IPAssignmentPlan(
                meta=_meta(),
                device_name="sw1",
                parent_prefix="10.10.5.0/24",
                unexpected="nope",  # type: ignore[call-arg]
            )

    def test_lifecycle_state_can_be_set(self):
        plan = IPAssignmentPlan(
            meta=_meta(),
            device_name="sw1",
            parent_prefix="10.10.5.0/24",
            lifecycle_state=ResourceLifecycleState.APPROVED,
        )
        assert plan.lifecycle_state == ResourceLifecycleState.APPROVED


class TestIpamSnapshotUnchanged:
    """Regression test — IpamSnapshot must still work after ipam.py additions."""

    def test_ipam_snapshot_still_valid(self):
        snap = IpamSnapshot(
            meta=_meta("run-snap"),
            source_of_truth="mock",
        )
        assert snap.prefixes == []
        assert snap.assignments == []
