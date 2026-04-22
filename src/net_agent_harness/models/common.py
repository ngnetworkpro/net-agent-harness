from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ArtifactMeta(BaseModel):
    run_id: str = Field(..., description="Unique run identifier")
    artifact_id: str = Field(..., description="Unique artifact identifier")
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(..., description="Agent or service name")


class ScopeRef(BaseModel):
    site: str = Field(..., description="Site name explicitly mentioned in the request, such as HQ")
    region: str | None = Field(default=None, description="Region name if mentioned; null if not stated")
    device_names: list[str] = Field(default_factory=list, description="Device names explicitly mentioned in the request, such as sw1")
    device_roles: list[str] = Field(default_factory=list, description="Device roles explicitly mentioned in the request or strongly implied, such as access-switch")
