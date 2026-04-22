from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ArtifactMeta(BaseModel):
    run_id: str = Field(..., description="Unique run identifier")
    artifact_id: str = Field(..., description="Unique artifact identifier")
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(..., description="Agent or service name")


class ScopeRef(BaseModel):
    site: str | None = None
    region: str | None = None
    device_names: list[str] = Field(default_factory=list)
    device_roles: list[str] = Field(default_factory=list)
