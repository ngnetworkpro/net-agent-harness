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
    def _apply_mode_semantics(self) -> "InterfaceInfo":
        """Enforce the field contract implied by switchport mode.

        Access ports
        ------------
        - ``access_vlan`` is required — an access port with no VLAN assignment
          is not a valid configuration.
        - ``native_vlan``, ``allowed_vlans_mode``, and ``vlan_ids`` are trunk
          concepts and are silently cleared so serialised output stays clean.

        Trunk ports
        -----------
        - ``native_vlan`` defaults to 1 (IEEE 802.1Q default) when omitted;
          real switches behave the same way, so we mirror that rather than
          forcing callers to spell it out every time.
        - ``allowed_vlans_mode`` defaults to ``ALL`` when omitted — the most
          permissive trunk posture and the common vendor default.
        - ``vlan_ids`` must be non-empty when ``allowed_vlans_mode`` is ``LIST``;
          an explicit list with no entries is meaningless and caught here.
        - ``access_vlan`` is a layer-2 access concept and is cleared.
        """
        if self.mode == SwitchportMode.ACCESS:
            if self.access_vlan is None:
                raise ValueError(
                    f"Interface '{self.name}': access_vlan is required for ACCESS mode ports."
                )
            # Trunk fields have no meaning on an access port — clear them so
            # downstream consumers don't have to second-guess which fields apply.
            self.native_vlan = None
            self.allowed_vlans_mode = None
            self.vlan_ids = []

        elif self.mode == SwitchportMode.TRUNK:
            # access_vlan is an access-port concept; clear it on trunks.
            self.access_vlan = None

            # Apply 802.1Q default native VLAN when the caller omitted it.
            if self.native_vlan is None:
                self.native_vlan = _TRUNK_DEFAULT_NATIVE_VLAN

            # Default to the most permissive posture when allowed_vlans_mode
            # was not specified — mirrors common vendor behaviour.
            if self.allowed_vlans_mode is None:
                self.allowed_vlans_mode = AllowedVlansMode.ALL

            # When the caller explicitly requested a VLAN list, that list must
            # contain at least one entry — an empty explicit list is a config
            # error (distinct from the intentional [] used with ALL/NONE).
            if self.allowed_vlans_mode == AllowedVlansMode.LIST and not self.vlan_ids:
                raise ValueError(
                    f"Interface '{self.name}': vlan_ids must be non-empty when "
                    "allowed_vlans_mode is LIST."
                )

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
