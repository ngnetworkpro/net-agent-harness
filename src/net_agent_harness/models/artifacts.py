from pydantic import BaseModel, Field
from .common import ArtifactMeta
from .enums import ValidationStatus


class ConfigSnippet(BaseModel):
    device_name: str
    path_hint: str | None = None
    commands: list[str] = Field(default_factory=list)
    rendered_text: str | None = None


class ConfigRender(BaseModel):
    meta: ArtifactMeta
    summary: str
    snippets: list[ConfigSnippet] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    code: str
    severity: str
    message: str
    device_name: str | None = None
    recommendation: str | None = None


class ValidationReport(BaseModel):
    meta: ArtifactMeta
    overall_status: ValidationStatus
    checks_run: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    approved_for_execution: bool = False
