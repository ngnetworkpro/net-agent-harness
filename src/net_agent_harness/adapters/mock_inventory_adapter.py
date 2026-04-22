from ..models.common import ArtifactMeta
from ..models.inventory import DeviceInfo, InterfaceInfo, InventorySnapshot
from ..models.enums import DeviceVendor


def get_inventory_for_site(run_id: str, site: str) -> InventorySnapshot:
    device = DeviceInfo(
        name="sw1",
        vendor=DeviceVendor.JUNIPER,
        model="EX2300",
        role="access-switch",
        site=site,
        management_ip="10.0.0.10",
        platform="mist",
        interfaces=[
            InterfaceInfo(name="Gig1/0/1", description="uplink", enabled=True),
            InterfaceInfo(
                name="Gig1/0/24",
                description="user-port",
                enabled=True,
                vlan_ids=[10],
            ),
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


def get_mock_inventory_snapshot(site: str | None = None, device_name: str | None = None) -> dict:
    site = site or "HQ"
    snapshot = get_inventory_for_site(run_id="mock-run", site=site)

    results = []
    for device in snapshot.devices:
        if device_name and device.name != device_name:
            continue
        results.append(
            {
                "name": device.name,
                "site": device.site,
                "role": device.role,
                "platform": device.platform,
                "primary_ip": device.management_ip,
                "source": "mock",
            }
        )

    return {
        "source": "mock",
        "count": len(results),
        "results": results,
    }


def get_mock_inventory(ctx, site: str):
    run_id = getattr(getattr(ctx, "deps", None), "run_id", "mock-run")
    snapshot = get_inventory_for_site(run_id=run_id, site=site)
    return snapshot.model_dump(mode="json")