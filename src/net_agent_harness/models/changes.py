from pydantic import BaseModel, Field, model_validator
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

class SviAttributes(BaseModel):
    model_config = {"extra": "forbid"}
    vlan_id: int | None = None
    ip_address: str | None = None
    prefix_length: int | None = None

class VlanDesiredStateOperation(BaseModel):
    model_config = {"extra": "forbid"}
    object_type: Literal["vlan"]
    operation: Literal["ensure_present", "ensure_absent"]
    attributes: VlanAttributes = Field(default_factory=VlanAttributes)
    target_device: str | None = Field(default=None, description="Optional single target device name")
    target_devices: list[str] | None = Field(default=None, description="Optional target device names")

class InterfaceDesiredStateOperation(BaseModel):
    model_config = {"extra": "forbid"}
    object_type: Literal["interface"]
    operation: Literal["set_access_vlan", "set_trunk"]
    attributes: InterfaceAttributes = Field(default_factory=InterfaceAttributes)
    target_device: str | None = Field(default=None, description="Optional single target device name")
    target_devices: list[str] | None = Field(default=None, description="Optional target device names")

class SviDesiredStateOperation(BaseModel):
    model_config = {"extra": "forbid"}
    object_type: Literal["svi"]
    operation: Literal["ensure_present", "ensure_absent"]
    attributes: SviAttributes = Field(default_factory=SviAttributes)
    target_device: str | None = Field(default=None, description="Optional single target device name")
    target_devices: list[str] | None = Field(default=None, description="Optional target device names")

DesiredStateOperation = Union[
    VlanDesiredStateOperation,
    InterfaceDesiredStateOperation,
    SviDesiredStateOperation,
]


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


class VlanChangeOperation(BaseModel):
    model_config = {"extra": "forbid"}
    change_type: Literal["vlan"] = "vlan"
    op: Literal["create", "remove"]
    vlan_id: int
    name: str = ""
    status: Literal["apply", "skip", "blocked"] = "apply"
    reason: str | None = None

class SviChangeOperation(BaseModel):
    model_config = {"extra": "forbid"}
    change_type: Literal["svi"] = "svi"
    op: Literal["create", "remove"]
    vlan_id: int
    ip_address: str | None = None
    prefix_length: int | None = None
    interface: str | None = None
    status: Literal["apply", "skip", "blocked"] = "apply"
    reason: str | None = None

class InterfaceChangeOperation(BaseModel):
    model_config = {"extra": "forbid"}
    change_type: Literal["interface"] = "interface"
    op: Literal["set_access_vlan", "set_trunk"]
    interface: str
    vlan_id: int
    status: Literal["apply", "skip", "blocked"] = "apply"
    reason: str | None = None

ChangeOperation = Union[VlanChangeOperation, SviChangeOperation, InterfaceChangeOperation]


class VlanChange(BaseModel):
    model_config = {"extra": "forbid"}
    operations: list[ChangeOperation] = Field(
        default_factory=list,
        description="Typed operations for the target device",
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        
        if "operations" in data:
            return data
            
        operations = []
        # Convert legacy fields
        for v in data.get("vlans_to_create", []):
            v_id = v.get("id") if isinstance(v, dict) else getattr(v, "id", None)
            v_name = v.get("name", "") if isinstance(v, dict) else getattr(v, "name", "")
            operations.append({
                "change_type": "vlan",
                "op": "create",
                "vlan_id": v_id,
                "name": v_name,
                "status": "apply",
            })
        for v in data.get("vlans_to_remove", []):
            v_id = v.get("id") if isinstance(v, dict) else getattr(v, "id", None)
            v_name = v.get("name", "") if isinstance(v, dict) else getattr(v, "name", "")
            operations.append({
                "change_type": "vlan",
                "op": "remove",
                "vlan_id": v_id,
                "name": v_name,
                "status": "apply",
            })
        for p in data.get("ports_to_update", []):
            iface = p.get("interface") if isinstance(p, dict) else getattr(p, "interface", None)
            v_id = p.get("vlan_id") if isinstance(p, dict) else getattr(p, "vlan_id", None)
            mode = p.get("mode") if isinstance(p, dict) else getattr(p, "mode", None)
            op = "set_access_vlan" if mode == "access" else "set_trunk"
            operations.append({
                "change_type": "interface",
                "op": op,
                "interface": iface,
                "vlan_id": v_id,
                "status": "apply",
            })
            
        return {"operations": operations}

    @property
    def vlans_to_create(self) -> list[VlanSpec]:
        return [
            VlanSpec(id=op.vlan_id, name=op.name)
            for op in self.operations
            if isinstance(op, VlanChangeOperation) and op.op == "create" and op.status == "apply"
        ]

    @property
    def vlans_to_remove(self) -> list[VlanSpec]:
        return [
            VlanSpec(id=op.vlan_id, name=op.name)
            for op in self.operations
            if isinstance(op, VlanChangeOperation) and op.op == "remove" and op.status == "apply"
        ]

    @property
    def ports_to_update(self) -> list[PortSpec]:
        ports = []
        for op in self.operations:
            if isinstance(op, InterfaceChangeOperation) and op.status == "apply":
                mode = "access" if op.op == "set_access_vlan" else "trunk"
                ports.append(PortSpec(interface=op.interface, vlan_id=op.vlan_id, mode=mode))
        return ports


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

