from ..models.common import ArtifactMeta
from ..models.inventory import DeviceInfo, InterfaceInfo, VlanInfo, InventorySnapshot
from ..models.enums import DeviceVendor, SwitchportMode, AllowedVlansMode, InterfaceType, SpanningTreeMode

# ---------------------------------------------------------------------------
# Shared site VLAN table
# Both devices participate in the same L2 domain, so they share the same VLAN
# definitions. Centralising here prevents the two lists drifting out of sync.
# ---------------------------------------------------------------------------
_SITE_VLANS = [
    VlanInfo(name="default",  id=1),
    VlanInfo(name="users",    id=11),
    VlanInfo(name="printers", id=21),
    VlanInfo(name="security", id=31),
]


def get_mock_inventory_snapshot(site: str | None = None, device_name: str | None = None):
    snapshot = get_inventory_for_site(run_id="mock-run", site=site)
    
    results = []
    for device in snapshot.devices:
        if device_name and device.name != device_name:
            continue
        if site and device.site != site:
            continue
        results.append(device.model_dump(mode="json"))
    
    return {
        "source": "mock",
        "count": len(results),
        "results": results,
    }

def get_inventory_for_site(run_id: str, site: str) -> InventorySnapshot:
    devices = [
        # ------------------------------------------------------------------
        # sw1 — Juniper EX2300 access switch
        # Uplinks (mge-0/0/1, mge-0/0/2) are trunks carrying all site VLANs.
        # Edge ports are access-mode, each pinned to a single VLAN.
        # ------------------------------------------------------------------
        DeviceInfo(
            name="sw1",
            vendor=DeviceVendor.JUNIPER,
            model="EX2300",
            role="access-switch",
            site=site,
            management_ip="10.0.0.10",
            platform="mist",
            interfaces=[
                # Trunk uplink toward the firewall — validator supplies
                # native_vlan=1 and allowed_vlans_mode=ALL automatically.
                InterfaceInfo(
                    name="mge-0/0/1",
                    description="uplink to fw1",
                    enabled=True,
                    type=InterfaceType.SWITCHPORT,
                    mode=SwitchportMode.TRUNK,
                    stp=SpanningTreeMode.TRUNK,
                ),
                # Trunk downlink to wireless AP — edge-trunk STP role because
                # the AP is an endpoint, not a bridge.
                InterfaceInfo(
                    name="mge-0/0/2",
                    description="AP",
                    enabled=True,
                    type=InterfaceType.SWITCHPORT,
                    mode=SwitchportMode.TRUNK,
                    stp=SpanningTreeMode.EDGE_TRUNK,
                ),
                InterfaceInfo(
                    name="mge-0/0/5",
                    description="camera",
                    enabled=True,
                    type=InterfaceType.SWITCHPORT,
                    mode=SwitchportMode.ACCESS,
                    stp=SpanningTreeMode.EDGE,
                    access_vlan=31,
                ),
                InterfaceInfo(
                    name="ge-0/0/8",
                    description="printer",
                    enabled=True,
                    type=InterfaceType.SWITCHPORT,
                    mode=SwitchportMode.ACCESS,
                    stp=SpanningTreeMode.EDGE,
                    access_vlan=21,
                ),
                InterfaceInfo(
                    name="ge-0/0/12",
                    description="user-port",
                    enabled=True,
                    type=InterfaceType.SWITCHPORT,
                    mode=SwitchportMode.ACCESS,
                    stp=SpanningTreeMode.EDGE,
                    access_vlan=11,
                ),
            ],
            vlans=_SITE_VLANS,
        ),
        # ------------------------------------------------------------------
        # fw1 — Meraki MX-95 firewall / inter-VLAN router
        # LAN5 is a dedicated management access port (VLAN 1).
        # LAN9 is the trunk toward sw1, carrying all site VLANs.
        # The firewall does not participate in spanning-tree.
        # ------------------------------------------------------------------
        DeviceInfo(
            name="fw1",
            vendor=DeviceVendor.MERAKI,
            model="MX-95",
            role="firewall",
            site=site,
            management_ip="10.0.0.1",
            platform="meraki",
            interfaces=[
                InterfaceInfo(
                    name="LAN5",
                    description="switch management",
                    enabled=True,
                    type=InterfaceType.SWITCHPORT,
                    mode=SwitchportMode.ACCESS,
                    stp=SpanningTreeMode.NONE,
                    access_vlan=1,
                ),
                # Trunk toward sw1 — validator supplies native_vlan=1 and
                # allowed_vlans_mode=ALL automatically.
                InterfaceInfo(
                    name="LAN9",
                    description="uplink to sw1",
                    enabled=True,
                    type=InterfaceType.SWITCHPORT,
                    mode=SwitchportMode.TRUNK,
                    stp=SpanningTreeMode.NONE,
                ),
            ],
            vlans=_SITE_VLANS,
        ),
    ]

    return InventorySnapshot(
        meta=ArtifactMeta(
            run_id=run_id,
            artifact_id="inventory-001",
            created_by="mock_inventory_adapter",
        ),
        devices=devices,
        source_of_truth="mock",
        notes=[f"Mock inventory for site {site}"],
    )

def get_mock_inventory(ctx, site: str):
    run_id = getattr(getattr(ctx, "deps", None), "run_id", "mock-run")
    snapshot = get_inventory_for_site(run_id=run_id, site=site)
    return snapshot.model_dump(mode="json")