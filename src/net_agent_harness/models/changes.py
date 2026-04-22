from pydantic import BaseModel, Field
from .common import ArtifactMeta, ScopeRef
from .enums import ChangeRisk


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

class RollbackPlan(BaseModel):
    summary: str = Field(
        description="Short summary of how to back out the change"
    )
    trigger_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions that should trigger rollback"
    )
    rollback_steps: list[str] = Field(
        default_factory=list,
        description="Include at least one concrete rollback step when the change affects a switch configuration."
    )


class PlannedChange(BaseModel):
    scope: ScopeRef
    requested_change: RequestedChange
    risk: ChangeRisk
    assumptions: list[str] = Field(
        default_factory=list,
        description="Reasonable assumptions required to plan the change"
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="External prerequisites or dependencies"
    )
    rollback_plan: RollbackPlan | None = None


class ChangeRequest(BaseModel):
    meta: ArtifactMeta
    scope: ScopeRef
    requested_change: RequestedChange
    risk: ChangeRisk
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    rollback_plan: RollbackPlan | None = None