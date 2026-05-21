from collections.abc import Callable
from ..models.changes import (
    DeviceChange,
    PlanDecision,
    VlanChange,
    VlanSpec,
    VlanChangeOperation,
    SviChangeOperation,
    InterfaceChangeOperation,
    ChangeOperation,
)
from ..models.enums import NetworkDomain, PlanDecisionType, DeviceVendor
from ..models.inventory import DeviceInfo
from ..tools.vlan_state import compute_vlan_diff, vlan_exists
from ..orchestration.platform_constraints import validate_platform_constraints


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
        if "meraki" in vendor_str or (device.platform and "meraki" in device.platform.lower()):
            return True
        return False
    return True


def get_existing_svi_interface(device: DeviceInfo, vlan_id: int):
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
):
    from .inventory_tools import lookup_device_context_sync
    from ..models.inventory import DeviceInfo

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


def _merge_device_changes(all_changes: list[DeviceChange]) -> list[DeviceChange]:
    if not all_changes:
        return []

    device_name = all_changes[0].device
    domain = all_changes[0].domain
    
    merged_ops: list[ChangeOperation] = []
    for dc in all_changes:
        merged_ops.extend(dc.changes.operations)

    # Deduplicate operations
    # Key by (change_type, op, vlan_id, interface)
    deduped: dict[tuple, ChangeOperation] = {}
    for op in merged_ops:
        key = (
            op.change_type,
            op.op,
            getattr(op, "vlan_id", None),
            getattr(op, "interface", None),
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = op
        elif isinstance(op, VlanChangeOperation) and isinstance(existing, VlanChangeOperation):
            # Prefer the one with a non-empty name
            if not existing.name and op.name:
                deduped[key] = op
        else:
            # For other operations, we can keep the existing or update.
            pass

    return [DeviceChange(
        device=device_name,
        domain=domain,
        changes=VlanChange(operations=list(deduped.values())),
    )]


def _op_matches_device(op: dict, device_name: str) -> bool:
    target_device = op.get("target_device")
    target_devices = op.get("target_devices")
    
    if target_device is not None and target_device != device_name:
        return False
    if target_devices is not None and device_name not in target_devices:
        return False
        
    return True


def _evaluate_vlan_operations(
    run_id: str,
    site: str,
    device_name: str,
    desired_state: dict,
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

    vlan_ops = [op for op in operations if op.get("object_type") == "vlan" and _op_matches_device(op, device_name)]
    interface_ops = [op for op in operations if op.get("object_type") == "interface" and _op_matches_device(op, device_name)]
    svi_ops = [op for op in operations if op.get("object_type") == "svi" and _op_matches_device(op, device_name)]

    for vlan_op in vlan_ops:
        operation = vlan_op.get("operation")
        attrs = vlan_op.get("attributes", {})
        vlan_id = attrs.get("vlan_id")
        vlan_name = attrs.get("name", "")

        if operation == "ensure_present":
            if vlan_id is None:
                return _blocked("vlan_id is required for vlan ensure_present operation.")
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

    for iface_op in interface_ops:
        operation = iface_op.get("operation")
        attrs = iface_op.get("attributes", {})
        iface_name = attrs.get("name")
        access_vlan = attrs.get("access_vlan")

        if iface_name is None:
            return _blocked("interface name is required for interface operations.")

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
        elif operation == "set_trunk":
            device_changes = compute_vlan_diff(
                intent={
                    "vlan_id": access_vlan or 1,
                    "vlan_name": "",
                    "interfaces": [{
                        "name": iface_name,
                        "switchport_mode": "trunk",
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
                                op="set_trunk",
                                interface=iface_name,
                                vlan_id=access_vlan or 1,
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
                                vlan_id=access_vlan or 1,
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
        operation = svi_op.get("operation")
        attrs = svi_op.get("attributes", {})
        vlan_id = attrs.get("vlan_id")
        ip_address = attrs.get("ip_address")
        prefix_length = attrs.get("prefix_length")

        if vlan_id is None:
            return _blocked("vlan_id is required for svi operations.")

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
        return _blocked("; ".join(platform_errors), merged_changes)

    return _apply("; ".join(reason_parts) + ".", merged_changes)


_DOMAIN_EVALUATORS: dict[str, Callable[..., PlanDecision]] = {
    "vlan": _evaluate_vlan_operations,
}


def evaluate_intent_state(
    run_id: str,
    domain: str,
    site: str | None,
    device_names: list[str],
    desired_state: dict | None = None,
    inventory_source: str = "mock",
) -> PlanDecision:
    """Evaluate whether a normalized intent is already satisfied, requires changes,
    or should be blocked based on current inventory state.

    Returns a PlanDecision with list[DeviceChange] diff.
    """

    desired_state = desired_state or {}

    if not site:
        return _blocked("Site is required to evaluate intent.")

    if not device_names:
        return _blocked("At least one target device is required to evaluate intent.")

    evaluator = _DOMAIN_EVALUATORS.get(domain)
    if evaluator is None:
        return _blocked(f"Unsupported evaluation domain '{domain}'.")

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
