"""Scenario tests for multi-domain workflows (Issue #65).

These tests cover the most important end-to-end scenarios for the Milestone 5
broader workflows.  All tests use mock data and in-memory state only — no
live backend dependencies.

Scenarios covered:
1. New site provisioning — happy path
2. New site provisioning — IPAM exhaustion blocks the workflow
3. VLAN expansion across sites — cross-domain dependency check
4. Topology link failure review — incident workflow
5. Policy-blocked VLAN proposal
6. Approval-required change with cross-domain dependency
"""
from __future__ import annotations

from net_agent_harness.models.changes import ChangeRequest, ChangeRequestDependency, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import (
    ChangeRisk,
    NetworkDomain,
    PlanDecisionType,
    RequestKind,
    ResourceLifecycleState,
    RoutingStatus,
    RunStage,
    TargetScope,
    Capability,
)
from net_agent_harness.models.incident import IncidentEvidence, IncidentSummary
from net_agent_harness.models.ipam import PrefixAllocationPlan
from net_agent_harness.models.routing import RoutedRequest
from net_agent_harness.models.site_provisioning import SiteProvisioningIntent, SubnetAllocation
from net_agent_harness.models.site_template import DesignPolicy, validate_against_design_policy
from net_agent_harness.models.topology import TopologyUpdatePlan
from net_agent_harness.orchestration.dependency_resolver import resolve_dependencies
from net_agent_harness.orchestration.dispatcher import DispatchMode, dispatch_request
from net_agent_harness.orchestration.graph_runner import (
    IPAMPlanWorkflowRunner,
    IncidentWorkflowRunner,
    SiteWorkflowRunner,
    TopologyPlanWorkflowRunner,
)
from net_agent_harness.orchestration.graph_state import GraphOutcome
from net_agent_harness.orchestration.intent_router import route_intent


def _meta(run_id: str = "run-scenario-1", created_by: str = "test") -> ArtifactMeta:
    return ArtifactMeta(
        run_id=run_id,
        artifact_id=f"art-{run_id}",
        created_by=created_by,
    )


# ---------------------------------------------------------------------------
# Scenario 1: New site provisioning — happy path
# ---------------------------------------------------------------------------


class TestNewSiteProvisioningHappyPath:
    """A request to provision a new branch site succeeds end-to-end."""

    def test_routes_to_site_plan(self):
        request = "Provision a new branch site BRANCH-07 with management and server subnets"
        routed = route_intent(request)
        assert routed.status is RoutingStatus.ROUTED
        assert routed.kind is RequestKind.PLAN
        assert routed.capability is Capability.SITE

    def test_dispatches_to_workflow_run(self):
        routed = RoutedRequest(
            status=RoutingStatus.ROUTED,
            kind=RequestKind.PLAN,
            capability=Capability.SITE,
            confidence=0.85,
            requires_run=True,
            requires_approval=False,
            rationale=["provision site", "site"],
        )
        decision = dispatch_request(routed)
        assert decision.mode is DispatchMode.WORKFLOW_RUN
        assert decision.handler == "site_workflow"
        assert decision.initial_stage is RunStage.DISCOVER

    def test_site_provisioning_intent_created(self):
        intent = SiteProvisioningIntent(
            meta=_meta("run-site-happy"),
            scope=ScopeRef(site="BRANCH-07"),
            site_name="BRANCH-07",
            summary="Provision new branch office at BRANCH-07",
            subnet_allocations=[
                SubnetAllocation(purpose="management", prefix="10.7.0.0/24", vlan_id=10),
                SubnetAllocation(purpose="servers", prefix="10.7.1.0/24", vlan_id=20),
            ],
            vlan_assignments=[10, 20],
            device_roles=["core", "access"],
        )
        assert intent.site_name == "BRANCH-07"
        assert len(intent.subnet_allocations) == 2

    def test_full_site_workflow_runner_happy_path(self):
        runner = SiteWorkflowRunner("run-site-happy")

        # Discover
        outcome = runner.advance(artifact_id="discover-1")
        assert outcome is GraphOutcome.APPLY

        # IPAM allocated
        runner.transition_to(RunStage.ALLOCATE_IPAM)
        outcome = runner.advance(
            ipam_decision=PlanDecisionType.APPLY.value, artifact_id="ipam-1"
        )
        assert outcome is GraphOutcome.APPLY

        # Topology planned
        runner.transition_to(RunStage.PLAN_TOPOLOGY)
        outcome = runner.advance(
            topology_decision=PlanDecisionType.APPLY.value, artifact_id="topo-1"
        )
        assert outcome is GraphOutcome.APPLY

        # Changes planned
        runner.transition_to(RunStage.PLAN_CHANGES)
        outcome = runner.advance(
            plan_decision=PlanDecisionType.APPLY.value, artifact_id="change-1"
        )
        assert outcome is GraphOutcome.APPLY

        # Validated
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(artifact_id="val-1")
        assert outcome is GraphOutcome.COMPLETE


# ---------------------------------------------------------------------------
# Scenario 2: New site provisioning — IPAM exhaustion
# ---------------------------------------------------------------------------


class TestNewSiteProvisioningIPAMExhausted:
    """IPAM allocation is blocked when the parent prefix is full."""

    def test_prefix_allocation_plan_blocked_when_parent_full(self):
        plan = PrefixAllocationPlan(
            meta=_meta("run-ipam-full"),
            parent_prefix="10.7.0.0/24",
            requested_prefix_length=25,
            decision=PlanDecisionType.BLOCKED,
            blocking_reason="Parent prefix 10.7.0.0/24 has no available /25 sub-blocks",
        )
        assert plan.decision is PlanDecisionType.BLOCKED
        assert "no available" in (plan.blocking_reason or "")

    def test_site_workflow_runner_blocked_at_ipam(self):
        runner = SiteWorkflowRunner("run-site-ipam-blocked")

        runner.advance(artifact_id="discover-1")

        runner.transition_to(RunStage.ALLOCATE_IPAM)
        outcome = runner.advance(ipam_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_site_workflow_errors_block_immediately(self):
        runner = SiteWorkflowRunner("run-site-errors")
        outcome = runner.advance(errors=["Inventory service unavailable"])
        assert outcome is GraphOutcome.BLOCKED


# ---------------------------------------------------------------------------
# Scenario 3: VLAN expansion across sites — cross-domain dependency check
# ---------------------------------------------------------------------------


class TestVlanExpansionCrossDomain:
    """A VLAN expansion that depends on an approved IPAM allocation."""

    def test_change_request_blocked_when_ipam_dep_not_approved(self):
        ipam_dep = ChangeRequestDependency(
            dependency_type="ipam_allocation",
            description="IPAM allocation for VLAN 300 subnet at HQ",
            artifact_id="art-ipam-1",
            run_id="run-ipam-001",
            required_lifecycle_state=ResourceLifecycleState.APPROVED,
            current_lifecycle_state=ResourceLifecycleState.PLANNED,
            blocking=True,
        )
        all_resolved, reasons = resolve_dependencies([ipam_dep])
        assert all_resolved is False
        assert len(reasons) == 1

    def test_change_request_unblocked_when_ipam_dep_approved(self):
        ipam_dep = ChangeRequestDependency(
            dependency_type="ipam_allocation",
            description="IPAM allocation for VLAN 300 subnet at HQ",
            artifact_id="art-ipam-1",
            run_id="run-ipam-001",
            required_lifecycle_state=ResourceLifecycleState.APPROVED,
            current_lifecycle_state=ResourceLifecycleState.APPROVED,
            blocking=True,
        )
        all_resolved, reasons = resolve_dependencies([ipam_dep])
        assert all_resolved is True
        assert reasons == []

    def test_change_request_with_cross_domain_deps_serializes(self):
        """ChangeRequest with cross_domain_dependencies round-trips through JSON."""
        cr = ChangeRequest(
            meta=_meta("run-cr-cross"),
            domain=NetworkDomain.VLAN,
            scope=ScopeRef(site="HQ"),
            target_scope=TargetScope.site,
            requested_change=RequestedChange(
                summary="Add VLAN 300 at HQ",
                intent="Add VLAN 300 for IoT devices at HQ",
                desired_state={},
            ),
            risk=ChangeRisk.MEDIUM,
            rollback_plan=RollbackPlan(summary="Remove VLAN 300", rollback_steps=["delete vlan 300"]),
            cross_domain_dependencies=[
                ChangeRequestDependency(
                    dependency_type="ipam_allocation",
                    description="Reserve 10.0.30.0/24 for VLAN 300",
                    required_lifecycle_state=ResourceLifecycleState.APPROVED,
                    current_lifecycle_state=ResourceLifecycleState.PLANNED,
                )
            ],
        )
        serialized = cr.model_dump_json()
        restored = ChangeRequest.model_validate_json(serialized)
        assert len(restored.cross_domain_dependencies) == 1
        dep = restored.cross_domain_dependencies[0]
        assert dep.dependency_type == "ipam_allocation"
        assert dep.required_lifecycle_state == ResourceLifecycleState.APPROVED


# ---------------------------------------------------------------------------
# Scenario 4: Topology link failure review — incident workflow
# ---------------------------------------------------------------------------


class TestTopologyLinkFailureIncidentReview:
    """An incident review for a topology link failure produces a summary."""

    def test_routes_to_incident_review(self):
        request = "Review the outage: sw1 uplink is down and traffic is degraded at HQ"
        routed = route_intent(request)
        assert routed.status is RoutingStatus.ROUTED
        assert routed.kind is RequestKind.REVIEW
        assert routed.capability is Capability.INCIDENT

    def test_dispatches_to_workflow_run(self):
        routed = RoutedRequest(
            status=RoutingStatus.ROUTED,
            kind=RequestKind.REVIEW,
            capability=Capability.INCIDENT,
            confidence=0.8,
            requires_run=False,
            requires_approval=False,
            rationale=["outage", "down"],
        )
        decision = dispatch_request(routed)
        assert decision.mode is DispatchMode.WORKFLOW_RUN
        assert decision.handler == "incident_review"
        assert decision.initial_stage is RunStage.INCIDENT

    def test_incident_workflow_produces_summary(self):
        runner = IncidentWorkflowRunner("run-inc-link")

        # Gather evidence
        outcome = runner.advance(artifact_id="evidence-1")
        assert outcome is GraphOutcome.APPLY

        # Produce summary
        runner.transition_to(RunStage.REVIEW)
        outcome = runner.advance(artifact_id="summary-1")
        assert outcome is GraphOutcome.COMPLETE

    def test_incident_summary_carries_evidence(self):
        evidence = IncidentEvidence(
            logs=["14:00 ge-0/0/0: link down", "14:01 STP: topology change"],
            recent_changes=["run-change-abc"],
            device_facts={"sw1": {"uplink": "down"}},
        )
        summary = IncidentSummary(
            meta=_meta("run-inc-link"),
            scope=ScopeRef(site="HQ", device_names=["sw1"]),
            title="Uplink failure on sw1",
            summary="The primary uplink on sw1 failed at 14:00 UTC.",
            severity="high",
            affected_devices=["sw1", "sw2", "sw3"],
            findings=["ge-0/0/0 link fault", "STP topology reconverged"],
            recommended_actions=["Replace ge-0/0/0 cable", "Verify STP state"],
            evidence=evidence,
            related_change_run_ids=["run-change-abc"],
        )
        assert summary.severity == "high"
        assert len(summary.affected_devices) == 3
        assert len(summary.findings) == 2
        assert "run-change-abc" in summary.related_change_run_ids


# ---------------------------------------------------------------------------
# Scenario 5: Policy-blocked VLAN proposal
# ---------------------------------------------------------------------------


class TestPolicyBlockedVlanProposal:
    """A VLAN proposal outside the allowed range is blocked by design policy."""

    def test_vlan_outside_policy_range_is_blocked(self):
        policy = DesignPolicy(
            name="strict-branch",
            allowed_vlan_ranges=[(10, 99), (200, 299)],
        )
        violations = validate_against_design_policy(
            proposed_vlans=[500],  # outside (10-99) and (200-299)
            proposed_prefixes={},
            policy=policy,
        )
        assert len(violations) == 1
        assert violations[0].severity == "blocked"

    def test_prefix_too_broad_blocked_by_policy(self):
        policy = DesignPolicy(
            name="strict-branch",
            required_prefix_lengths={"management": 24},
        )
        violations = validate_against_design_policy(
            proposed_vlans=[],
            proposed_prefixes={"management": 22},  # /22 is less specific than required /24
            policy=policy,
        )
        assert len(violations) == 1
        assert "required_prefix_length" == violations[0].rule

    def test_compliant_vlan_passes_policy(self):
        policy = DesignPolicy(
            name="strict-branch",
            allowed_vlan_ranges=[(10, 99)],
        )
        violations = validate_against_design_policy(
            proposed_vlans=[10, 50, 99],
            proposed_prefixes={},
            policy=policy,
        )
        assert violations == []


# ---------------------------------------------------------------------------
# Scenario 6: Approval-required IPAM plan
# ---------------------------------------------------------------------------


class TestApprovalRequiredIPAMPlan:
    """An IPAM allocation plan that requires approval before rendering."""

    def test_ipam_plan_lifecycle_starts_at_planned(self):
        plan = PrefixAllocationPlan(
            meta=_meta("run-ipam-approval"),
            parent_prefix="10.20.0.0/16",
            requested_prefix_length=24,
            proposed_prefix="10.20.5.0/24",
            overlap_check_passed=True,
            policy_check_passed=True,
            decision=PlanDecisionType.APPLY,
        )
        assert plan.lifecycle_state is ResourceLifecycleState.PLANNED

    def test_ipam_plan_runner_applies_then_validates(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-approval")

        outcome = runner.advance(
            plan_decision=PlanDecisionType.APPLY.value,
            artifact_id="ipam-plan-1",
        )
        assert outcome is GraphOutcome.APPLY

        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(artifact_id="ipam-val-1")
        assert outcome is GraphOutcome.COMPLETE

    def test_ipam_plan_with_missing_parent_prefix_is_blocked(self):
        PrefixAllocationPlan(
            meta=_meta("run-ipam-missing"),
            parent_prefix="192.168.0.0/24",
            requested_prefix_length=25,
            decision=PlanDecisionType.BLOCKED,
            blocking_reason="Parent prefix 192.168.0.0/24 is fully allocated",
        )
        runner = IPAMPlanWorkflowRunner("run-ipam-missing")
        outcome = runner.advance(plan_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_topology_plan_missing_device_facts_is_blocked(self):
        plan = TopologyUpdatePlan(
            meta=_meta("run-topo-missing"),
            scope=ScopeRef(site="HQ"),
            summary="Add uplink between sw1 and core1",
            decision=PlanDecisionType.BLOCKED,
            blocking_reason="Device facts unavailable for sw1",
            missing_device_facts=["sw1"],
        )
        runner = TopologyPlanWorkflowRunner("run-topo-missing")
        outcome = runner.advance(plan_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED
        assert "sw1" in plan.missing_device_facts
