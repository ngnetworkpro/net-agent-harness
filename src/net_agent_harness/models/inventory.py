from pydantic import BaseModel, Field
from typing import Optional, List
from .common import ArtifactMeta
from .enums import DeviceVendor, SwitchportMode, AllowedVlansMode, InterfaceType, SpanningTreeMode


class InterfaceInfo(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    ip_addresses: list[str] = Field(default_factory=list)
    vlan_ids: list[int] = Field(default_factory=list)
    type: Optional[InterfaceType] = InterfaceType.SWITCHPORT
    mtu: int | None = 1500
    enabled: bool = True
    mode: Optional[SwitchportMode] = SwitchportMode.ACCESS
    stp: Optional[SpanningTreeMode] = SpanningTreeMode.TRUNK
    access_vlan: Optional[int] = None
    native_vlan: Optional[int] = None
    allowed_vlans_mode: Optional[AllowedVlansMode] = None
    vlan_ids: List[int] = Field(default_factory=list)

class VlanInfo(BaseModel):
    name: str
    id: int

class DeviceInfo(BaseModel):
    name: str
    vendor: DeviceVendor
    model: str | None = None
    role: str
    site: str
    management_ip: str | None = None
    platform: str | None = None
    interfaces: list[InterfaceInfo] = Field(default_factory=list)
    vlans: list[VlanInfo] = Field(default_factory=list)

class InventorySnapshot(BaseModel):
    meta: ArtifactMeta
    devices: list[DeviceInfo] = Field(default_factory=list)
    source_of_truth: str = "mock"
    notes: list[str] = Field(default_factory=list)
