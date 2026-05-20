"""Tests for TopologyUpdatePlan model (Issue #60)."""
import pytest
from pydantic import ValidationError

from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import PlanDecisionType, ResourceLifecycleState
from net_agent_harness.models.topology import (
    TopologyDelta,
    TopologyLink,
    TopologyState,
    TopologyUpdatePlan,
)


def _meta(run_id: str = "run-topo-1") -> ArtifactMeta:
    return ArtifactMeta(run_id=run_id, artifact_id=f"art-{run_id}", created_by="test")


def _scope() -> ScopeRef:
    return ScopeRef(site="HQ")


class TestTopologyLink:
    def test_minimal_link(self):
        link = TopologyLink(endpoint_a_device="sw1", endpoint_b_device="sw2")
        assert link.endpoint_a_device == "sw1"
        assert link.endpoint_b_device == "sw2"
        assert link.endpoint_a_interface is None
        assert link.endpoint_b_interface is None
        assert link.link_type is None

    def test_full_link(self):
        link = TopologyLink(
            endpoint_a_device="sw1",
            endpoint_a_interface="ge-0/0/0",
            endpoint_b_device="core1",
            endpoint_b_interface="ge-0/0/1",
            link_type="uplink",
        )
        assert link.link_type == "uplink"
        assert link.endpoint_a_interface == "ge-0/0/0"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            TopologyLink(
                endpoint_a_device="sw1",
                endpoint_b_device="sw2",
                unexpected="nope",  # type: ignore[call-arg]
            )


class TestTopologyState:
    def test_empty_state(self):
        state = TopologyState()
        assert state.devices == []
        assert state.links == []

    def test_populated_state(self):
        link = TopologyLink(endpoint_a_device="sw1", endpoint_b_device="core1")
        state = TopologyState(devices=["sw1", "core1"], links=[link])
        assert len(state.devices) == 2
        assert len(state.links) == 1


class TestTopologyDelta:
    def test_empty_delta_is_empty(self):
        delta = TopologyDelta()
        assert delta.is_empty is True

    def test_non_empty_delta_is_not_empty(self):
        delta = TopologyDelta(devices_added=["sw3"])
        assert delta.is_empty is False

    def test_links_added(self):
        delta = TopologyDelta(
            links_added=[TopologyLink(endpoint_a_device="sw1", endpoint_b_device="sw2")]
        )
        assert delta.is_empty is False
        assert len(delta.links_added) == 1

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            TopologyDelta(unexpected="nope")  # type: ignore[call-arg]


class TestTopologyUpdatePlan:
    def test_defaults_to_blocked(self):
        plan = TopologyUpdatePlan(
            meta=_meta(),
            scope=_scope(),
            summary="Add uplink between sw1 and core1",
        )
        assert plan.decision == PlanDecisionType.BLOCKED
        assert plan.lifecycle_state == ResourceLifecycleState.PLANNED
        assert plan.blocking_reason is None
        assert plan.missing_device_facts == []

    def test_apply_plan_with_delta(self):
        current = TopologyState(devices=["sw1", "core1"], links=[])
        desired = TopologyState(
            devices=["sw1", "core1"],
            links=[TopologyLink(endpoint_a_device="sw1", endpoint_b_device="core1")],
        )
        delta = TopologyDelta(
            links_added=[TopologyLink(endpoint_a_device="sw1", endpoint_b_device="core1")]
        )
        plan = TopologyUpdatePlan(
            meta=_meta(),
            scope=_scope(),
            summary="Add uplink sw1 → core1",
            current_state=current,
            desired_state=desired,
            delta=delta,
            decision=PlanDecisionType.APPLY,
        )
        assert plan.decision == PlanDecisionType.APPLY
        assert len(plan.delta.links_added) == 1
        assert plan.delta.is_empty is False

    def test_no_op_when_states_match(self):
        current = desired = TopologyState(devices=["sw1"], links=[])
        plan = TopologyUpdatePlan(
            meta=_meta(),
            scope=_scope(),
            summary="No changes needed",
            current_state=current,
            desired_state=desired,
            delta=TopologyDelta(),
            decision=PlanDecisionType.NO_OP,
        )
        assert plan.decision == PlanDecisionType.NO_OP
        assert plan.delta.is_empty is True

    def test_blocked_with_missing_device_facts(self):
        plan = TopologyUpdatePlan(
            meta=_meta(),
            scope=_scope(),
            summary="Cannot plan without facts",
            decision=PlanDecisionType.BLOCKED,
            blocking_reason="Device facts unavailable for sw2",
            missing_device_facts=["sw2"],
        )
        assert plan.blocking_reason is not None
        assert "sw2" in plan.missing_device_facts

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            TopologyUpdatePlan(
                meta=_meta(),
                scope=_scope(),
                summary="test",
                unexpected="nope",  # type: ignore[call-arg]
            )

    def test_lifecycle_state_default_is_planned(self):
        plan = TopologyUpdatePlan(
            meta=_meta(), scope=_scope(), summary="test plan"
        )
        assert plan.lifecycle_state == ResourceLifecycleState.PLANNED
