from pydantic import BaseModel, Field
from .common import ArtifactMeta
from .enums import DeviceVendor


class InterfaceInfo(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    ip_addresses: list[str] = Field(default_factory=list)
    vlan_ids: list[int] = Field(default_factory=list)


class DeviceInfo(BaseModel):
    name: str
    vendor: DeviceVendor
    model: str | None = None
    role: str
    site: str
    management_ip: str | None = None
    platform: str | None = None
    interfaces: list[InterfaceInfo] = Field(default_factory=list)


class InventorySnapshot(BaseModel):
    meta: ArtifactMeta
    devices: list[DeviceInfo] = Field(default_factory=list)
    source_of_truth: str = "mock"
    notes: list[str] = Field(default_factory=list)
