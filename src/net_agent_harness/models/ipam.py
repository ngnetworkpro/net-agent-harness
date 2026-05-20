from pydantic import BaseModel, ConfigDict, Field

from .common import ArtifactMeta
from .enums import PlanDecisionType, ResourceLifecycleState


class IpamPrefix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cidr: str
    site: str | None = None
    vlan_id: int | None = None
    role: str | None = None
    status: str = "active"
    lifecycle_state: ResourceLifecycleState = Field(
        default=ResourceLifecycleState.CURRENT,
        description=(
            "Lifecycle state of this prefix. "
            "Use 'planned' for prefixes reserved before device configuration exists."
        ),
    )


class IpamAddressAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str
    device_name: str
    interface: str | None = None
    dns_name: str | None = None
    status: str = "active"
    lifecycle_state: ResourceLifecycleState = Field(
        default=ResourceLifecycleState.CURRENT,
        description=(
            "Lifecycle state of this address assignment. "
            "Use 'planned' for allocations that are reserved or planned "
            "before the device configuration exists."
        ),
    )


class IpamSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: ArtifactMeta
    source_of_truth: str = "mock"
    prefixes: list[IpamPrefix] = Field(default_factory=list)
    assignments: list[IpamAddressAssignment] = Field(default_factory=list)


class PrefixAllocationPlan(BaseModel):
    """Planned IPAM prefix allocation artifact.

    Produced by the ``plan.ipam`` workflow to propose a prefix allocation
    from a parent block.  No writes are made to any IPAM backend until
    explicit approval gates are added in a later phase.

    Artifact filename: ``prefixallocationplan.json``
    """

    model_config = ConfigDict(extra="forbid")

    meta: ArtifactMeta
    parent_prefix: str = Field(
        description="Parent CIDR block to allocate from, e.g. '10.10.0.0/16'"
    )
    requested_prefix_length: int = Field(
        description="Requested prefix length (CIDR mask bits), e.g. 24 for a /24",
        ge=1,
        le=128,
    )
    proposed_prefix: str | None = Field(
        default=None,
        description="Proposed CIDR allocation, e.g. '10.10.5.0/24'; None when blocked",
    )
    site: str | None = Field(default=None, description="Target site for this allocation")
    purpose: str | None = Field(
        default=None,
        description="Intended use, e.g. 'server', 'management', 'guest'",
    )
    overlap_check_passed: bool = Field(
        default=False,
        description="True when no overlapping prefix was found in the parent block",
    )
    policy_check_passed: bool = Field(
        default=False,
        description="True when the proposed prefix satisfies design-policy constraints",
    )
    decision: PlanDecisionType = Field(
        default=PlanDecisionType.BLOCKED,
        description="apply — allocation is proposed; blocked — cannot proceed safely",
    )
    blocking_reason: str | None = Field(
        default=None,
        description="Human-readable reason when decision is blocked",
    )
    lifecycle_state: ResourceLifecycleState = Field(
        default=ResourceLifecycleState.PLANNED,
        description="Lifecycle state of this allocation; starts at 'planned'",
    )


class IPAssignmentPlan(BaseModel):
    """Planned host IP address assignment artifact.

    Produced alongside a ``PrefixAllocationPlan`` or independently when a
    specific host address must be reserved before device configuration is
    rendered.

    Artifact filename: ``ipassignmentplan.json``
    """

    model_config = ConfigDict(extra="forbid")

    meta: ArtifactMeta
    device_name: str = Field(description="Target device hostname")
    interface: str | None = Field(
        default=None, description="Interface the address will be assigned to, if known"
    )
    parent_prefix: str = Field(
        description="Parent CIDR from which the address is drawn, e.g. '10.10.5.0/24'"
    )
    proposed_address: str | None = Field(
        default=None,
        description="Proposed host address in CIDR notation, e.g. '10.10.5.10/24'; None when blocked",
    )
    decision: PlanDecisionType = Field(
        default=PlanDecisionType.BLOCKED,
        description="apply — assignment is proposed; blocked — cannot proceed safely",
    )
    blocking_reason: str | None = Field(
        default=None,
        description="Human-readable reason when decision is blocked",
    )
    lifecycle_state: ResourceLifecycleState = Field(
        default=ResourceLifecycleState.PLANNED,
        description="Lifecycle state of this assignment; starts at 'planned'",
    )
