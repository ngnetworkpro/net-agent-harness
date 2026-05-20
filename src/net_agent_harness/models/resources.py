from typing import Annotated, Literal

from pydantic import BaseModel, Field


class SiteResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["site"] = "site"
    site_name: str = Field(description="Site name, e.g. HQ")


class DeviceResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["device"] = "device"
    device_name: str = Field(description="Device hostname, e.g. sw1")
    site_name: str | None = Field(default=None, description="Resolved site for the device")


class InterfaceResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["interface"] = "interface"
    device_name: str = Field(description="Parent device hostname for this interface")
    interface_name: str = Field(description="Interface name, e.g. ge-0/0/1")
    site_name: str | None = Field(default=None, description="Site name if known")


class VlanResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["vlan"] = "vlan"
    vlan_id: int = Field(ge=1, le=4094, description="VLAN ID")
    site_name: str | None = Field(default=None, description="Site scope if known")
    device_name: str | None = Field(default=None, description="Device scope if known")


class VrfResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["vrf"] = "vrf"
    vrf_name: str = Field(description="VRF name")
    site_name: str | None = Field(default=None, description="Site scope if known")
    device_name: str | None = Field(default=None, description="Device scope if known")


class SubnetResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["subnet"] = "subnet"
    cidr: str = Field(description="Subnet CIDR, e.g. 10.10.20.0/24")
    vrf_name: str | None = Field(default=None, description="VRF context if known")
    site_name: str | None = Field(default=None, description="Site scope if known")


class PrefixResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["prefix"] = "prefix"
    prefix: str = Field(description="IP prefix expression")
    vrf_name: str | None = Field(default=None, description="VRF context if known")
    site_name: str | None = Field(default=None, description="Site scope if known")


class IpAssignmentResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["ip_assignment"] = "ip_assignment"
    ip_address: str = Field(description="Assigned host IP")
    interface_name: str | None = Field(default=None, description="Interface if known")
    device_name: str | None = Field(default=None, description="Device if known")
    site_name: str | None = Field(default=None, description="Site if known")


class TopologyLinkResourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    resource_type: Literal["topology_link"] = "topology_link"
    endpoint_a_device: str = Field(description="First endpoint device")
    endpoint_a_interface: str | None = Field(default=None, description="First endpoint interface")
    endpoint_b_device: str = Field(description="Second endpoint device")
    endpoint_b_interface: str | None = Field(default=None, description="Second endpoint interface")
    site_name: str | None = Field(default=None, description="Site context if known")


ResourceRef = Annotated[
    SiteResourceRef
    | DeviceResourceRef
    | InterfaceResourceRef
    | VlanResourceRef
    | VrfResourceRef
    | SubnetResourceRef
    | PrefixResourceRef
    | IpAssignmentResourceRef
    | TopologyLinkResourceRef,
    Field(discriminator="resource_type"),
]


class SiteToDeviceRelationship(BaseModel):
    model_config = {"extra": "forbid"}
    relationship_type: Literal["site_to_device"] = "site_to_device"
    site: SiteResourceRef
    device: DeviceResourceRef


class InterfaceToSubnetRelationship(BaseModel):
    model_config = {"extra": "forbid"}
    relationship_type: Literal["interface_to_subnet"] = "interface_to_subnet"
    interface: InterfaceResourceRef
    subnet: SubnetResourceRef


class DeviceToTopologyLinkRelationship(BaseModel):
    model_config = {"extra": "forbid"}
    relationship_type: Literal["device_to_topology_link"] = "device_to_topology_link"
    device: DeviceResourceRef
    topology_link: TopologyLinkResourceRef


ResourceRelationship = Annotated[
    SiteToDeviceRelationship
    | InterfaceToSubnetRelationship
    | DeviceToTopologyLinkRelationship,
    Field(discriminator="relationship_type"),
]
