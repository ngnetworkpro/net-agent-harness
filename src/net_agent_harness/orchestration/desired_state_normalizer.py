from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..models.changes import VlanDesiredState
from ..models.enums import NetworkDomain


def normalize_desired_state(
    domain: NetworkDomain,
    desired_state: dict[str, Any] | VlanDesiredState | BaseModel,
) -> dict[str, Any]:
    if hasattr(desired_state, "model_dump"):
        desired_state = desired_state.model_dump(exclude_unset=True)

    normalizer = _NORMALIZERS.get(domain)
    if normalizer:
        return normalizer(desired_state)
    return desired_state


def _normalize_vlan_desired_state(state: dict[str, Any]) -> dict[str, Any]:
    if "operations" in state and isinstance(state["operations"], list):
        # We assume it's already using the structured format; default empty VLAN names on ensure_present
        normalized_ops = []
        for op in state["operations"]:
            if isinstance(op, dict) and op.get("object_type") == "vlan" and op.get("operation") == "ensure_present":
                attrs = dict(op.get("attributes") or {})
                vlan_id = attrs.get("vlan_id")
                if vlan_id is not None and not attrs.get("name"):
                    attrs["name"] = str(vlan_id)
                normalized_ops.append({**op, "attributes": attrs})
            else:
                normalized_ops.append(op)
        return {**state, "operations": normalized_ops}

    operations = []

    if state.get("vlans"):
        for vlan in state["vlans"]:
            vlan_id = vlan.get("vlan_id")
            vlan_name = vlan.get("name") or (str(vlan_id) if vlan_id is not None else "")
            operations.append({
                "object_type": "vlan",
                "operation": "ensure_present",
                "attributes": {
                    "vlan_id": vlan_id,
                    "name": vlan_name,
                },
            })

    elif "vlan_id" in state:
        vlan_id = state.get("vlan_id")
        vlan_name = state.get("name") or (str(vlan_id) if vlan_id is not None else "")
        operations.append({
            "object_type": "vlan",
            "operation": "ensure_present",
            "attributes": {
                "vlan_id": vlan_id,
                "name": vlan_name,
            },
        })

    interfaces = state.get("interfaces", [])
    if interfaces:
        for iface in interfaces:
            mode = iface.get("switchport_mode", "access").lower()
            op = "set_trunk" if mode == "trunk" else "set_access_vlan"
            operations.append({
                "object_type": "interface",
                "operation": op,
                "attributes": {
                    "name": iface.get("name"),
                    "access_vlan": iface.get("access_vlan") or state.get("vlan_id"),
                },
            })

    return {"operations": operations} if operations else state


_NORMALIZERS: dict[NetworkDomain, Callable[[dict[str, Any]], dict[str, Any]]] = {
    NetworkDomain.VLAN: _normalize_vlan_desired_state,
}
