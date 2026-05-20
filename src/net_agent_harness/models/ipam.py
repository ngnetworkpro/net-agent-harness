from pydantic import BaseModel, ConfigDict, Field

from .common import ArtifactMeta
from .enums import ResourceLifecycleState


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
