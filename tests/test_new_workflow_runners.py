"""Tests for new workflow runners added in Milestone 5 (Issues #51, #59, #60, #61)."""
from net_agent_harness.models.enums import Capability, PlanDecisionType, RunStage
from net_agent_harness.orchestration.graph_runner import (
    IPAMPlanWorkflowRunner,
    IncidentWorkflowRunner,
    SiteWorkflowRunner,
    TopologyPlanWorkflowRunner,
)
from net_agent_harness.orchestration.graph_state import GraphOutcome


class TestIncidentWorkflowRunner:
    def test_initial_stage_is_incident(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        assert runner.current_stage is RunStage.INCIDENT

    def test_incident_stage_returns_apply(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        outcome = runner.advance(artifact_id="evidence-1")
        assert outcome is GraphOutcome.APPLY

    def test_incident_stage_with_errors_returns_blocked(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        outcome = runner.advance(errors=["Evidence unavailable"])
        assert outcome is GraphOutcome.BLOCKED

    def test_review_stage_returns_complete(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        runner.advance()
        runner.transition_to(RunStage.REVIEW)
        outcome = runner.advance(artifact_id="summary-1")
        assert outcome is GraphOutcome.COMPLETE

    def test_review_stage_with_errors_returns_blocked(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        runner.advance()
        runner.transition_to(RunStage.REVIEW)
        outcome = runner.advance(errors=["Analysis failed"])
        assert outcome is GraphOutcome.BLOCKED

    def test_transition_clears_outcome(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        runner.advance()
        assert runner.outcome is GraphOutcome.APPLY
        runner.transition_to(RunStage.REVIEW)
        assert runner.outcome is None

    def test_artifact_ids_stored(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        runner.advance(artifact_id="evidence-1")
        assert runner.state.artifact_ids["incident"] == "evidence-1"

    def test_capability_is_incident(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        assert runner.state.capability is Capability.INCIDENT

    def test_unknown_stage_returns_failed(self):
        runner = IncidentWorkflowRunner("run-inc-1")
        runner.state.current_stage = RunStage.PLAN  # unexpected stage
        outcome = runner.advance()
        assert outcome is GraphOutcome.FAILED


class TestIPAMPlanWorkflowRunner:
    def test_initial_stage_is_plan(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        assert runner.current_stage is RunStage.PLAN

    def test_plan_apply_returns_apply(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        assert outcome is GraphOutcome.APPLY

    def test_plan_blocked_returns_blocked(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_plan_no_op_returns_no_op(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.NO_OP.value)
        assert outcome is GraphOutcome.NO_OP

    def test_plan_missing_decision_returns_blocked(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        outcome = runner.advance()
        assert outcome is GraphOutcome.BLOCKED

    def test_validate_no_errors_returns_complete(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(artifact_id="val-1")
        assert outcome is GraphOutcome.COMPLETE

    def test_validate_with_errors_returns_failed(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(errors=["Policy check failed"])
        assert outcome is GraphOutcome.FAILED

    def test_capability_is_ipam(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        assert runner.state.capability is Capability.IPAM

    def test_artifact_id_stored(self):
        runner = IPAMPlanWorkflowRunner("run-ipam-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value, artifact_id="plan-1")
        assert runner.state.artifact_ids["plan"] == "plan-1"


class TestTopologyPlanWorkflowRunner:
    def test_initial_stage_is_plan(self):
        runner = TopologyPlanWorkflowRunner("run-topo-1")
        assert runner.current_stage is RunStage.PLAN

    def test_plan_apply_returns_apply(self):
        runner = TopologyPlanWorkflowRunner("run-topo-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        assert outcome is GraphOutcome.APPLY

    def test_plan_blocked_returns_blocked(self):
        runner = TopologyPlanWorkflowRunner("run-topo-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_plan_no_op_returns_no_op(self):
        runner = TopologyPlanWorkflowRunner("run-topo-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.NO_OP.value)
        assert outcome is GraphOutcome.NO_OP

    def test_validate_complete_returns_complete(self):
        runner = TopologyPlanWorkflowRunner("run-topo-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance()
        assert outcome is GraphOutcome.COMPLETE

    def test_validate_with_errors_returns_failed(self):
        runner = TopologyPlanWorkflowRunner("run-topo-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(errors=["Missing device facts"])
        assert outcome is GraphOutcome.FAILED

    def test_capability_is_topology(self):
        runner = TopologyPlanWorkflowRunner("run-topo-1")
        assert runner.state.capability is Capability.TOPOLOGY


class TestSiteWorkflowRunner:
    def test_initial_stage_is_discover(self):
        runner = SiteWorkflowRunner("run-site-1")
        assert runner.current_stage is RunStage.DISCOVER

    def test_discover_no_errors_returns_apply(self):
        runner = SiteWorkflowRunner("run-site-1")
        outcome = runner.advance(artifact_id="discover-1")
        assert outcome is GraphOutcome.APPLY

    def test_discover_with_errors_returns_blocked(self):
        runner = SiteWorkflowRunner("run-site-1")
        outcome = runner.advance(errors=["Inventory unavailable"])
        assert outcome is GraphOutcome.BLOCKED

    def test_allocate_ipam_apply_returns_apply(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.advance()
        runner.transition_to(RunStage.ALLOCATE_IPAM)
        outcome = runner.advance(ipam_decision=PlanDecisionType.APPLY.value)
        assert outcome is GraphOutcome.APPLY

    def test_allocate_ipam_blocked_returns_blocked(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.advance()
        runner.transition_to(RunStage.ALLOCATE_IPAM)
        outcome = runner.advance(ipam_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_plan_topology_apply_returns_apply(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.advance()
        runner.transition_to(RunStage.PLAN_TOPOLOGY)
        outcome = runner.advance(topology_decision=PlanDecisionType.APPLY.value)
        assert outcome is GraphOutcome.APPLY

    def test_plan_topology_blocked_returns_blocked(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.advance()
        runner.transition_to(RunStage.PLAN_TOPOLOGY)
        outcome = runner.advance(topology_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_plan_changes_apply_returns_apply(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.advance()
        runner.transition_to(RunStage.PLAN_CHANGES)
        outcome = runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        assert outcome is GraphOutcome.APPLY

    def test_plan_changes_blocked_returns_blocked(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.advance()
        runner.transition_to(RunStage.PLAN_CHANGES)
        outcome = runner.advance(plan_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_validate_no_errors_returns_complete(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance()
        assert outcome is GraphOutcome.COMPLETE

    def test_validate_with_errors_returns_failed(self):
        runner = SiteWorkflowRunner("run-site-1")
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(errors=["Validation failed"])
        assert outcome is GraphOutcome.FAILED

    def test_capability_is_site(self):
        runner = SiteWorkflowRunner("run-site-1")
        assert runner.state.capability is Capability.SITE

    def test_full_happy_path(self):
        runner = SiteWorkflowRunner("run-site-1")
        # Discover
        outcome = runner.advance(artifact_id="discover-1")
        assert outcome is GraphOutcome.APPLY

        # Allocate IPAM
        runner.transition_to(RunStage.ALLOCATE_IPAM)
        outcome = runner.advance(ipam_decision=PlanDecisionType.APPLY.value, artifact_id="ipam-1")
        assert outcome is GraphOutcome.APPLY

        # Plan topology
        runner.transition_to(RunStage.PLAN_TOPOLOGY)
        outcome = runner.advance(
            topology_decision=PlanDecisionType.APPLY.value, artifact_id="topo-1"
        )
        assert outcome is GraphOutcome.APPLY

        # Plan changes
        runner.transition_to(RunStage.PLAN_CHANGES)
        outcome = runner.advance(
            plan_decision=PlanDecisionType.APPLY.value, artifact_id="change-1"
        )
        assert outcome is GraphOutcome.APPLY

        # Validate
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(artifact_id="val-1")
        assert outcome is GraphOutcome.COMPLETE

        # All artifacts stored
        assert runner.state.artifact_ids["discover"] == "discover-1"
        assert runner.state.artifact_ids["allocate_ipam"] == "ipam-1"
        assert runner.state.artifact_ids["plan_topology"] == "topo-1"
        assert runner.state.artifact_ids["plan_changes"] == "change-1"
        assert runner.state.artifact_ids["validate"] == "val-1"
