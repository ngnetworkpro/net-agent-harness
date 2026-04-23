from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ArtifactMeta(BaseModel):
    run_id: str = Field(..., description="Unique run identifier")
    artifact_id: str = Field(..., description="Unique artifact identifier")
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(..., description="Agent or service name")


class ScopeRef(BaseModel):
    site: str | None = Field(default=None, description="Site name explicitly mentioned, e.g. HQ")
    region: str | None = Field(default=None, description="Region explicitly mentioned, if any")
    device_names: list[str] = Field(default_factory=list, description="Explicit device names, e.g. sw1")
    device_roles: list[str] = Field(default_factory=list, description="Explicit device roles, e.g. access switch")
    requested_role: str | None = Field(default=None, description="Primary role phrase if the user requests a role-based target")