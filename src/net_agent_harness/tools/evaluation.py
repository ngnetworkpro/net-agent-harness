from collections.abc import Callable
from ..models.changes import DeviceChange, PlanDecision, VlanChange
from ..models.enums import NetworkDomain, PlanDecisionType
from ..tools.vlan_state import compute_vlan_diff


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


def _evaluate_vlan_intent(
    run_id: str,
    intent_type: str,
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

    vlans_list = desired_state.get("vlans", [])
    interfaces_list = desired_state.get("interfaces", [])

    if not vlans_list:
        return _blocked("desired_state.vlans is required for VLAN operations.")

    first_vlan = vlans_list[0]
    vlan_id = first_vlan.get("vlan_id")
    vlan_name = first_vlan.get("name", "")

    if intent_type in {"set_access_vlan", "provision_access_port"}:
        if vlan_id is None:
            return _blocked("vlan_id is required in desired_state.vlans[0] for set_access_vlan.")

        device_changes = compute_vlan_diff(
            intent={
                "vlan_id": vlan_id,
                "vlan_name": vlan_name,
                "interfaces": interfaces_list,
            },
            current_state=device,
        )

        if not device_changes:
            return _no_op(f"No changes required for {device_name}.")

        changes = device_changes[0].changes
        if not changes.vlans_to_create and not changes.ports_to_update:
            return _no_op(
                f"VLAN {vlan_id} already access-configured on all target interfaces on {device_name}."
            )

        reason_parts = []
        if changes.vlans_to_create:
            reason_parts.append(f"VLAN {vlan_id} must be created on {device_name}")
        if changes.ports_to_update:
            reason_parts.append(
                f"{len(changes.ports_to_update)} interface(s) require access update: {', '.join(p.interface for p in changes.ports_to_update)}"
            )

        return _apply("; ".join(reason_parts) + ".", device_changes)

    if intent_type in {"create_vlan"}:
        if vlan_id is None:
            return _blocked("vlan_id is required in desired_state.vlans[0] for create_vlan.")

        device_changes = compute_vlan_diff(
            intent={
                "vlan_id": vlan_id,
                "vlan_name": vlan_name,
                "interfaces": [],
            },
            current_state=device,
        )

        changes = device_changes[0].changes
        if not changes.vlans_to_create:
            return _no_op(f"VLAN {vlan_id} already exists on {device_name}.")

        return _apply(f"VLAN {vlan_id} must be created on {device_name}.", device_changes)

    if intent_type in {"update_trunk_allowed_vlans", "provision_vlan_trunk"}:
        if vlan_id is None:
            return _blocked(f"vlan_id is required in desired_state.vlans[0] for {intent_type}.")

        device_changes = compute_vlan_diff(
            intent={
                "vlan_id": vlan_id,
                "vlan_name": vlan_name,
                "interfaces": interfaces_list,
            },
            current_state=device,
        )

        changes = device_changes[0].changes
        if not changes.vlans_to_create and not changes.ports_to_update:
            return _no_op(
                f"VLAN {vlan_id} already trunk-configured on all target interfaces on {device_name}."
            )

        reason_parts = []
        if changes.vlans_to_create:
            reason_parts.append(f"VLAN {vlan_id} must be created on {device_name}")
        if changes.ports_to_update:
            reason_parts.append(
                f"{len(changes.ports_to_update)} interface(s) require trunk update: {', '.join(p.interface for p in changes.ports_to_update)}"
            )

        return _apply("; ".join(reason_parts) + ".", device_changes)

    if intent_type in {"create_vlan", "delete_vlan", "set_native_vlan", "create_or_update_svi", "check_vlan_state"}:
        return _blocked(
            f"VLAN intent_type '{intent_type}' is not yet implemented in evaluate_intent."
        )

    return _blocked(f"Unsupported VLAN intent_type '{intent_type}'.")


_DOMAIN_EVALUATORS: dict[str, Callable[..., PlanDecision]] = {
    "vlan": _evaluate_vlan_intent,
}


def evaluate_intent_state(
    run_id: str,
    domain: str,
    intent_type: str,
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
        intent_type=intent_type,
        site=site,
        device_name=device_names[0],
        desired_state=desired_state,
    )