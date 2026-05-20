"""Tests for ChangeRequestDependency and dependency resolver (Issue #62)."""
import pytest
from pydantic import ValidationError

from net_agent_harness.models.changes import ChangeRequestDependency
from net_agent_harness.models.enums import ResourceLifecycleState
from net_agent_harness.orchestration.dependency_resolver import (
    _is_state_satisfied,
    _lifecycle_rank,
    resolve_dependencies,
)


class TestLifecycleRank:
    def test_current_is_lowest(self):
        assert _lifecycle_rank(ResourceLifecycleState.CURRENT) < _lifecycle_rank(
            ResourceLifecycleState.PLANNED
        )

    def test_verified_is_highest(self):
        assert _lifecycle_rank(ResourceLifecycleState.VERIFIED) > _lifecycle_rank(
            ResourceLifecycleState.APPLIED
        )

    def test_full_ordering(self):
        states = [
            ResourceLifecycleState.CURRENT,
            ResourceLifecycleState.INTENDED,
            ResourceLifecycleState.PLANNED,
            ResourceLifecycleState.APPROVED,
            ResourceLifecycleState.APPLIED,
            ResourceLifecycleState.VERIFIED,
        ]
        ranks = [_lifecycle_rank(s) for s in states]
        assert ranks == sorted(ranks), "Lifecycle states must be monotonically increasing"


class TestIsStateSatisfied:
    def test_exact_match_is_satisfied(self):
        assert _is_state_satisfied(
            ResourceLifecycleState.APPROVED, ResourceLifecycleState.APPROVED
        ) is True

    def test_higher_state_satisfies_lower_requirement(self):
        assert _is_state_satisfied(
            ResourceLifecycleState.APPLIED, ResourceLifecycleState.APPROVED
        ) is True

    def test_lower_state_does_not_satisfy_higher_requirement(self):
        assert _is_state_satisfied(
            ResourceLifecycleState.PLANNED, ResourceLifecycleState.APPROVED
        ) is False

    def test_planned_satisfies_planned(self):
        assert _is_state_satisfied(
            ResourceLifecycleState.PLANNED, ResourceLifecycleState.PLANNED
        ) is True


class TestChangeRequestDependency:
    def test_minimal_creation(self):
        dep = ChangeRequestDependency(
            dependency_type="ipam_allocation",
            description="Reserve /24 from 10.10.0.0/16",
        )
        assert dep.dependency_type == "ipam_allocation"
        assert dep.blocking is True
        assert dep.artifact_id is None
        assert dep.run_id is None
        assert dep.required_lifecycle_state is None
        assert dep.current_lifecycle_state is None

    def test_full_creation(self):
        dep = ChangeRequestDependency(
            dependency_type="topology_plan",
            description="Topology plan for sw1 → core1 uplink",
            artifact_id="art-topo-1",
            run_id="run-topo-abc",
            required_lifecycle_state=ResourceLifecycleState.APPROVED,
            current_lifecycle_state=ResourceLifecycleState.PLANNED,
            blocking=True,
        )
        assert dep.required_lifecycle_state == ResourceLifecycleState.APPROVED
        assert dep.current_lifecycle_state == ResourceLifecycleState.PLANNED

    def test_non_blocking_dependency(self):
        dep = ChangeRequestDependency(
            dependency_type="policy_check",
            description="Advisory policy check",
            blocking=False,
        )
        assert dep.blocking is False

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ChangeRequestDependency(
                dependency_type="ipam_allocation",
                description="test",
                unexpected="nope",  # type: ignore[call-arg]
            )


class TestResolveDependencies:
    def test_empty_dependencies_is_resolved(self):
        all_resolved, reasons = resolve_dependencies([])
        assert all_resolved is True
        assert reasons == []

    def test_dependency_with_no_state_is_blocking(self):
        dep = ChangeRequestDependency(
            dependency_type="ipam_allocation",
            description="IPAM allocation",
            blocking=True,
            current_lifecycle_state=None,
        )
        all_resolved, reasons = resolve_dependencies([dep])
        assert all_resolved is False
        assert len(reasons) == 1
        assert "no recorded lifecycle state" in reasons[0]

    def test_dependency_satisfied_at_exact_state(self):
        dep = ChangeRequestDependency(
            dependency_type="ipam_allocation",
            description="IPAM allocation",
            blocking=True,
            required_lifecycle_state=ResourceLifecycleState.APPROVED,
            current_lifecycle_state=ResourceLifecycleState.APPROVED,
        )
        all_resolved, reasons = resolve_dependencies([dep])
        assert all_resolved is True
        assert reasons == []

    def test_dependency_satisfied_at_higher_state(self):
        dep = ChangeRequestDependency(
            dependency_type="ipam_allocation",
            description="IPAM allocation",
            blocking=True,
            required_lifecycle_state=ResourceLifecycleState.APPROVED,
            current_lifecycle_state=ResourceLifecycleState.APPLIED,
        )
        all_resolved, reasons = resolve_dependencies([dep])
        assert all_resolved is True

    def test_dependency_not_satisfied_at_lower_state(self):
        dep = ChangeRequestDependency(
            dependency_type="topology_plan",
            description="Topology plan must be approved",
            blocking=True,
            required_lifecycle_state=ResourceLifecycleState.APPROVED,
            current_lifecycle_state=ResourceLifecycleState.PLANNED,
        )
        all_resolved, reasons = resolve_dependencies([dep])
        assert all_resolved is False
        assert len(reasons) == 1
        assert "planned" in reasons[0]
        assert "approved" in reasons[0]

    def test_non_blocking_dependency_is_ignored(self):
        dep = ChangeRequestDependency(
            dependency_type="policy_check",
            description="Advisory check",
            blocking=False,
            current_lifecycle_state=None,  # Would block if blocking=True
        )
        all_resolved, reasons = resolve_dependencies([dep])
        assert all_resolved is True
        assert reasons == []

    def test_multiple_dependencies_all_resolved(self):
        deps = [
            ChangeRequestDependency(
                dependency_type="ipam_allocation",
                description="IPAM",
                blocking=True,
                required_lifecycle_state=ResourceLifecycleState.APPROVED,
                current_lifecycle_state=ResourceLifecycleState.APPROVED,
            ),
            ChangeRequestDependency(
                dependency_type="topology_plan",
                description="Topology",
                blocking=True,
                required_lifecycle_state=ResourceLifecycleState.PLANNED,
                current_lifecycle_state=ResourceLifecycleState.PLANNED,
            ),
        ]
        all_resolved, reasons = resolve_dependencies(deps)
        assert all_resolved is True

    def test_multiple_dependencies_one_blocking(self):
        deps = [
            ChangeRequestDependency(
                dependency_type="ipam_allocation",
                description="IPAM",
                blocking=True,
                required_lifecycle_state=ResourceLifecycleState.APPROVED,
                current_lifecycle_state=ResourceLifecycleState.APPROVED,
            ),
            ChangeRequestDependency(
                dependency_type="topology_plan",
                description="Topology not approved",
                blocking=True,
                required_lifecycle_state=ResourceLifecycleState.APPROVED,
                current_lifecycle_state=ResourceLifecycleState.PLANNED,
            ),
        ]
        all_resolved, reasons = resolve_dependencies(deps)
        assert all_resolved is False
        assert len(reasons) == 1

    def test_no_required_state_means_any_state_is_ok(self):
        dep = ChangeRequestDependency(
            dependency_type="device_availability",
            description="Device must be reachable",
            blocking=True,
            required_lifecycle_state=None,
            current_lifecycle_state=ResourceLifecycleState.CURRENT,
        )
        all_resolved, reasons = resolve_dependencies([dep])
        assert all_resolved is True
