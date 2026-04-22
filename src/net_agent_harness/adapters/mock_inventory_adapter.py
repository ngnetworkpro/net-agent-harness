from ..models.common import ArtifactMeta
from ..models.inventory import DeviceInfo, InterfaceInfo, InventorySnapshot
from ..models.enums import DeviceVendor


def get_inventory_for_site(run_id: str, site: str) -> InventorySnapshot:
    device = DeviceInfo(
        name="sw1",
        vendor=DeviceVendor.CISCO,
        model="C9300",
        role="access-switch",
        site=site,
        management_ip="10.0.0.10",
        platform="iosxe",
        interfaces=[
            InterfaceInfo(name="Gig1/0/1", description="uplink", enabled=True),
            InterfaceInfo(name="Gig1/0/24", description="user-port", enabled=True, vlan_ids=[10]),
        ],
    )
    return InventorySnapshot(
        meta=ArtifactMeta(
            run_id=run_id,
            artifact_id="inventory-001",
            created_by="mock_inventory_adapter",
        ),
        devices=[device],
        source_of_truth="mock",
        notes=[f"Mock inventory for site {site}"],
    )
