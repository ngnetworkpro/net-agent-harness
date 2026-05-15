from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional
from enum import Enum
from .common import ArtifactMeta
from .enums import ValidationStatus, SwitchportMode, AllowedVlansMode, NetworkDomain, RenderBackendType, RenderRole
from .changes import VlanSpec, PortSpec


class ConfigSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_name: str
    backend_type: RenderBackendType | None = None
    render_role: RenderRole | None = None
    path_hint: str | None = None
    api_payload: dict | None = None
    commands: list[str] = Field(default_factory=list)
    rendered_text: str | None = None


class ConfigRenderOutput(BaseModel):
    """LLM-facing output model for the render agent.

    Does not include ArtifactMeta — orchestration wraps this into a full
    ConfigRender after the agent returns.
    """
    summary: str
    snippets: list[ConfigSnippet] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConfigRender(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    summary: str
    snippets: list[ConfigSnippet] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class VlanRenderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent_type: Literal["set_access_vlan", "provision_vlan_trunk"]
    vlans_to_create: list[VlanSpec]
    ports_to_update: list[PortSpec]
    target_device: str
    vlan_name: Optional[str] = None
    mode: Literal["access", "trunk"]


class RenderTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    site: str | None = None
    role: str | None = None
    platform: str | None = None
    primary_ip: str | None = None

class OperationType(str, Enum):
    ENSURE_PRESENT = "ensure_present"
    UPDATE = "update"
    REMOVE = "remove"

class VlanRenderOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: RenderTarget
    vlan_id: int
    operation: OperationType
    vlan_name: str | None = None

class VlanInterfaceRenderOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: RenderTarget
    interface_name: str
    switchport_mode: SwitchportMode | None = None
    access_vlan: int | None = None
    native_vlan: int | None = None
    allowed_vlans: list[int] = Field(default_factory=list)
    allowed_vlans_mode: AllowedVlansMode | None = None

class VlanRenderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vlan_ops: list[VlanRenderOp] = Field(default_factory=list)
    interface_ops: list[VlanInterfaceRenderOp] = Field(default_factory=list)

class RoutingRenderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefixes: list[str] = Field(default_factory=list)
    next_hop: str | None = None

class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: NetworkDomain
    intent_type: str
    payload: VlanRenderPayload | RoutingRenderPayload


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    device_name: str | None = None
    recommendation: str | None = None


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    overall_status: ValidationStatus
    checks_run: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    approved_for_execution: bool = False


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    backend: str
    status: str
    detail: str
    reference: str | None = None

class RenderAcceptanceResult(BaseModel):
    """Result of deterministic render acceptance validation."""
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
