from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum
from .common import ArtifactMeta
from .enums import ValidationStatus, SwitchportMode, AllowedVlansMode, NetworkDomain
from .changes import VlanSpec, PortSpec


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


class VlanRenderInput(BaseModel):
    intent_type: Literal["set_access_vlan", "provision_vlan_trunk"]
    vlans_to_create: list[VlanSpec]
    ports_to_update: list[PortSpec]
    target_device: str
    vlan_name: Optional[str] = None
    mode: Literal["access", "trunk"]


class RenderTarget(BaseModel):
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
    target: RenderTarget
    vlan_id: int
    operation: OperationType
    vlan_name: str | None = None

class VlanInterfaceRenderOp(BaseModel):
    target: RenderTarget
    interface_name: str
    switchport_mode: SwitchportMode | None = None
    access_vlan: int | None = None
    native_vlan: int | None = None
    allowed_vlans: list[int] = Field(default_factory=list)
    allowed_vlans_mode: AllowedVlansMode | None = None

class VlanRenderPayload(BaseModel):
    vlan_ops: list[VlanRenderOp] = Field(default_factory=list)
    interface_ops: list[VlanInterfaceRenderOp] = Field(default_factory=list)

class RoutingRenderPayload(BaseModel):
    prefixes: list[str] = Field(default_factory=list)
    next_hop: str | None = None

class RenderRequest(BaseModel):
    domain: NetworkDomain
    intent_type: str
    payload: VlanRenderPayload | RoutingRenderPayload


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
