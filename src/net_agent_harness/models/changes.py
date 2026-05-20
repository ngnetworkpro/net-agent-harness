from pydantic import BaseModel, Field
from .common import ArtifactMeta, ScopeRef
from .enums import ChangeRisk, TargetScope, PlanDecisionType, NetworkDomain, SwitchportMode, DeviceVendor, ResourceLifecycleState
from .resources import ResourceRef, ResourceRelationship
from typing import Any, Union, Literal


class VlanAttributes(BaseModel):
    model_config = {"extra": "forbid"}
    vlan_id: int | None = None
    name: str | None = None

class InterfaceAttributes(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    access_vlan: int | None = None
    native_vlan: int | None = None
    allowed_vlans: list[int] = Field(default_factory=list)

class VlanDesiredStateOperation(BaseModel):
    model_config = {"extra": "forbid"}
    object_type: Literal["vlan"]
    operation: Literal["ensure_present", "ensure_absent"]
    attributes: VlanAttributes = Field(default_factory=VlanAttributes)

class InterfaceDesiredStateOperation(BaseModel):
    model_config = {"extra": "forbid"}
    object_type: Literal["interface"]
    operation: Literal["set_access_vlan", "set_trunk"]
    attributes: InterfaceAttributes = Field(default_factory=InterfaceAttributes)

DesiredStateOperation = Union[VlanDesiredStateOperation, InterfaceDesiredStateOperation]


class VlanDesiredState(BaseModel):
    model_config = {"extra": "forbid"}
    operations: list[DesiredStateOperation] = Field(default_factory=list)


class ResolvedTarget(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(description="Concrete device name resolved from inventory")
    site: str | None = Field(default=None, description="Resolved site for the device")
    role: str | None = Field(default=None, description="Resolved device role")
    platform: str | None = Field(default=None, description="Resolved platform")
    primary_ip: str | None = Field(default=None, description="Resolved management IP")
    vendor: DeviceVendor | None = Field(default=None, description="Resolved device vendor")


class RequestedChange(BaseModel):
    model_config = {"extra": "forbid"}
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
    desired_state: VlanDesiredState | dict[str, Any] = Field(
        default_factory=dict,
        description="The desired state of the network after the change. This is a structured dictionary representing the desired configuration."
    )


class RollbackPlan(BaseModel):
    model_config = {"extra": "forbid"}
    summary: str = Field(
        description="Short summary of how to reverse the requested change"
    )
    trigger_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions that should trigger rollback"
    )
    rollback_steps: list[str] = Field(
        default_factory=list,
        description="Concrete rollback actions; include at least one step when feasible"
    )


class VlanSpec(BaseModel):
    model_config = {"extra": "forbid"}
    id: int = Field(description="VLAN ID", ge=1, le=4094)
    name: str = Field(default="", description="VLAN name, empty if not specified")


class PortSpec(BaseModel):
    model_config = {"extra": "forbid"}
    interface: str = Field(description="Interface name, e.g., 'ge-0/0/1'")
    vlan_id: int = Field(description="VLAN ID to assign", ge=1, le=4094)
    mode: SwitchportMode = Field(description="'access' or 'trunk'")


class VlanChange(BaseModel):
    model_config = {"extra": "forbid"}
    vlans_to_create: list[VlanSpec] = Field(
        default_factory=list,
        description="VLANs that must be created on the target device",
    )
    vlans_to_remove: list[VlanSpec] = Field(
        default_factory=list,
        description="VLANs that must be removed from the target device",
    )
    ports_to_update: list[PortSpec] = Field(
        default_factory=list,
        description="Interfaces whose VLAN configuration must be updated",
    )


class DeviceChange(BaseModel):
    model_config = {"extra": "forbid"}
    device: str = Field(description="Hostname of the target device")
    domain: NetworkDomain = Field(description="Network domain: vlan, acl, routing, etc.")
    changes: VlanChange = Field(description="Typed change payload for the domain")


class VlanDiff(BaseModel):
    model_config = {"extra": "forbid"}
    vlans_to_create: list[int] = Field(
        default_factory=list,
        description="VLAN IDs that must be created on the target device",
    )
    ports_to_update: list[str] = Field(
        default_factory=list,
        description="Interface names whose VLAN configuration must be updated",
    )


class PlanDecision(BaseModel):
    model_config = {"extra": "forbid"}
    decision: PlanDecisionType = Field(
        description="apply — changes required; no_op — already satisfied; blocked — cannot proceed"
    )
    reason: str = Field(
        description="Human-readable explanation of the decision"
    )
    diff: list[DeviceChange] = Field(
        description="List of device-specific changes to apply",
    )


class PlannedChange(BaseModel):
    model_config = {"extra": "forbid"}
    """
    Raw output from the change planner agent.
    resolved_targets here is informational — the orchestration layer
    overwrites it with an authoritative inventory lookup before
    writing the ChangeRequest artifact.
    """
    scope: ScopeRef
    target_scope: TargetScope = Field(
        description="How the change targets infrastructure: a single device, a site-wide fan-out, or ambiguous"
    )
    resolved_targets: list[ResolvedTarget] = Field(
        default_factory=list,
        description="Concrete devices resolved from inventory for rendering and validation"
    )
    target_resources: list[ResourceRef] = Field(
        default_factory=list,
        description="Typed references to resource objects targeted by the request",
    )
    resource_relationships: list[ResourceRelationship] = Field(
        default_factory=list,
        description="Structured relationships between targeted resources",
    )
    clarifications_needed: list[str] = Field(
        default_factory=list,
        description="Questions that must be answered before rendering if targets cannot be resolved safely"
    )
    requested_change: RequestedChange
    risk: ChangeRisk
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    rollback_plan: RollbackPlan
    plan_decision: PlanDecision | None = Field(
        default=None,
        description=(
            "Structured decision produced by evaluate_vlan_intent. "
            "no_op means the intent is already satisfied and no config changes are needed. "
            "apply means changes must be rendered. "
            "blocked means the request cannot proceed safely."
        ),
    )


class ChangeRequestDependency(BaseModel):
    """A structured cross-domain dependency for a change request.

    Used by the dependency resolver to check whether upstream artifacts
    (IPAM allocations, topology plans, device availability) are in the
    required lifecycle state before rendering is allowed.
    """

    model_config = {"extra": "forbid"}

    dependency_type: str = Field(
        description=(
            "Type of dependency: 'ipam_allocation', 'topology_plan', "
            "'device_availability', or 'policy_check'."
        )
    )
    description: str = Field(description="Human-readable description of this dependency")
    artifact_id: str | None = Field(
        default=None,
        description="Artifact ID of the upstream artifact this depends on",
    )
    run_id: str | None = Field(
        default=None,
        description="Run ID that produced the upstream artifact",
    )
    required_lifecycle_state: ResourceLifecycleState | None = Field(
        default=None,
        description="Minimum required lifecycle state; None means any observed state is acceptable",
    )
    current_lifecycle_state: ResourceLifecycleState | None = Field(
        default=None,
        description="Observed current lifecycle state of the upstream artifact",
    )
    blocking: bool = Field(
        default=True,
        description="When True, an unresolved dependency blocks rendering",
    )


class ChangeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    """
    Durable change artifact written after planning is complete.
    resolved_targets is always set by orchestration, never trusted
    from LLM output alone.
    """
    meta: ArtifactMeta
    domain: NetworkDomain
    scope: ScopeRef
    target_scope: TargetScope
    resolved_targets: list[ResolvedTarget] = Field(default_factory=list)
    target_resources: list[ResourceRef] = Field(default_factory=list)
    resource_relationships: list[ResourceRelationship] = Field(default_factory=list)
    clarifications_needed: list[str] = Field(default_factory=list)
    requested_change: RequestedChange
    risk: ChangeRisk
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    cross_domain_dependencies: list[ChangeRequestDependency] = Field(
        default_factory=list,
        description="Structured cross-domain dependencies that must be resolved before rendering",
    )
    rollback_plan: RollbackPlan
    plan_decision: PlanDecision | None = Field(
        default=None,
        description="Structured no_op/apply/blocked decision carried through from the planner.",
    )

