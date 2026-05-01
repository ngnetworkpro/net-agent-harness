from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from .common import ArtifactMeta
from .enums import DeviceVendor, SwitchportMode, AllowedVlansMode, InterfaceType, SpanningTreeMode

_TRUNK_DEFAULT_NATIVE_VLAN = 1


class InterfaceInfo(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    ip_addresses: list[str] = Field(default_factory=list)
    vlan_ids: list[int] = Field(default_factory=list)
    type: Optional[InterfaceType] = InterfaceType.SWITCHPORT
    mtu: int | None = 1500
    mode: Optional[SwitchportMode] = SwitchportMode.ACCESS
    stp: Optional[SpanningTreeMode] = SpanningTreeMode.TRUNK
    access_vlan: Optional[int] = None
    native_vlan: Optional[int] = None
    allowed_vlans_mode: Optional[AllowedVlansMode] = None

    @model_validator(mode="after")
    def _default_trunk_native_vlan(self) -> "InterfaceInfo":
        """Apply the 802.1Q default native VLAN (1) to trunk interfaces.

        native_vlan is left as None for non-trunk ports so consumers can
        distinguish "not applicable" from "explicitly unset".  For trunks,
        omitting native_vlan in source data is normal — the switch uses VLAN 1
        unless told otherwise — so we mirror that here rather than forcing
        callers to always spell it out.
        """
        if self.mode == SwitchportMode.TRUNK and self.native_vlan is None:
            self.native_vlan = _TRUNK_DEFAULT_NATIVE_VLAN
        return self

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
