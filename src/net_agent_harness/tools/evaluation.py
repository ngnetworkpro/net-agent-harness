from collections.abc import Callable
from ..tools.vlan_state import compute_vlan_diff


def _blocked(reason: str, diff: dict | None = None) -> dict:
    return {
        "decision": "blocked",
        "reason": reason,
        "diff": diff or {},
    }


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
) -> dict:
    device = _load_device_from_inventory(run_id, site=site, device_name=device_name)
    if device is None:
        return _blocked(
            f"Device '{device_name}' was not found in the inventory snapshot for site '{site}'. "
            "Verify the device name and site."
        )

    vlan_id = desired_state.get("vlan_id")
    vlan_name = desired_state.get("vlan_name")
    target_interfaces = desired_state.get("target_interfaces", [])

    if intent_type in {"set_access_vlan"}:
        if vlan_id is None:
            return _blocked("desired_state.vlan_id is required for set_access_vlan.")

        return compute_vlan_diff(
            intent={
                "vlan_id": vlan_id,
                "target_interfaces": target_interfaces,
                "mode": "access",
                "vlan_name": vlan_name,
            },
            current_state=device,
        )

    if intent_type in {"create_vlan"}:
        if vlan_id is None:
            return _blocked("desired_state.vlan_id is required for create_vlan.")

        return compute_vlan_diff(
            intent={
                "vlan_id": vlan_id,
                "target_interfaces": [],
                "vlan_name": vlan_name,
            },
            current_state=device,
        )

    if intent_type in {"update_trunk_allowed_vlans", "provision_vlan_trunk"}:
        if vlan_id is None:
            return _blocked(f"desired_state.vlan_id is required for {intent_type}.")

        return compute_vlan_diff(
            intent={
                "vlan_id": vlan_id,
                "target_interfaces": target_interfaces,
                "mode": "trunk",
                "vlan_name": vlan_name,
            },
            current_state=device,
        )

    if intent_type in {"create_vlan", "delete_vlan", "set_native_vlan", "create_or_update_svi", "check_vlan_state"}:
        return _blocked(
            f"VLAN intent_type '{intent_type}' is not yet implemented in evaluate_intent."
        )

    return _blocked(f"Unsupported VLAN intent_type '{intent_type}'.")


_DOMAIN_EVALUATORS: dict[str, Callable[..., dict]] = {
    "vlan": _evaluate_vlan_intent,
}

def evaluate_intent_state(
    run_id: str,
    domain: str,
    intent_type: str,
    site: str,
    device_names: list[str],
    desired_state: dict | None = None,
) -> dict:
    """
    Evaluate whether a normalized intent is already satisfied, requires changes,
    or should be blocked based on current inventory state.

    Returns a PlanDecision-shaped dict:
    {
        "decision": "apply" | "no_op" | "blocked",
        "reason": str,
        "diff": dict,
    }
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
