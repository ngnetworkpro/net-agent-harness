"""
Graph state models for multi-step workflow graphs.

WorkflowGraphState and DiscoveryGraphState are lightweight Pydantic models that
track the current position, outcome, and artifact references for a single workflow
run.  They deliberately hold only artifact IDs (not full payloads) so that the
in-memory footprint stays small and all durable data lives in artifact files.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import Capability, RunStage


class GraphOutcome(str, Enum):
    """Outcome of a single graph-edge evaluation.

    ``apply``            — change is approved and ready to render.
    ``no_op``            — desired state is already satisfied; nothing to do.
    ``blocked``          — cannot proceed safely; manual review required.
    ``approval_pending`` — validation passed; awaiting operator approval.
    ``complete``         — workflow reached a terminal success state.
    ``failed``           — workflow reached a terminal failure state.
    """

    APPLY = "apply"
    NO_OP = "no_op"
    BLOCKED = "blocked"
    APPROVAL_PENDING = "approval_pending"
    COMPLETE = "complete"
    FAILED = "failed"


class WorkflowGraphState(BaseModel):
    """Tracks the runtime state of a change workflow graph.

    Each field is intentionally small.  Full artifact payloads are written to
    the artifact store and referenced here by their string artifact IDs.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    capability: Capability
    current_stage: RunStage
    outcome: GraphOutcome | None = None
    # Maps stage name → artifact ID written during that stage.
    artifact_ids: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    # Lightweight key-value store for edge-decision inputs (e.g. plan_decision).
    metadata: dict = Field(default_factory=dict)


class DiscoveryGraphState(BaseModel):
    """Tracks the runtime state of a discovery (ask) workflow graph.

    Discovery graphs are shorter: discover → answer.  Simple direct-answer
    requests bypass this graph layer entirely and do not produce a state object.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    capability: Capability
    current_stage: RunStage
    outcome: GraphOutcome | None = None
    artifact_ids: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
