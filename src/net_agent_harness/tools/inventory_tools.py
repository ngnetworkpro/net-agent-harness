from pydantic_ai import RunContext

from ..adapters import mock_inventory_adapter
from ..adapters.netbox_adapter import build_netbox_adapter_from_settings
from ..orchestration.run_context import RunContextData
from ..models.changes import ScopeRef, ResolvedTarget

ELIGIBLE_SITE_ROLES = {"access", "access-switch", "switch"}


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


def _normalize_device(item: dict) -> dict:
    primary = item.get("primary_ip4") or item.get("primary_ip") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "site": (item.get("site") or {}).get("name") if isinstance(item.get("site"), dict) else item.get("site"),
        "status": (item.get("status") or {}).get("value")
        if isinstance(item.get("status"), dict)
        else item.get("status"),
        "role": (item.get("role") or {}).get("name")
        if isinstance(item.get("role"), dict)
        else item.get("role"),
        "platform": (item.get("platform") or {}).get("name")
        if isinstance(item.get("platform"), dict)
        else item.get("platform"),
        "primary_ip": primary.get("address") if isinstance(primary, dict) else primary,
        "source": "netbox",
    }


def _normalize_resolved_target(item: dict) -> ResolvedTarget:
    return ResolvedTarget(
        name=item.get("name"),
        site=item.get("site"),
        role=item.get("role"),
        platform=item.get("platform"),
        primary_ip=item.get("primary_ip") or item.get("management_ip"),
    )


def _role_matches(role: str | None, allowed_roles: set[str] | None) -> bool:
    if not allowed_roles:
        return True
    if not role:
        return False
    return role.strip().lower() in {r.lower() for r in allowed_roles}


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


def resolve_targets(
    ctx: RunContext[RunContextData],
    site: str | None = None,
    device_name: str | None = None,
    allowed_roles: list[str] | None = None,
) -> dict:
    inventory = lookup_inventory(ctx, site=site, device_name=device_name)
    return _filter_and_normalize(inventory, site=site, device_name=device_name, allowed_roles=allowed_roles)

def resolve_site_targets(
    ctx: RunContext[RunContextData],
    site: str,
    allowed_roles: list[str] | None = None,
) -> dict:
    return resolve_targets(
        ctx,
        site=site,
        device_name=None,
        allowed_roles=allowed_roles or sorted(ELIGIBLE_SITE_ROLES),
    )


def resolve_device_target(
    ctx: RunContext[RunContextData],
    site: str | None,
    device_name: str,
) -> dict:
    return resolve_targets(
        ctx,
        site=site,
        device_name=device_name,
        allowed_roles=None,
    )


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
        "interfaces": interfaces_payload.get("results", []),
        "ip_addresses": ips_payload.get("results", []),
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


def resolve_device_target_sync(
    site: str | None,
    device_name: str,
    inventory_source: str,
) -> dict:
    """
    Plain Python version of resolve_device_target.
    No RunContext dependency — safe to call from orchestration.
    """
    raw = lookup_inventory_sync(inventory_source, site=site, device_name=device_name)
    return _filter_and_normalize(raw, site=site, device_name=device_name, allowed_roles=None)


def resolve_site_targets_sync(
    site: str,
    inventory_source: str,
    allowed_roles: list[str] | None = None,
) -> dict:
    """
    Plain Python version of resolve_site_targets.
    No RunContext dependency — safe to call from orchestration.
    """
    raw = lookup_inventory_sync(inventory_source, site=site, device_name=None)
    return _filter_and_normalize(
        raw,
        site=site,
        device_name=None,
        allowed_roles=allowed_roles or sorted(ELIGIBLE_SITE_ROLES),
    )


def _filter_and_normalize(
    inventory: dict,
    site: str | None,
    device_name: str | None,
    allowed_roles: list[str] | None,
) -> dict:
    """
    Shared filtering and normalization logic used by both sync and
    RunContext-based resolution paths.
    """
    allowed = set(allowed_roles or [])
    results = []

    for item in inventory.get("results", []):
        if device_name and item.get("name") != device_name:
            continue
        if site and item.get("site") != site:
            continue
        if allowed and not _role_matches(item.get("role"), allowed):
            continue
        results.append(_normalize_resolved_target(item))

    return {
        "source": inventory.get("source"),
        "count": len(results),
        "results": results,
    }

def lookup_inventory_sync(
    inventory_source: str,
    site: str | None = None,
    device_name: str | None = None,
) -> dict:
    """
    Loads inventory without a RunContext.
    Supports the same mock/file/API sources as lookup_inventory.
    """
    if inventory_source == "mock":
        return _mock_inventory_snapshot(site=site, device_name=device_name)

    # TODO: implement file-based inventory resolution
    # TODO: implement netbox-based inventory resolution

    raise ValueError(f"Unsupported inventory_source: {inventory_source!r}")

def resolve_from_scope(
    scope: ScopeRef,
    inventory_source: str,
) -> list[ResolvedTarget]:
    """
    Resolves inventory targets from a planner-produced ScopeRef.
    
    Resolution priority:
    1. Explicit device names — resolve each individually
    2. Site + roles — resolve by site filtered to allowed roles
    3. Site only — resolve all eligible devices at site
    Returns empty list if scope has insufficient information.
    """
    results = []

    # Priority 1: explicit device names
    if scope.device_names:
        for device_name in scope.device_names:
            raw = resolve_device_target_sync(
                site=scope.site,
                device_name=device_name,
                inventory_source=inventory_source,
            )
            results.extend(raw.get("results", []))
        return results

    # Priority 2: site + roles
    if scope.site:
        roles = scope.device_roles or (
            [scope.requested_role] if scope.requested_role else None
        )
        raw = resolve_site_targets_sync(
            site=scope.site,
            inventory_source=inventory_source,
            allowed_roles=roles,
        )
        return raw.get("results", [])

    # TODO: add region-level resolution when inventory supports it
    return []
