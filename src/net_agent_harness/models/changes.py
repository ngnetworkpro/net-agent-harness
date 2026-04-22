from pydantic import BaseModel, Field
from .common import ArtifactMeta, ScopeRef
from .enums import ChangeRisk


class RequestedChange(BaseModel):
    summary: str
    business_reason: str | None = None
    requested_by: str
    maintenance_window: str | None = None
    intent: str = Field(..., description="Desired network change in plain English")
    constraints: list[str] = Field(default_factory=list)


class RollbackPlan(BaseModel):
    summary: str
    trigger_conditions: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)


class ChangeRequest(BaseModel):
    meta: ArtifactMeta
    scope: ScopeRef
    requested_change: RequestedChange
    risk: ChangeRisk
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    rollback_plan: RollbackPlan | None = None
