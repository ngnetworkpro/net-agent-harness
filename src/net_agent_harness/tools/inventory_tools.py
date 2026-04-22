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

    if hasattr(mock_inventory_adapter, "get_inventory_for_site"):
        snapshot = mock_inventory_adapter.get_inventory_for_site(
            run_id=run_id,
            site=site,
        )
        return snapshot.model_dump(mode="json")

    return _mock_inventory_snapshot(site=site)


def _normalize_device(item: dict) -> dict:
    primary = item.get("primary_ip4") or item.get("primary_ip") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "site": (item.get("site") or {}).get("name"),
        "status": (item.get("status") or {}).get("value")
        or (item.get("status") or {}).get("label"),
        "role": (item.get("role") or {}).get("name"),
        "platform": (item.get("platform") or {}).get("name")
        if item.get("platform")
        else None,
        "primary_ip": primary.get("address") if isinstance(primary, dict) else None,
        "source": "netbox",
    }


def _normalize_interface(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": (item.get("type") or {}).get("label")
        if isinstance(item.get("type"), dict)
        else item.get("type"),
        "enabled": item.get("enabled"),
        "mtu": item.get("mtu"),
        "description": item.get("description"),
        "mode": (item.get("mode") or {}).get("value")
        if isinstance(item.get("mode"), dict)
        else item.get("mode"),
        "untagged_vlan": (
            (item.get("untagged_vlan") or {}).get("vid")
            if isinstance(item.get("untagged_vlan"), dict)
            else None
        ),
        "tagged_vlans": [
            v.get("vid") for v in item.get("tagged_vlans", []) if isinstance(v, dict)
        ],
    }


def _normalize_ip(item: dict) -> dict:
    assigned = item.get("assigned_object") or {}
    return {
        "id": item.get("id"),
        "address": item.get("address"),
        "family": (item.get("family") or {}).get("value")
        if isinstance(item.get("family"), dict)
        else item.get("family"),
        "status": (item.get("status") or {}).get("value")
        or (item.get("status") or {}).get("label"),
        "dns_name": item.get("dns_name"),
        "interface": assigned.get("name") if isinstance(assigned, dict) else None,
    }


def lookup_inventory(
    ctx: RunContext[RunContextData],
    site: str | None = None,
    device_name: str | None = None,
) -> dict:
    source = (ctx.deps.inventory_source or "mock").lower()

    if source == "netbox":
        adapter = build_netbox_adapter_from_settings()
        payload = adapter.get_devices(site=site, name=device_name)
        devices = [_normalize_device(item) for item in payload.get("results", [])]
        return {
            "source": "netbox",
            "count": payload.get("count", len(devices)),
            "results": devices,
        }

    return _mock_inventory_snapshot(site=site, device_name=device_name)


def lookup_device_context(
    ctx: RunContext[RunContextData],
    site: str | None = None,
    device_name: str | None = None,
) -> dict:
    source = (ctx.deps.inventory_source or "mock").lower()

    if source != "netbox":
        snapshot = _mock_inventory_snapshot(site=site, device_name=device_name)
        first = snapshot.get("results", [{}])[0] if snapshot.get("results") else {}
        return {
            "source": "mock",
            "device": first,
            "interfaces": [],
            "ip_addresses": [],
        }

    adapter = build_netbox_adapter_from_settings()
    payload = adapter.get_devices(site=site, name=device_name, limit=1)

    if not payload.get("results"):
        return {
            "source": "netbox",
            "device": None,
            "interfaces": [],
            "ip_addresses": [],
        }

    device_raw = payload["results"][0]
    device = _normalize_device(device_raw)
    device_id = device_raw.get("id")

    interfaces_payload = adapter.get_interfaces(device_id=device_id)
    ips_payload = adapter.get_ip_addresses(device_id=device_id)

    return {
        "source": "netbox",
        "device": device,
        "interfaces": [
            _normalize_interface(item)
            for item in interfaces_payload.get("results", [])
        ],
        "ip_addresses": [
            _normalize_ip(item) for item in ips_payload.get("results", [])
        ],
    }