from pydantic import BaseModel, Field
from .common import ArtifactMeta, ScopeRef
from .enums import ChangeRisk, TargetScope, PlanDecisionType
from typing import Any


class ResolvedTarget(BaseModel):
    name: str = Field(description="Concrete device name resolved from inventory")
    site: str | None = Field(default=None, description="Resolved site for the device")
    role: str | None = Field(default=None, description="Resolved device role")
    platform: str | None = Field(default=None, description="Resolved platform")
    primary_ip: str | None = Field(default=None, description="Resolved management IP")


class RequestedChange(BaseModel):
    summary: str = Field(
        description="Short human-readable summary of the requested change, one sentence, not a slug"
    )
    business_reason: str | None = Field(
        default=None,
        description="Why the change is needed; null if not stated"
    )
    requested_by: str | None = Field(
        default=None,
        description="Person or team requesting the change; null if unknown"
    )
    maintenance_window: str | None = Field(
        default=None,
        description="Planned change window if provided; null if unknown"
    )
    intent: str = Field(
        description="The requested network change in plain English. Preserve important details like VLAN IDs, device names, and site names. Do not use slugs, identifiers, or code-like labels."
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints stated in the request. Return an empty list if none are provided."
    )
    desired_state: dict[str, Any] = Field(
        default_factory=dict,
        description="The desired state of the network after the change. This is a dictionary of key-value pairs representing the desired configuration."
    )


class RollbackPlan(BaseModel):
    summary: str = Field(
        description="Short summary of how to reverse the requested change"
    )
    trigger_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions that should trigger rollback"
    )
    rollback_steps: list[str] = Field(
        default_factory=list,
        description="Concrete rollback actions; include at least one step when feasible"
    )


class VlanDiff(BaseModel):
    vlans_to_create: list[int] = Field(
        default_factory=list,
        description="VLAN IDs that must be created on the target device",
    )
    ports_to_update: list[str] = Field(
        default_factory=list,
        description="Interface names whose VLAN configuration must be updated",
    )


class PlanDecision(BaseModel):
    decision: PlanDecisionType = Field(
        description="apply — changes required; no_op — already satisfied; blocked — cannot proceed"
    )
    reason: str = Field(
        description="Human-readable explanation of the decision"
    )
    diff: VlanDiff


class PlannedChange(BaseModel):
    """
    Raw output from the change planner agent.
    resolved_targets here is informational — the orchestration layer
    overwrites it with an authoritative inventory lookup before
    writing the ChangeRequest artifact.
    """
    scope: ScopeRef
    target_scope: TargetScope = Field(
        description="How the change targets infrastructure: a single device, a site-wide fan-out, or ambiguous"
    )
    resolved_targets: list[ResolvedTarget] = Field(
        default_factory=list,
        description="Concrete devices resolved from inventory for rendering and validation"
    )
    clarifications_needed: list[str] = Field(
        default_factory=list,
        description="Questions that must be answered before rendering if targets cannot be resolved safely"
    )
    requested_change: RequestedChange
    risk: ChangeRisk
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    rollback_plan: RollbackPlan
    plan_decision: PlanDecision | None = Field(
        default=None,
        description=(
            "Structured decision produced by evaluate_vlan_intent. "
            "no_op means the intent is already satisfied and no config changes are needed. "
            "apply means changes must be rendered. "
            "blocked means the request cannot proceed safely."
        ),
    )


class ChangeRequest(BaseModel):
    """
    Durable change artifact written after planning is complete.
    resolved_targets is always set by orchestration, never trusted
    from LLM output alone.
    """
    meta: ArtifactMeta
    scope: ScopeRef
    target_scope: TargetScope
    resolved_targets: list[ResolvedTarget] = Field(default_factory=list)
    clarifications_needed: list[str] = Field(default_factory=list)
    requested_change: RequestedChange
    risk: ChangeRisk
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    rollback_plan: RollbackPlan
    plan_decision: PlanDecision | None = Field(
        default=None,
        description="Structured no_op/apply/blocked decision carried through from the planner.",
    )