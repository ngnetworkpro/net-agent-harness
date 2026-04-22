from pydantic_ai import RunContext

from ..adapters import mock_inventory_adapter
from ..adapters.netbox_adapter import build_netbox_adapter_from_settings
from ..orchestration.run_context import RunContextData


def _mock_inventory_snapshot(site: str | None = None, device_name: str | None = None) -> dict:
    if hasattr(mock_inventory_adapter, "get_mock_inventory_snapshot"):
        return mock_inventory_adapter.get_mock_inventory_snapshot(
            site=site,
            device_name=device_name,
        )

    site = site or "HQ"
    snapshot = mock_inventory_adapter.get_inventory_for_site(
        run_id="mock-run",
        site=site,
    )

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


def get_mock_inventory(ctx: RunContext[RunContextData], site: str) -> dict:
    run_id = getattr(getattr(ctx, "deps", None), "run_id", "mock-run")

    