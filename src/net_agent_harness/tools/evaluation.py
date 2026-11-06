from collections.abc import Callable
import ipaddress
from typing import Any

from ..models.artifacts import OperationType, RenderTarget, StaticRouteOp

from ..models.changes import (
    ChangeOperation,
    DeviceChange,
    InterfaceChangeOperation,
    PlanDecision,
    SviChangeOperation,
    VlanChange,
    VlanChangeOperation,
    VlanSpec,
)
from ..models.enums import DeviceVendor, NetworkDomain, PlanDecisionType
from ..models.inventory import DeviceInfo, InterfaceInfo
from ..orchestration.platform_constraints import validate_platform_constraints
from ..tools.vlan_state import compute_vlan_diff, vlan_exists


# Any: heterogeneous desired_state attribute value
def _is_valid_vlan_id(vlan_id: Any) -> bool:
    return isinstance(vlan_id, int) and not isinstance(vlan_id, bool) and 1 <= vlan_id <= 4094


def _blocked(reason: str, diff: list[DeviceChange] | None = None) -> PlanDecision:
    return PlanDecision(
        decision=PlanDecisionType.BLOCKED,
        reason=reason,
        diff=diff or [],
    )


def _no_op(reason: str) -> PlanDecision:
    return PlanDecision(
        decision=PlanDecisionType.NO_OP,
        reason=reason,
        diff=[],
    )


def _apply(reason: str, diff: list[DeviceChange]) -> PlanDecision:
    return PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason=reason,
        diff=diff,
    )


def get_svi_interface_name(vendor: DeviceVendor | str | None, vlan_id: int) -> str:
    vendor_str = str(vendor).lower() if vendor else ""
    if "juniper" in vendor_str or "mist" in vendor_str:
        return f"irb.{vlan_id}"
    elif "cisco" in vendor_str or "ios" in vendor_str:
        return f"Vlan{vlan_id}"
    else:
        return f"vlan.{vlan_id}"


def device_supports_svi(device: DeviceInfo) -> bool:
    role = device.role.lower()
    vendor_str = str(device.vendor).lower()
    if "firewall" in role:
        return "meraki" in vendor_str or bool(device.platform and "meraki" in device.platform.lower())
    return True


def get_existing_svi_interface(device: DeviceInfo, vlan_id: int) -> InterfaceInfo | None:
    names_to_check = {
        f"irb.{vlan_id}",
        f"vlan.{vlan_id}",
        f"vlan{vlan_id}",
        f"vlan {vlan_id}",
    }
    for iface in device.interfaces:
        if iface.name in names_to_check or iface.name.lower() in {n.lower() for n in names_to_check}:
            return iface
    return None


def _load_device_from_inventory(
    run_id: str,
    site: str,
    device_name: str,
    inventory_source: str,
) -> DeviceInfo | None:
    from ..models.inventory import DeviceInfo
    from .inventory_tools import lookup_device_context_sync

    inventory_data = lookup_device_context_sync(
        inventory_source=inventory_source,
        site=site,
        device_name=device_name
    )

    device_data = inventory_data.get("device")
    if not device_data:
        return None

    if inventory_source == "netbox":
        device_data = {
            **device_data,
            "interfaces": inventory_data.get("interfaces", []),
            "vlans": [],
        }

    return DeviceInfo.model_validate(device_data)


def normalize_vlan_diff(vlans: list[VlanSpec]) -> list[VlanSpec]:
    """Deduplicate VlanSpec entries by VLAN ID.

    When multiple entries share the same VLAN ID:
    - prefer the entry with a non-empty name
    - discard empty-name duplicates
    - if all entries for a given ID have empty names, keep exactly one

    Returns a deterministic list ordered by VLAN ID.
    """
    best: dict[int, VlanSpec] = {}
    for v in vlans:
        existing = best.get(v.id)
        if existing is None:
            best[v.id] = v
        elif not existing.name and v.name:
            # Replace empty-name entry with one that has a real name
            best[v.id] = v
        # else: keep existing (already has a name, or both are empty)
    return sorted(best.values(), key=lambda v: v.id)


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _operation_status_priority(op: ChangeOperation) -> int:
    status_priority = {"apply": 3, "blocked": 2, "skip": 1}
    return status_priority.get(op.status, 0)


def _operation_completeness(op: ChangeOperation) -> int:
    if isinstance(op, VlanChangeOperation):
        if not op.name:
            return 0
        if op.name == str(op.vlan_id):
            return 1
        return 2
    candidates = [
        getattr(op, "name", None),
        getattr(op, "interface", None),
        getattr(op, "ip_address", None),
        getattr(op, "prefix_length", None),
        getattr(op, "native_vlan", None),
        tuple(getattr(op, "allowed_vlans", ()) or ()),
    ]
    return sum(1 for value in candidates if value not in (None, "", ()))


def _operation_identity_key(op: ChangeOperation) -> tuple[Any, ...]:
    if isinstance(op, VlanChangeOperation):
        return ("vlan", op.op, op.vlan_id)
    if isinstance(op, SviChangeOperation):
        return ("svi", op.op, op.vlan_id, op.interface, op.ip_address, op.prefix_length)
    if isinstance(op, InterfaceChangeOperation):
        return (
            "interface",
            op.op,
            op.interface,
            op.vlan_id,
            op.native_vlan,
            tuple(op.allowed_vlans),
        )
    return (
        op.change_type,
        op.op,
        getattr(op, "vlan_id", None),
        getattr(op, "interface", None),
    )


def _operation_sort_key(op: ChangeOperation) -> tuple[Any, ...]:
    change_type_priority = {"vlan": 0, "svi": 1, "interface": 2}
    return (
        change_type_priority.get(op.change_type, 99),
        getattr(op, "vlan_id", 0),
        getattr(op, "interface", "") or "",
        op.op,
        -_operation_status_priority(op),
    )


def _prefer_operation(existing: ChangeOperation, candidate: ChangeOperation) -> ChangeOperation:
    existing_rank = (_operation_status_priority(existing), _operation_completeness(existing))
    candidate_rank = (_operation_status_priority(candidate), _operation_completeness(candidate))
    if candidate_rank > existing_rank:
        return candidate
    return existing


def _merge_device_changes(all_changes: list[DeviceChange]) -> list[DeviceChange]:
    if not all_changes:
        return []

    device_name = all_changes[0].device
    domain = all_changes[0].domain
    
    merged_ops: list[ChangeOperation] = []
    for dc in all_changes:
        merged_ops.extend(dc.changes.operations)

    deduped: dict[tuple[Any, ...], ChangeOperation] = {}
    for op in merged_ops:
        key = _operation_identity_key(op)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = op
        else:
            deduped[key] = _prefer_operation(existing, op)

    sorted_ops = sorted(deduped.values(), key=_operation_sort_key)

    return [DeviceChange(
        device=device_name,
        domain=domain,
        changes=VlanChange(operations=sorted_ops),
    )]


def _op_matches_device(op: dict[str, Any] | Any, device_name: str) -> bool:
    target_device = _get_value(op, "target_device")
    target_devices = _get_value(op, "target_devices")
    
    if target_device is not None and target_device != device_name:
        return False
    if target_devices is not None:
        if isinstance(target_devices, (list, tuple, set)):
            return device_name in target_devices
        return False
        
    return True


# Any: heterogeneous desired_state payload
def _evaluate_vlan_operations(
    run_id: str,
    site: str,
    device_name: str,
    desired_state: dict[str, Any],
    inventory_source: str,
) -> PlanDecision:
    device = _load_device_from_inventory(run_id, site=site, device_name=device_name, inventory_source=inventory_source)
    if device is None:
        return _blocked(
            f"Device '{device_name}' was not found in the inventory snapshot for site '{site}. "
            "Verify the device name and site."
        )
    if inventory_source.lower() == "netbox" and not device.vlans:
        return _blocked(
            f"Current VLAN state for '{device_name}' is unavailable from NetBox inventory data."
        )

    operations = desired_state.get("operations", [])
    if not operations:
        return _blocked("desired_state.operations is required for VLAN operations.")

    all_device_changes: list[DeviceChange] = []
    reason_parts: list[str] = []

    vlan_ops: list[Any] = []
    interface_ops: list[Any] = []
    svi_ops: list[Any] = []
    for op in operations:
        if not _op_matches_device(op, device_name):
            continue
        object_type = _get_value(op, "object_type")
        if object_type == "vlan":
            vlan_ops.append(op)
        elif object_type == "interface":
            interface_ops.append(op)
        elif object_type == "svi":
            svi_ops.append(op)

    for vlan_op in vlan_ops:
        operation = _get_value(vlan_op, "operation")
        attrs = _get_value(vlan_op, "attributes", {})
        vlan_id = _get_value(attrs, "vlan_id")
        vlan_name = _get_value(attrs, "name") or ""

        if vlan_id is not None and not _is_valid_vlan_id(vlan_id):
            return _blocked(f"Invalid vlan_id '{vlan_id}'; must be between 1 and 4094.")

        if operation == "ensure_present":
            if vlan_id is None:
                return _blocked("vlan_id is required for vlan ensure_present operation.")
            if not vlan_name:
                vlan_name = str(vlan_id)
            if vlan_exists(device, vlan_id):
                # VLAN already present — emit explicit skip
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            VlanChangeOperation(
                                change_type="vlan",
                                op="create",
                                vlan_id=vlan_id,
                                name=vlan_name,
                                status="skip",
                                reason=f"VLAN {vlan_id} already exists on {device_name}.",
                            )
                        ]
                    ),
                ))
            else:
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            VlanChangeOperation(
                                change_type="vlan",
                                op="create",
                                vlan_id=vlan_id,
                                name=vlan_name,
                                status="apply",
                                reason=f"VLAN {vlan_id} does not exist on {device_name}.",
                            )
                        ]
                    ),
                ))
                reason_parts.append(f"VLAN {vlan_id} must be created on {device_name}")
        elif operation == "ensure_absent":
            if vlan_id is None:
                return _blocked("vlan_id is required for vlan ensure_absent operation.")
            if vlan_exists(device, vlan_id):
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            VlanChangeOperation(
                                change_type="vlan",
                                op="remove",
                                vlan_id=vlan_id,
                                name=vlan_name,
                                status="apply",
                                reason=f"VLAN {vlan_id} exists on {device_name} and must be removed.",
                            )
                        ]
                    ),
                ))
                reason_parts.append(f"VLAN {vlan_id} must be deleted from {device_name}")
            else:
                # VLAN already absent — emit explicit skip
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            VlanChangeOperation(
                                change_type="vlan",
                                op="remove",
                                vlan_id=vlan_id,
                                name=vlan_name,
                                status="skip",
                                reason=f"VLAN {vlan_id} does not exist on {device_name}.",
                            )
                        ]
                    ),
                ))
        else:
            return _blocked(f"Unsupported vlan operation '{operation}'.")

    known_interfaces = {i.name for i in device.interfaces}

    for iface_op in interface_ops:
        operation = _get_value(iface_op, "operation")
        attrs = _get_value(iface_op, "attributes", {})
        iface_name = _get_value(attrs, "name")
        access_vlan = _get_value(attrs, "access_vlan")
        native_vlan = _get_value(attrs, "native_vlan")
        allowed_vlans = list(_get_value(attrs, "allowed_vlans", []) or [])

        if iface_name is None:
            return _blocked("interface name is required for interface operations.")
        if iface_name not in known_interfaces:
            return _blocked(
                f"Interface '{iface_name}' was not found on device '{device_name}'."
            )
        if access_vlan is not None and not _is_valid_vlan_id(access_vlan):
            return _blocked(
                f"Invalid access_vlan '{access_vlan}'; must be between 1 and 4094."
            )
        if native_vlan is not None and not _is_valid_vlan_id(native_vlan):
            return _blocked(
                f"Invalid native_vlan '{native_vlan}'; must be between 1 and 4094."
            )
        for vid in allowed_vlans:
            if not _is_valid_vlan_id(vid):
                return _blocked(
                    f"Invalid allowed VLAN ID '{vid}'; must be between 1 and 4094."
                )

        if operation == "set_access_vlan":
            if access_vlan is None:
                return _blocked("access_vlan is required for set_access_vlan operation.")
            device_changes = compute_vlan_diff(
                intent={
                    "vlan_id": access_vlan,
                    "vlan_name": "",
                    "interfaces": [{
                        "name": iface_name,
                        "switchport_mode": "access",
                        "access_vlan": access_vlan,
                    }],
                },
                current_state=device,
            )
            changes = device_changes[0].changes
            if changes.ports_to_update:
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            InterfaceChangeOperation(
                                change_type="interface",
                                op="set_access_vlan",
                                interface=iface_name,
                                vlan_id=access_vlan,
                                status="apply",
                                reason=(
                                    f"Interface {iface_name} is not in access VLAN"
                                    f" {access_vlan} on {device_name}."
                                ),
                            )
                        ]
                    ),
                ))
                reason_parts.append(
                    f"Interface {iface_name} requires access VLAN {access_vlan}"
                    f" update on {device_name}"
                )
            else:
                # Interface already correct — emit explicit skip
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            InterfaceChangeOperation(
                                change_type="interface",
                                op="set_access_vlan",
                                interface=iface_name,
                                vlan_id=access_vlan,
                                status="skip",
                                reason=(
                                    f"Interface {iface_name} is already in access"
                                    f" VLAN {access_vlan} on {device_name}."
                                ),
                            )
                        ]
                    ),
                ))
        elif operation in ("set_trunk", "update_trunk_allowed_vlans", "set_native_vlan"):
            if operation == "set_native_vlan" and native_vlan is None:
                return _blocked("native_vlan is required for set_native_vlan operation.")
            if (
                operation == "update_trunk_allowed_vlans"
                and not allowed_vlans
                and access_vlan is None
            ):
                return _blocked(
                    "allowed_vlans or access_vlan is required for update_trunk_allowed_vlans operation."
                )

            effective_vlan_id = (
                access_vlan
                or (allowed_vlans[0] if allowed_vlans else None)
                or (native_vlan if native_vlan is not None else 1)
            )
            device_changes = compute_vlan_diff(
                intent={
                    "vlan_id": effective_vlan_id,
                    "vlan_name": "",
                    "interfaces": [{
                        "name": iface_name,
                        "switchport_mode": "trunk",
                        "access_vlan": access_vlan,
                        "native_vlan": native_vlan,
                        "allowed_vlans": allowed_vlans,
                        "check_default_vlan": access_vlan is not None,
                    }],
                },
                current_state=device,
            )
            changes = device_changes[0].changes
            if changes.ports_to_update:
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            InterfaceChangeOperation(
                                change_type="interface",
                                op="set_trunk",
                                interface=iface_name,
                                vlan_id=effective_vlan_id,
                                native_vlan=native_vlan,
                                allowed_vlans=list(allowed_vlans),
                                status="apply",
                                reason=(
                                    f"Interface {iface_name} requires trunk"
                                    f" update on {device_name}."
                                ),
                            )
                        ]
                    ),
                ))
                reason_parts.append(
                    f"Interface {iface_name} requires trunk update on {device_name}"
                )
            else:
                # Trunk already correct — emit explicit skip
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            InterfaceChangeOperation(
                                change_type="interface",
                                op="set_trunk",
                                interface=iface_name,
                                vlan_id=effective_vlan_id,
                                native_vlan=native_vlan,
                                allowed_vlans=list(allowed_vlans),
                                status="skip",
                                reason=(
                                    f"Interface {iface_name} trunk is already correctly"
                                    f" configured on {device_name}."
                                ),
                            )
                        ]
                    ),
                ))
        else:
            return _blocked(f"Unsupported interface operation '{operation}'.")

    for svi_op in svi_ops:
        operation = _get_value(svi_op, "operation")
        attrs = _get_value(svi_op, "attributes", {})
        vlan_id = _get_value(attrs, "vlan_id")
        ip_address = _get_value(attrs, "ip_address")
        prefix_length = _get_value(attrs, "prefix_length")

        if vlan_id is None:
            return _blocked("vlan_id is required for svi operations.")
        if not _is_valid_vlan_id(vlan_id):
            return _blocked(f"Invalid vlan_id '{vlan_id}'; must be between 1 and 4094.")

        if operation == "ensure_present":
            if not device_supports_svi(device):
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            SviChangeOperation(
                                change_type="svi",
                                op="create",
                                vlan_id=vlan_id,
                                ip_address=ip_address,
                                prefix_length=prefix_length,
                                status="blocked",
                                reason=f"SVI configuration is not supported on {device.role} devices (device {device_name}).",
                            )
                        ]
                    )
                ))
                reason_parts.append(f"SVI configuration is not supported on {device_name}")
                continue

            existing_iface = get_existing_svi_interface(device, vlan_id)
            if existing_iface:
                target_ip = f"{ip_address}/{prefix_length}" if ip_address and prefix_length else None
                if target_ip and target_ip in existing_iface.ip_addresses:
                    all_device_changes.append(DeviceChange(
                        device=device_name,
                        domain=NetworkDomain.VLAN,
                        changes=VlanChange(
                            operations=[
                                SviChangeOperation(
                                    change_type="svi",
                                    op="create",
                                    vlan_id=vlan_id,
                                    ip_address=ip_address,
                                    prefix_length=prefix_length,
                                    interface=existing_iface.name,
                                    status="skip",
                                    reason=f"SVI is already configured on interface {existing_iface.name}.",
                                )
                            ]
                        )
                    ))
                else:
                    iface_name = existing_iface.name
                    all_device_changes.append(DeviceChange(
                        device=device_name,
                        domain=NetworkDomain.VLAN,
                        changes=VlanChange(
                            operations=[
                                SviChangeOperation(
                                    change_type="svi",
                                    op="create",
                                    vlan_id=vlan_id,
                                    ip_address=ip_address,
                                    prefix_length=prefix_length,
                                    interface=iface_name,
                                    status="apply",
                                    reason=f"SVI for VLAN {vlan_id} must be updated on {device_name}.",
                                )
                            ]
                        )
                    ))
                    reason_parts.append(f"SVI for VLAN {vlan_id} must be updated on {device_name}")
            else:
                iface_name = get_svi_interface_name(device.vendor, vlan_id)
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            SviChangeOperation(
                                change_type="svi",
                                op="create",
                                vlan_id=vlan_id,
                                ip_address=ip_address,
                                prefix_length=prefix_length,
                                interface=iface_name,
                                status="apply",
                                reason=f"SVI for VLAN {vlan_id} must be created on {device_name}.",
                            )
                        ]
                    )
                ))
                reason_parts.append(f"SVI for VLAN {vlan_id} must be created on {device_name}")

        elif operation == "ensure_absent":
            if not device_supports_svi(device):
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            SviChangeOperation(
                                change_type="svi",
                                op="remove",
                                vlan_id=vlan_id,
                                status="blocked",
                                reason=f"SVI configuration is not supported on {device.role} devices (device {device_name}).",
                            )
                        ]
                    )
                ))
                reason_parts.append(f"SVI configuration is not supported on {device_name}")
                continue

            existing_iface = get_existing_svi_interface(device, vlan_id)
            if existing_iface:
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            SviChangeOperation(
                                change_type="svi",
                                op="remove",
                                vlan_id=vlan_id,
                                interface=existing_iface.name,
                                status="apply",
                                reason=f"SVI for VLAN {vlan_id} exists on {device_name} and must be removed.",
                            )
                        ]
                    )
                ))
                reason_parts.append(f"SVI for VLAN {vlan_id} must be deleted from {device_name}")
            else:
                iface_name = get_svi_interface_name(device.vendor, vlan_id)
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        operations=[
                            SviChangeOperation(
                                change_type="svi",
                                op="remove",
                                vlan_id=vlan_id,
                                interface=iface_name,
                                status="skip",
                                reason=f"SVI does not exist on {device_name}.",
                            )
                        ]
                    )
                ))
        else:
            return _blocked(f"Unsupported SVI operation '{operation}'.")

    merged_changes = _merge_device_changes(all_device_changes)
    if not merged_changes or not merged_changes[0].changes.operations:
        return _no_op(f"No changes required for {device_name}.")

    ops = merged_changes[0].changes.operations
    blocked_ops = [op for op in ops if op.status == "blocked"]
    apply_ops = [op for op in ops if op.status == "apply"]

    if blocked_ops and not apply_ops:
        # All actionable operations are blocked — plan-level block
        reasons = [op.reason for op in blocked_ops if op.reason]
        reason_str = "; ".join(reasons) if reasons else f"Blocked operations on {device_name}"
        return _blocked(reason_str, merged_changes)

    if not apply_ops:
        # Only skip operations remain — no-op
        return _no_op(f"No changes required for {device_name}.")

    # Mixed or all-apply: proceed with apply decision
    platform_errors = validate_platform_constraints(device.platform, merged_changes)
    if platform_errors:
        for op in merged_changes[0].changes.operations:
            if (
                isinstance(op, VlanChangeOperation)
                and op.op == "create"
                and op.status == "apply"
                and not op.name
                and device.platform
                and device.platform.lower() == "mist"
            ):
                op.status = "blocked"
                op.reason = (
                    f"Platform 'mist' requires a non-empty VLAN name for VLAN {op.vlan_id} "
                    f"creation on device '{device_name}'."
                )
        return _blocked("; ".join(platform_errors), merged_changes)

    return _apply("; ".join(reason_parts) + ".", merged_changes)


def _evaluate_routing_operations(
    run_id: str,
    site: str,
    device_name: str,
    desired_state: dict[str, Any],
    inventory_source: str,
) -> PlanDecision:
    try:
        if not isinstance(desired_state, dict):
            return _blocked("desired_state must be a dictionary.")

        device = _load_device_from_inventory(
            run_id, site=site, device_name=device_name, inventory_source=inventory_source
        )
        if device is None:
            return _blocked(
                f"Device '{device_name}' was not found in the inventory snapshot for site '{site}'. "
                "Verify the device name and site."
            )

        operations = desired_state.get("operations")
        if operations is None:
            if "routes" in desired_state:
                routes = desired_state["routes"]
                if not isinstance(routes, list):
                    return _blocked("desired_state.routes must be a list of routing operations.")
                operations = routes
            elif "prefix" in desired_state or "next_hop" in desired_state:
                operations = [desired_state]
            else:
                return _blocked("desired_state does not contain valid routing operations.")
        elif not isinstance(operations, list):
            return _blocked("desired_state.operations must be a list of routing operations.")

        if not operations:
            return _blocked("desired_state.operations is required for routing operations.")

        target = RenderTarget(
            name=device.name,
            site=device.site,
            role=device.role,
            platform=device.platform,
            primary_ip=device.management_ip,
        )

        route_ops: list[StaticRouteOp] = []
        reason_parts: list[str] = []

        for op in operations:
            if not isinstance(op, dict):
                return _blocked("Each routing operation must be a dictionary.")

            target_device = _get_value(op, "target_device")
            if target_device is not None and not isinstance(target_device, str):
                return _blocked(f"Invalid target_device '{target_device}'. Must be a string.")

            target_devices = _get_value(op, "target_devices")
            if target_devices is not None and not isinstance(target_devices, (list, tuple, set)):
                return _blocked(f"Invalid target_devices '{target_devices}'. Must be a list of device names.")

            if not _op_matches_device(op, device_name):
                continue

            attrs = _get_value(op, "attributes", {}) if "attributes" in op else op
            if not isinstance(attrs, dict):
                return _blocked("Operation attributes must be a dictionary.")

            prefix = _get_value(attrs, "prefix") or _get_value(attrs, "subnet")
            next_hop = _get_value(attrs, "next_hop")
            op_name = _get_value(op, "operation", "ensure_present")
            description = _get_value(attrs, "description")
            admin_distance = _get_value(attrs, "admin_distance")

            if not prefix:
                return _blocked("prefix is required for static route operation.")
            try:
                net = ipaddress.ip_network(str(prefix), strict=False)
            except (ValueError, TypeError):
                return _blocked(f"Invalid prefix '{prefix}'. Must be a valid CIDR network prefix.")
            prefix_str = str(net)

            if not next_hop:
                return _blocked("next_hop is required for static route operation.")
            try:
                nh_ip = ipaddress.ip_address(str(next_hop))
            except (ValueError, TypeError):
                return _blocked(f"Invalid next_hop '{next_hop}'. Must be a valid IP address.")
            next_hop_str = str(nh_ip)

            if admin_distance is not None:
                if (
                    isinstance(admin_distance, bool)
                    or not isinstance(admin_distance, int)
                    or not (1 <= admin_distance <= 255)
                ):
                    return _blocked(f"Invalid admin_distance '{admin_distance}'. Must be between 1 and 255.")

            op_type = (
                OperationType.REMOVE
                if op_name in ("ensure_absent", "remove", "delete")
                else OperationType.ENSURE_PRESENT
            )

            route_op = StaticRouteOp(
                prefix=prefix_str,
                next_hop=next_hop_str,
                operation=op_type,
                target=target,
                description=str(description) if description is not None else None,
                admin_distance=admin_distance,
            )
            route_ops.append(route_op)
            if op_type == OperationType.ENSURE_PRESENT:
                reason_parts.append(f"Static route {prefix_str} via {next_hop_str} must be created on {device_name}")
            else:
                reason_parts.append(f"Static route {prefix_str} must be removed from {device_name}")

        if not route_ops:
            return _no_op(f"No routing changes required for {device_name}.")

        device_change = DeviceChange(
            device=device_name,
            domain=NetworkDomain.ROUTING,
            changes=route_ops,
        )
        return _apply("; ".join(reason_parts) + ".", [device_change])
    except Exception as e:
        return _blocked(f"Routing evaluation failed with error: {e}")


_DOMAIN_EVALUATORS: dict[str, Callable[..., PlanDecision]] = {
    "vlan": _evaluate_vlan_operations,
    "routing": _evaluate_routing_operations,
}


# Any: heterogeneous desired_state payload
def evaluate_intent_state(
    run_id: str,
    domain: str,
    site: str | None,
    device_names: list[str],
    desired_state: dict[str, Any] | None = None,
    inventory_source: str = "mock",
) -> PlanDecision:
    """Evaluate whether a normalized intent is already satisfied, requires changes,
    or should be blocked based on current inventory state.

    Returns a PlanDecision with list[DeviceChange] diff.
    """

    if desired_state is not None and not isinstance(desired_state, dict):
        return _blocked("desired_state must be a dictionary.")

    desired_state = desired_state or {}

    if not site:
        return _blocked("Site is required to evaluate intent.")

    if not device_names:
        return _blocked("At least one target device is required to evaluate intent.")

    evaluator = _DOMAIN_EVALUATORS.get(domain)
    if evaluator is None:
        return _blocked(f"Unsupported evaluation domain '{domain}'.")

    try:
        decisions = []
        for device_name in device_names:
            decision = evaluator(
                run_id=run_id,
                site=site,
                device_name=device_name,
                desired_state=desired_state,
                inventory_source=inventory_source,
            )
            decisions.append(decision)
    except Exception as e:
        return _blocked(f"Intent evaluation failed with error: {e}")

    blocked_decisions = [d for d in decisions if d.decision == PlanDecisionType.BLOCKED]
    if blocked_decisions:
        reason = "; ".join(d.reason for d in blocked_decisions)
        all_diffs = []
        for d in decisions:
            all_diffs.extend(d.diff)
        return _blocked(reason, diff=all_diffs)

    apply_decisions = [d for d in decisions if d.decision == PlanDecisionType.APPLY]
    if apply_decisions:
        reason = " ".join(d.reason for d in apply_decisions)
        diff = []
        for d in apply_decisions:
            diff.extend(d.diff)
        return _apply(reason, diff)

    reason = " ".join(d.reason for d in decisions)
    return _no_op(reason)
