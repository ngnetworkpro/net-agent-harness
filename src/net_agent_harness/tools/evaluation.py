from collections.abc import Callable
from ..models.changes import DeviceChange, PlanDecision, VlanChange, VlanSpec, PortSpec
from ..models.enums import NetworkDomain, PlanDecisionType
from ..tools.vlan_state import compute_vlan_diff, vlan_exists


def _blocked(reason: str) -> PlanDecision:
    return PlanDecision(
        decision=PlanDecisionType.BLOCKED,
        reason=reason,
        diff=[],
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


def _load_device_from_inventory(
    run_id: str,
    site: str,
    device_name: str,
):
    from ..adapters.mock_inventory_adapter import get_inventory_for_site

    snapshot = get_inventory_for_site(run_id=run_id, site=site)
    return next((d for d in snapshot.devices if d.name == device_name), None)


def _merge_device_changes(all_changes: list[DeviceChange]) -> list[DeviceChange]:
    if not all_changes:
        return []
    if len(all_changes) == 1:
        return all_changes

    merged_vlans: list[VlanSpec] = []
    merged_ports: list[PortSpec] = []
    device_name = all_changes[0].device

    for dc in all_changes:
        merged_vlans.extend(dc.changes.vlans_to_create)
        merged_ports.extend(dc.changes.ports_to_update)

    return [DeviceChange(
        device=device_name,
        domain=NetworkDomain.VLAN,
        changes=VlanChange(
            vlans_to_create=merged_vlans,
            ports_to_update=merged_ports,
        ),
    )]


def _evaluate_vlan_operations(
    run_id: str,
    site: str,
    device_name: str,
    desired_state: dict,
) -> PlanDecision:
    device = _load_device_from_inventory(run_id, site=site, device_name=device_name)
    if device is None:
        return _blocked(
            f"Device '{device_name}' was not found in the inventory snapshot for site '{site}. "
            "Verify the device name and site."
        )

    operations = desired_state.get("operations", [])
    if not operations:
        return _blocked("desired_state.operations is required for VLAN operations.")

    all_device_changes: list[DeviceChange] = []
    reason_parts: list[str] = []

    vlan_ops = [op for op in operations if op.get("object_type") == "vlan"]
    interface_ops = [op for op in operations if op.get("object_type") == "interface"]

    for vlan_op in vlan_ops:
        operation = vlan_op.get("operation")
        attrs = vlan_op.get("attributes", {})
        vlan_id = attrs.get("vlan_id")
        vlan_name = attrs.get("name", "")

        if operation == "ensure_present":
            if vlan_id is None:
                return _blocked("vlan_id is required for vlan ensure_present operation.")
            device_changes = compute_vlan_diff(
                intent={
                    "vlan_id": vlan_id,
                    "vlan_name": vlan_name,
                    "interfaces": [],
                },
                current_state=device,
            )
            changes = device_changes[0].changes
            if changes.vlans_to_create:
                all_device_changes.extend(device_changes)
                reason_parts.append(f"VLAN {vlan_id} must be created on {device_name}")
        elif operation == "ensure_absent":
            if vlan_id is None:
                return _blocked("vlan_id is required for vlan ensure_absent operation.")
            if vlan_exists(device, vlan_id):
                all_device_changes.append(DeviceChange(
                    device=device_name,
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[],
                        ports_to_update=[],
                    ),
                ))
                reason_parts.append(f"VLAN {vlan_id} must be deleted from {device_name}")
        else:
            return _blocked(f"Unsupported vlan operation '{operation}'.")

    for iface_op in interface_ops:
        operation = iface_op.get("operation")
        attrs = iface_op.get("attributes", {})
        iface_name = attrs.get("name")
        access_vlan = attrs.get("access_vlan")
        native_vlan = attrs.get("native_vlan")
        allowed_vlans = attrs.get("allowed_vlans", [])

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
                all_device_changes.extend(device_changes)
                reason_parts.append(
                    f"Interface {iface_name} requires access VLAN {access_vlan} update on {device_name}"
                )
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
                all_device_changes.extend(device_changes)
                reason_parts.append(f"Interface {iface_name} requires trunk update on {device_name}")
        else:
            return _blocked(f"Unsupported interface operation '{operation}'.")

    if not all_device_changes:
        return _no_op(f"No changes required for {device_name}.")

    merged_changes = _merge_device_changes(all_device_changes)

    merged_vlans = merged_changes[0].changes.vlans_to_create if merged_changes else []
    merged_ports = merged_changes[0].changes.ports_to_update if merged_changes else []

    if not merged_vlans and not merged_ports:
        return _no_op(f"No changes required for {device_name}.")

    return _apply("; ".join(reason_parts) + ".", merged_changes)


_DOMAIN_EVALUATORS: dict[str, Callable[..., PlanDecision]] = {
    "vlan": _evaluate_vlan_operations,
}


def evaluate_intent_state(
    run_id: str,
    domain: str,
    site: str,
    device_names: list[str],
    desired_state: dict | None = None,
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

    if len(device_names) != 1:
        return _blocked(
            "This first-pass evaluator supports exactly one target device. "
            "Split the request per device or extend the evaluator for multi-device scope."
        )

    evaluator = _DOMAIN_EVALUATORS.get(domain)
    if evaluator is None:
        return _blocked(f"Unsupported evaluation domain '{domain}'.")

    return evaluator(
        run_id=run_id,
        site=site,
        device_name=device_names[0],
        desired_state=desired_state,
    )