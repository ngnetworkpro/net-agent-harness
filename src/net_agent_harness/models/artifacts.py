from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional, Protocol
from enum import Enum
from .common import ArtifactMeta, ScopeRef
from .enums import (
    AllowedVlansMode,
    Capability,
    NetworkDomain,
    RenderBackendType,
    RenderRole,
    SwitchportMode,
    ValidationStatus,
)
from .changes import VlanSpec, PortSpec


class ApiRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    body: dict | None = None
    query: dict[str, str] = Field(default_factory=dict)
    vendor_context: dict[str, str] = Field(default_factory=dict)


class ConfigSnippet(BaseModel):
    """A configuration snippet for a target device.
    
    API-primary snippet (render_role=PRIMARY, backend_type=API):
    - api_payload: required typed API request payload
    - rendered_text: required, human-readable preview of the API call
    - path_hint: optional, endpoint or resource path hint for the reviewer
    - commands: must be empty list; CLI data does not belong here

    CLI-fallback snippet (render_role=FALLBACK, backend_type=CLI):
    - commands: required, non-empty list of vendor-specific CLI commands
    - rendered_text: required, human-readable text joining the commands
    - api_payload: must be None; API data does not belong here

    Mixed output (API-capable device):
    A single device should emit one PRIMARY API snippet plus one FALLBACK CLI snippet
    as two separate ConfigSnippet entries in the ConfigRender.snippets list.
    They share device_name.
    """
    model_config = ConfigDict(extra="forbid")
    device_name: str
    backend_type: RenderBackendType | None = None
    render_role: RenderRole | None = None
    path_hint: str | None = None
    api_payload: ApiRequestPayload | None = None
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


class RenderPayload(Protocol):
    def has_ops(self) -> bool:
        """Return True when payload contains at least one renderable operation."""

    def describe_ops(self) -> list[str]:
        """Return human-readable lines describing payload operations."""

    def validate_snippets(self, snippets: list[ConfigSnippet]) -> list[str]:
        """Run domain-specific validation on rendered snippets; return error strings."""
        ...


class VlanRenderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vlan_ops: list[VlanRenderOp] = Field(default_factory=list)
    interface_ops: list[VlanInterfaceRenderOp] = Field(default_factory=list)

    def has_ops(self) -> bool:
        return bool(self.vlan_ops or self.interface_ops)

    def describe_ops(self) -> list[str]:
        payload_parts: list[str] = []

        if self.vlan_ops:
            payload_parts.append("VLAN Operations:")
            for op in self.vlan_ops:
                name_part = f", name={op.vlan_name}" if op.vlan_name is not None else ""
                payload_parts.append(
                    "  - VLAN "
                    + str(op.vlan_id)
                    + name_part
                    + ", operation="
                    + str(op.operation.value)
                    + ", target="
                    + str(op.target.name)
                )

        if self.interface_ops:
            payload_parts.append("Interface Operations:")
            for op in self.interface_ops:
                mode = op.switchport_mode.value if op.switchport_mode else "unknown"
                access_part = f", access_vlan={op.access_vlan}" if op.access_vlan is not None else ""
                payload_parts.append(
                    "  - "
                    + str(op.interface_name)
                    + ": mode="
                    + mode
                    + access_part
                    + ", target="
                    + str(op.target.name)
                )

        return payload_parts

    def validate_snippets(self, snippets: list[ConfigSnippet]) -> list[str]:
        return []


class StaticRouteOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefix: str
    next_hop: str
    operation: OperationType
    target: RenderTarget
    description: Optional[str] = None
    admin_distance: Optional[int] = None


class RoutingRenderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_ops: list[StaticRouteOp] = Field(default_factory=list)

    def has_ops(self) -> bool:
        return bool(self.route_ops)

    def describe_ops(self) -> list[str]:
        payload_parts: list[str] = []
        if self.route_ops:
            payload_parts.append("Route Operations:")
            for op in self.route_ops:
                payload_parts.append(
                    "  - "
                    + op.prefix
                    + " via "
                    + op.next_hop
                    + ": operation="
                    + op.operation.value
                    + ", target="
                    + op.target.name
                )
        return payload_parts

    def validate_snippets(self, snippets: list[ConfigSnippet]) -> list[str]:
        """Verify each API-primary snippet for a route op includes next_hop in api_payload."""
        errors: list[str] = []
        for snippet in snippets:
            is_api_primary = (
                snippet.backend_type is not None
                and snippet.backend_type.value == "api"
                and snippet.render_role is not None
                and snippet.render_role.value == "primary"
            )
            if is_api_primary:
                body = snippet.api_payload.body if snippet.api_payload else None
                if body is None:
                    errors.append(
                        f"API-primary snippet for device '{snippet.device_name}' "
                        f"has no api_payload.body (next_hop is required)."
                    )
                elif "next_hop" not in body:
                    errors.append(
                        f"API-primary snippet for device '{snippet.device_name}' "
                        f"is missing 'next_hop' in api_payload.body."
                    )
        return errors

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


class ValidationCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_name: str
    backend_type: RenderBackendType | None = None
    status: ValidationStatus
    details: str | None = None
    blocking: bool = False


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    overall_status: ValidationStatus
    checks_run: list[str] = Field(default_factory=list)
    check_results: list[ValidationCheckResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    approved_for_execution: bool = False


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    backend: str
    status: str
    detail: str
    reference: str | None = None


class ReadOnlyAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    capability: Capability
    question: str
    answer: str
    data: dict = Field(default_factory=dict)


class QueryFinding(BaseModel):
    """A finding produced by a read-only query or analysis."""
    model_config = ConfigDict(extra="forbid")
    code: str
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    source: str | None = None


class TopologyQueryResult(BaseModel):
    """Typed result of a topology discovery query."""
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    capability: Literal[Capability.TOPOLOGY] = Capability.TOPOLOGY
    question: str
    answer: str
    scope: ScopeRef | None = None
    links: list[dict] = Field(default_factory=list)
    findings: list[QueryFinding] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class IPAMQueryResult(BaseModel):
    """Typed result of an IPAM lookup query."""
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    capability: Literal[Capability.IPAM] = Capability.IPAM
    question: str
    answer: str
    scope: ScopeRef | None = None
    prefix: dict | None = None
    assignment: dict | None = None
    findings: list[QueryFinding] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class InventoryQueryResult(BaseModel):
    """Typed result of an inventory query."""
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    capability: Literal[Capability.TOPOLOGY] = Capability.TOPOLOGY
    question: str
    answer: str
    scope: ScopeRef | None = None
    devices: list[dict] = Field(default_factory=list)
    findings: list[QueryFinding] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AnswerArtifact(BaseModel):
    """Typed, versionable artifact for direct-answer (discovery) capabilities.

    Intended as the durable persisted form of a read-only answer.
    The `data` field carries the raw structured payload from the underlying tool;
    typed subclasses (TopologyQueryResult, IPAMQueryResult, etc.) carry richer schemas.
    """
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    capability: Capability
    question: str
    answer: str
    scope: ScopeRef | None = None
    findings: list[QueryFinding] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    data: dict = Field(default_factory=dict)


class IncidentSummary(BaseModel):
    """Typed artifact produced by incident triage and review workflows."""
    model_config = ConfigDict(extra="forbid")
    meta: ArtifactMeta
    capability: Literal[Capability.INCIDENT] = Capability.INCIDENT
    title: str
    description: str
    scope: ScopeRef | None = None
    affected_devices: list[str] = Field(default_factory=list)
    findings: list[QueryFinding] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    recommended_actions: list[str] = Field(default_factory=list)


class RenderAcceptanceResult(BaseModel):
    """Result of deterministic render acceptance validation."""
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
