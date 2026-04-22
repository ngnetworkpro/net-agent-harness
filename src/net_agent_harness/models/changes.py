from pydantic import BaseModel, Field
from .common import ArtifactMeta, ScopeRef
from .enums import ChangeRisk


class RequestedChange(BaseModel):
    summary: str = Field(description="Short machine-friendly summary of the requested change")
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
        ...,
        description="Desired network change in plain English, grounded in the user request"
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints or guardrails from the request"
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
        description="Ordered rollback actions"
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