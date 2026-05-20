"""
Workflow graph runners for multi-step change and discovery paths.

Each runner holds a GraphState and exposes an ``advance`` method that evaluates
deterministic edge logic and returns a GraphOutcome.  The runners do **not**
call agents, load artifacts, or touch the network — that remains the
responsibility of the orchestration layer (coordinator.py / main.py).

Direct-answer requests (ask.topology, ask.ipam) bypass this module entirely;
they do not need stateful graph routing.

Usage example (change workflow):

    runner = ChangeWorkflowRunner(run_id="run-abc")
    outcome = runner.advance(plan_decision="apply", artifact_id="cr-abc")
    if outcome is GraphOutcome.APPLY:
        runner.transition_to(RunStage.RENDER)
        outcome = runner.advance(artifact_id="render-abc")
        ...
"""
from ..models.enums import Capability, PlanDecisionType, RunStage
from .graph_state import DiscoveryGraphState, GraphOutcome, WorkflowGraphState


# ---------------------------------------------------------------------------
# Internal edge functions — pure, deterministic, no side effects.
# ---------------------------------------------------------------------------


def _change_edge(state: WorkflowGraphState) -> GraphOutcome:
    """Return the correct outcome for the current change-workflow stage."""
    stage = state.current_stage

    if stage is RunStage.PLAN:
        decision = state.metadata.get("plan_decision")
        if decision == PlanDecisionType.NO_OP.value:
            return GraphOutcome.NO_OP
        if decision == PlanDecisionType.BLOCKED.value:
            return GraphOutcome.BLOCKED
        if decision == PlanDecisionType.APPLY.value:
            return GraphOutcome.APPLY
        # Missing or unrecognised decision — fail safe.
        return GraphOutcome.BLOCKED

    if stage is RunStage.RENDER:
        if state.errors:
            return GraphOutcome.FAILED
        return GraphOutcome.APPLY

    if stage is RunStage.VALIDATE:
        approved = state.metadata.get("approved_for_execution", False)
        return GraphOutcome.APPROVAL_PENDING if approved else GraphOutcome.BLOCKED

    if stage is RunStage.APPROVAL_PENDING:
        operator_approved = state.metadata.get("operator_approved", False)
        return GraphOutcome.APPLY if operator_approved else GraphOutcome.BLOCKED

    if stage is RunStage.EXECUTE:
        if state.errors:
            return GraphOutcome.FAILED
        return GraphOutcome.COMPLETE

    return GraphOutcome.FAILED


def _discovery_edge(state: DiscoveryGraphState) -> GraphOutcome:
    """Return the correct outcome for the current discovery-workflow stage."""
    if state.errors:
        return GraphOutcome.BLOCKED

    stage = state.current_stage
    if stage is RunStage.DISCOVER:
        return GraphOutcome.COMPLETE

    return GraphOutcome.FAILED


def _incident_edge(state: WorkflowGraphState) -> GraphOutcome:
    """Return the correct outcome for the current incident-workflow stage."""
    if state.errors:
        return GraphOutcome.BLOCKED

    stage = state.current_stage

    if stage is RunStage.INCIDENT:
        return GraphOutcome.APPLY

    if stage is RunStage.REVIEW:
        return GraphOutcome.COMPLETE

    return GraphOutcome.FAILED


def _plan_edge(state: WorkflowGraphState) -> GraphOutcome:
    """Shared edge logic for single-stage plan → validate workflows.

    Used by both ``IPAMPlanWorkflowRunner`` and ``TopologyPlanWorkflowRunner``.
    """
    stage = state.current_stage

    if stage is RunStage.PLAN:
        decision = state.metadata.get("plan_decision")
        if decision == PlanDecisionType.NO_OP.value:
            return GraphOutcome.NO_OP
        if decision == PlanDecisionType.BLOCKED.value:
            return GraphOutcome.BLOCKED
        if decision == PlanDecisionType.APPLY.value:
            return GraphOutcome.APPLY
        return GraphOutcome.BLOCKED

    if stage is RunStage.VALIDATE:
        if state.errors:
            return GraphOutcome.FAILED
        return GraphOutcome.COMPLETE

    return GraphOutcome.FAILED


def _site_edge(state: WorkflowGraphState) -> GraphOutcome:
    """Return the correct outcome for the current site-provisioning stage."""
    stage = state.current_stage

    if stage is RunStage.DISCOVER:
        if state.errors:
            return GraphOutcome.BLOCKED
        return GraphOutcome.APPLY

    if stage is RunStage.ALLOCATE_IPAM:
        if state.errors:
            return GraphOutcome.BLOCKED
        decision = state.metadata.get("ipam_decision")
        if decision == PlanDecisionType.BLOCKED.value:
            return GraphOutcome.BLOCKED
        return GraphOutcome.APPLY

    if stage is RunStage.PLAN_TOPOLOGY:
        if state.errors:
            return GraphOutcome.BLOCKED
        decision = state.metadata.get("topology_decision")
        if decision == PlanDecisionType.BLOCKED.value:
            return GraphOutcome.BLOCKED
        return GraphOutcome.APPLY

    if stage is RunStage.PLAN_CHANGES:
        if state.errors:
            return GraphOutcome.BLOCKED
        decision = state.metadata.get("plan_decision")
        if decision == PlanDecisionType.BLOCKED.value:
            return GraphOutcome.BLOCKED
        return GraphOutcome.APPLY

    if stage is RunStage.VALIDATE:
        if state.errors:
            return GraphOutcome.FAILED
        return GraphOutcome.COMPLETE

    return GraphOutcome.FAILED


# ---------------------------------------------------------------------------
# Public runner classes
# ---------------------------------------------------------------------------


class ChangeWorkflowRunner:
    """Stateful runner for the change workflow graph.

    Stage sequence: plan → render → validate → approval_pending → execute

    Each call to ``advance`` evaluates the deterministic edge for the current
    stage and returns the resulting ``GraphOutcome``.  Callers are responsible
    for calling ``transition_to`` before each subsequent ``advance``.
    """

    def __init__(self, run_id: str) -> None:
        self.state = WorkflowGraphState(
            run_id=run_id,
            capability=Capability.CHANGE,
            current_stage=RunStage.PLAN,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def advance(
        self,
        *,
        plan_decision: str | None = None,
        approved_for_execution: bool = False,
        operator_approved: bool = False,
        artifact_id: str | None = None,
        errors: list[str] | None = None,
    ) -> GraphOutcome:
        """Evaluate the current stage edge and return the resulting outcome.

        Parameters
        ----------
        plan_decision:
            ``PlanDecisionType`` value string (``"apply"``, ``"no_op"``,
            ``"blocked"``).  Consumed only at the ``plan`` stage.
        approved_for_execution:
            Whether the validation report approved the change for execution.
            Consumed only at the ``validate`` stage.
        operator_approved:
            Whether the human operator confirmed execution at the approval gate.
            Consumed only at the ``approval_pending`` stage.
        artifact_id:
            Artifact ID written during this stage; stored in ``state.artifact_ids``.
        errors:
            Any errors encountered during this stage.
        """
        if plan_decision is not None:
            self.state.metadata["plan_decision"] = plan_decision
        if approved_for_execution:
            self.state.metadata["approved_for_execution"] = approved_for_execution
        if operator_approved:
            self.state.metadata["operator_approved"] = operator_approved
        if errors:
            self.state.errors.extend(errors)
        if artifact_id:
            self.state.artifact_ids[self.state.current_stage.value] = artifact_id

        outcome = _change_edge(self.state)
        self.state.outcome = outcome
        return outcome

    def transition_to(self, stage: RunStage) -> None:
        """Move to the next stage, clearing the previous outcome."""
        self.state.current_stage = stage
        self.state.outcome = None

    @property
    def current_stage(self) -> RunStage:
        return self.state.current_stage

    @property
    def outcome(self) -> GraphOutcome | None:
        return self.state.outcome


class DiscoveryWorkflowRunner:
    """Stateful runner for the discovery workflow graph.

    Stage sequence: discover → answer

    This runner is used for discovery flows that require multi-step inventory
    or IPAM inspection before producing an answer.  Simple direct-answer
    requests bypass this class entirely (they do not instantiate a runner).
    """

    def __init__(self, run_id: str, capability: Capability) -> None:
        self.state = DiscoveryGraphState(
            run_id=run_id,
            capability=capability,
            current_stage=RunStage.DISCOVER,
        )

    def advance(
        self,
        *,
        artifact_id: str | None = None,
        errors: list[str] | None = None,
    ) -> GraphOutcome:
        """Evaluate the current discovery stage and return the outcome."""
        if errors:
            self.state.errors.extend(errors)
        if artifact_id:
            self.state.artifact_ids[self.state.current_stage.value] = artifact_id

        outcome = _discovery_edge(self.state)
        self.state.outcome = outcome
        return outcome

    def transition_to(self, stage: RunStage) -> None:
        """Move to the next stage, clearing the previous outcome."""
        self.state.current_stage = stage
        self.state.outcome = None

    @property
    def current_stage(self) -> RunStage:
        return self.state.current_stage

    @property
    def outcome(self) -> GraphOutcome | None:
        return self.state.outcome


class IncidentWorkflowRunner:
    """Stateful runner for the incident review workflow graph.

    Stage sequence: incident → review

    The incident workflow is read-only: it consumes evidence and produces
    an ``IncidentSummary`` artifact.  No device configuration is generated
    or applied.

    - ``incident`` stage: gather and analyse evidence.
    - ``review``   stage: produce the final ``IncidentSummary`` artifact.
    """

    def __init__(self, run_id: str) -> None:
        self.state = WorkflowGraphState(
            run_id=run_id,
            capability=Capability.INCIDENT,
            current_stage=RunStage.INCIDENT,
        )

    def advance(
        self,
        *,
        artifact_id: str | None = None,
        errors: list[str] | None = None,
    ) -> GraphOutcome:
        """Evaluate the current incident-workflow stage and return the outcome."""
        if errors:
            self.state.errors.extend(errors)
        if artifact_id:
            self.state.artifact_ids[self.state.current_stage.value] = artifact_id

        outcome = _incident_edge(self.state)
        self.state.outcome = outcome
        return outcome

    def transition_to(self, stage: RunStage) -> None:
        """Move to the next stage, clearing the previous outcome."""
        self.state.current_stage = stage
        self.state.outcome = None

    @property
    def current_stage(self) -> RunStage:
        return self.state.current_stage

    @property
    def outcome(self) -> GraphOutcome | None:
        return self.state.outcome


class IPAMPlanWorkflowRunner:
    """Stateful runner for the IPAM allocation planning workflow.

    Stage sequence: plan → validate

    Produces a ``PrefixAllocationPlan`` or ``IPAssignmentPlan`` artifact.
    No writes are made to any IPAM backend; the artifact is read-only until
    explicit approval gates are wired in a later phase.
    """

    def __init__(self, run_id: str) -> None:
        self.state = WorkflowGraphState(
            run_id=run_id,
            capability=Capability.IPAM,
            current_stage=RunStage.PLAN,
        )

    def advance(
        self,
        *,
        plan_decision: str | None = None,
        artifact_id: str | None = None,
        errors: list[str] | None = None,
    ) -> GraphOutcome:
        """Evaluate the current IPAM-plan stage and return the outcome."""
        if plan_decision is not None:
            self.state.metadata["plan_decision"] = plan_decision
        if errors:
            self.state.errors.extend(errors)
        if artifact_id:
            self.state.artifact_ids[self.state.current_stage.value] = artifact_id

        outcome = _plan_edge(self.state)
        self.state.outcome = outcome
        return outcome

    def transition_to(self, stage: RunStage) -> None:
        """Move to the next stage, clearing the previous outcome."""
        self.state.current_stage = stage
        self.state.outcome = None

    @property
    def current_stage(self) -> RunStage:
        return self.state.current_stage

    @property
    def outcome(self) -> GraphOutcome | None:
        return self.state.outcome


class TopologyPlanWorkflowRunner:
    """Stateful runner for the topology update planning workflow.

    Stage sequence: plan → validate

    Produces a ``TopologyUpdatePlan`` artifact.  Plans do not generate
    device configuration — that remains a render step after approval.
    """

    def __init__(self, run_id: str) -> None:
        self.state = WorkflowGraphState(
            run_id=run_id,
            capability=Capability.TOPOLOGY,
            current_stage=RunStage.PLAN,
        )

    def advance(
        self,
        *,
        plan_decision: str | None = None,
        artifact_id: str | None = None,
        errors: list[str] | None = None,
    ) -> GraphOutcome:
        """Evaluate the current topology-plan stage and return the outcome."""
        if plan_decision is not None:
            self.state.metadata["plan_decision"] = plan_decision
        if errors:
            self.state.errors.extend(errors)
        if artifact_id:
            self.state.artifact_ids[self.state.current_stage.value] = artifact_id

        outcome = _plan_edge(self.state)
        self.state.outcome = outcome
        return outcome

    def transition_to(self, stage: RunStage) -> None:
        """Move to the next stage, clearing the previous outcome."""
        self.state.current_stage = stage
        self.state.outcome = None

    @property
    def current_stage(self) -> RunStage:
        return self.state.current_stage

    @property
    def outcome(self) -> GraphOutcome | None:
        return self.state.outcome


class SiteWorkflowRunner:
    """Stateful runner for the site provisioning workflow graph.

    Stage sequence:
        discover → allocate_ipam → plan_topology → plan_changes → validate

    Each stage produces a child artifact linked to a ``SiteProvisioningIntent``.
    All stages remain read-only or mock-backed initially; no live infrastructure
    changes are attempted.
    """

    def __init__(self, run_id: str) -> None:
        self.state = WorkflowGraphState(
            run_id=run_id,
            capability=Capability.SITE,
            current_stage=RunStage.DISCOVER,
        )

    def advance(
        self,
        *,
        ipam_decision: str | None = None,
        topology_decision: str | None = None,
        plan_decision: str | None = None,
        artifact_id: str | None = None,
        errors: list[str] | None = None,
    ) -> GraphOutcome:
        """Evaluate the current site-provisioning stage and return the outcome.

        Parameters
        ----------
        ipam_decision:
            Decision from the IPAM allocation stage (``"apply"`` or ``"blocked"``).
            Consumed only at the ``allocate_ipam`` stage.
        topology_decision:
            Decision from the topology planning stage.
            Consumed only at the ``plan_topology`` stage.
        plan_decision:
            Decision from the change planning stage.
            Consumed only at the ``plan_changes`` stage.
        artifact_id:
            Artifact ID written during this stage.
        errors:
            Any errors encountered during this stage.
        """
        if ipam_decision is not None:
            self.state.metadata["ipam_decision"] = ipam_decision
        if topology_decision is not None:
            self.state.metadata["topology_decision"] = topology_decision
        if plan_decision is not None:
            self.state.metadata["plan_decision"] = plan_decision
        if errors:
            self.state.errors.extend(errors)
        if artifact_id:
            self.state.artifact_ids[self.state.current_stage.value] = artifact_id

        outcome = _site_edge(self.state)
        self.state.outcome = outcome
        return outcome

    def transition_to(self, stage: RunStage) -> None:
        """Move to the next stage, clearing the previous outcome."""
        self.state.current_stage = stage
        self.state.outcome = None

    @property
    def current_stage(self) -> RunStage:
        return self.state.current_stage

    @property
    def outcome(self) -> GraphOutcome | None:
        return self.state.outcome



# ---------------------------------------------------------------------------
# Internal edge functions — pure, deterministic, no side effects.
# ---------------------------------------------------------------------------


def _change_edge(state: WorkflowGraphState) -> GraphOutcome:
    """Return the correct outcome for the current change-workflow stage."""
    stage = state.current_stage

    if stage is RunStage.PLAN:
        decision = state.metadata.get("plan_decision")
        if decision == PlanDecisionType.NO_OP.value:
            return GraphOutcome.NO_OP
        if decision == PlanDecisionType.BLOCKED.value:
            return GraphOutcome.BLOCKED
        if decision == PlanDecisionType.APPLY.value:
            return GraphOutcome.APPLY
        # Missing or unrecognised decision — fail safe.
        return GraphOutcome.BLOCKED

    if stage is RunStage.RENDER:
        if state.errors:
            return GraphOutcome.FAILED
        return GraphOutcome.APPLY

    if stage is RunStage.VALIDATE:
        approved = state.metadata.get("approved_for_execution", False)
        return GraphOutcome.APPROVAL_PENDING if approved else GraphOutcome.BLOCKED

    if stage is RunStage.APPROVAL_PENDING:
        operator_approved = state.metadata.get("operator_approved", False)
        return GraphOutcome.APPLY if operator_approved else GraphOutcome.BLOCKED

    if stage is RunStage.EXECUTE:
        if state.errors:
            return GraphOutcome.FAILED
        return GraphOutcome.COMPLETE

    return GraphOutcome.FAILED


def _discovery_edge(state: DiscoveryGraphState) -> GraphOutcome:
    """Return the correct outcome for the current discovery-workflow stage."""
    if state.errors:
        return GraphOutcome.BLOCKED

    stage = state.current_stage
    if stage is RunStage.DISCOVER:
        return GraphOutcome.COMPLETE

    return GraphOutcome.FAILED
