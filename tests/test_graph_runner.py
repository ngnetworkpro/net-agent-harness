"""Tests for graph state models and workflow runners (Issue #46)."""
import pytest

from net_agent_harness.models.enums import Capability, PlanDecisionType, RunStage
from net_agent_harness.orchestration.graph_runner import (
    ChangeWorkflowRunner,
    DiscoveryWorkflowRunner,
)
from net_agent_harness.orchestration.graph_state import (
    DiscoveryGraphState,
    GraphOutcome,
    WorkflowGraphState,
)


class TestGraphStateModels:
    def test_workflow_graph_state_defaults(self):
        state = WorkflowGraphState(
            run_id="run-1",
            capability=Capability.CHANGE,
            current_stage=RunStage.PLAN,
        )
        assert state.outcome is None
        assert state.artifact_ids == {}
        assert state.errors == []
        assert state.metadata == {}

    def test_discovery_graph_state_defaults(self):
        state = DiscoveryGraphState(
            run_id="run-1",
            capability=Capability.TOPOLOGY,
            current_stage=RunStage.DISCOVER,
        )
        assert state.outcome is None
        assert state.errors == []

    def test_graph_state_rejects_extra_fields(self):
        with pytest.raises(Exception):
            WorkflowGraphState(
                run_id="r",
                capability=Capability.CHANGE,
                current_stage=RunStage.PLAN,
                unexpected="oops",
            )

    def test_graph_outcome_values(self):
        assert GraphOutcome.APPLY.value == "apply"
        assert GraphOutcome.NO_OP.value == "no_op"
        assert GraphOutcome.BLOCKED.value == "blocked"
        assert GraphOutcome.APPROVAL_PENDING.value == "approval_pending"
        assert GraphOutcome.COMPLETE.value == "complete"
        assert GraphOutcome.FAILED.value == "failed"


class TestChangeWorkflowRunner:
    def test_initial_stage_is_plan(self):
        runner = ChangeWorkflowRunner("run-1")
        assert runner.current_stage is RunStage.PLAN

    def test_plan_apply_returns_apply(self):
        runner = ChangeWorkflowRunner("run-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        assert outcome is GraphOutcome.APPLY

    def test_plan_no_op_returns_no_op(self):
        runner = ChangeWorkflowRunner("run-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.NO_OP.value)
        assert outcome is GraphOutcome.NO_OP

    def test_plan_blocked_returns_blocked(self):
        runner = ChangeWorkflowRunner("run-1")
        outcome = runner.advance(plan_decision=PlanDecisionType.BLOCKED.value)
        assert outcome is GraphOutcome.BLOCKED

    def test_plan_missing_decision_returns_blocked(self):
        runner = ChangeWorkflowRunner("run-1")
        outcome = runner.advance()
        assert outcome is GraphOutcome.BLOCKED

    def test_render_stage_no_errors_returns_apply(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.RENDER)
        outcome = runner.advance(artifact_id="render-abc")
        assert outcome is GraphOutcome.APPLY

    def test_render_stage_with_errors_returns_failed(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.RENDER)
        outcome = runner.advance(errors=["Render failed"])
        assert outcome is GraphOutcome.FAILED

    def test_validate_approved_returns_approval_pending(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.RENDER)
        runner.advance()
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(approved_for_execution=True)
        assert outcome is GraphOutcome.APPROVAL_PENDING

    def test_validate_not_approved_returns_blocked(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        runner.transition_to(RunStage.RENDER)
        runner.advance()
        runner.transition_to(RunStage.VALIDATE)
        outcome = runner.advance(approved_for_execution=False)
        assert outcome is GraphOutcome.BLOCKED

    def test_approval_pending_operator_approved_returns_apply(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.state.current_stage = RunStage.APPROVAL_PENDING
        outcome = runner.advance(operator_approved=True)
        assert outcome is GraphOutcome.APPLY

    def test_approval_pending_operator_denied_returns_blocked(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.state.current_stage = RunStage.APPROVAL_PENDING
        outcome = runner.advance(operator_approved=False)
        assert outcome is GraphOutcome.BLOCKED

    def test_execute_no_errors_returns_complete(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.transition_to(RunStage.EXECUTE)
        outcome = runner.advance()
        assert outcome is GraphOutcome.COMPLETE

    def test_execute_with_errors_returns_failed(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.transition_to(RunStage.EXECUTE)
        outcome = runner.advance(errors=["Timeout"])
        assert outcome is GraphOutcome.FAILED

    def test_artifact_ids_stored_per_stage(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value, artifact_id="cr-1")
        assert runner.state.artifact_ids["plan"] == "cr-1"

    def test_transition_clears_outcome(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.advance(plan_decision=PlanDecisionType.APPLY.value)
        assert runner.outcome is GraphOutcome.APPLY
        runner.transition_to(RunStage.RENDER)
        assert runner.outcome is None

    def test_errors_accumulate_across_advances(self):
        runner = ChangeWorkflowRunner("run-1")
        runner.advance(errors=["e1"])
        runner.advance(errors=["e2"])
        assert "e1" in runner.state.errors
        assert "e2" in runner.state.errors


class TestDiscoveryWorkflowRunner:
    def test_initial_stage_is_discover(self):
        runner = DiscoveryWorkflowRunner("run-1", Capability.TOPOLOGY)
        assert runner.current_stage is RunStage.DISCOVER

    def test_discover_no_errors_returns_complete(self):
        runner = DiscoveryWorkflowRunner("run-1", Capability.TOPOLOGY)
        outcome = runner.advance(artifact_id="answer-1")
        assert outcome is GraphOutcome.COMPLETE

    def test_discover_with_errors_returns_blocked(self):
        runner = DiscoveryWorkflowRunner("run-1", Capability.TOPOLOGY)
        outcome = runner.advance(errors=["Inventory unavailable"])
        assert outcome is GraphOutcome.BLOCKED

    def test_artifact_id_stored(self):
        runner = DiscoveryWorkflowRunner("run-1", Capability.IPAM)
        runner.advance(artifact_id="ipam-result-1")
        assert runner.state.artifact_ids["discover"] == "ipam-result-1"

    def test_transition_clears_outcome(self):
        runner = DiscoveryWorkflowRunner("run-1", Capability.TOPOLOGY)
        runner.advance()
        runner.transition_to(RunStage.VERIFY)
        assert runner.outcome is None
        assert runner.current_stage is RunStage.VERIFY

    def test_capability_stored_in_state(self):
        runner = DiscoveryWorkflowRunner("run-1", Capability.IPAM)
        assert runner.state.capability is Capability.IPAM
