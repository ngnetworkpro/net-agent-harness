from collections.abc import Callable

from ..models.enums import NetworkDomain


from pydantic import BaseModel
from ..models.changes import VlanDesiredState

def normalize_desired_state(domain: NetworkDomain, desired_state: dict | VlanDesiredState | BaseModel) -> dict:
    if hasattr(desired_state, "model_dump"):
        desired_state = desired_state.model_dump(exclude_unset=True)

    normalizer = _NORMALIZERS.get(domain)
    if normalizer:
        return normalizer(desired_state)
    return desired_state


def _normalize_vlan_desired_state(state: dict) -> dict:
    if "operations" in state and isinstance(state["operations"], list):
        # We assume it's already using the structured format
        return state

    operations = []

    if "vlans" in state and state["vlans"]:
        for vlan in state["vlans"]:
            operations.append({
                "object_type": "vlan",
                "operation": "ensure_present",
                "attributes": {
                    "vlan_id": vlan.get("vlan_id"),
                    "name": vlan.get("name", ""),
                },
            })

    elif "vlan_id" in state:
        operations.append({
            "object_type": "vlan",
            "operation": "ensure_present",
            "attributes": {
                "vlan_id": state.get("vlan_id"),
                "name": state.get("name", ""),
            },
        })

    interfaces = state.get("interfaces", [])
    if interfaces:
        for iface in interfaces:
            mode = iface.get("switchport_mode", "access").lower()
            if mode == "trunk":
                op = "set_trunk"
            else:
                op = "set_access_vlan"
            operations.append({
                "object_type": "interface",
                "operation": op,
                "attributes": {
                    "name": iface.get("name"),
                    "access_vlan": iface.get("access_vlan") or state.get("vlan_id"),
                },
            })

    return {"operations": operations} if operations else state


_NORMALIZERS: dict[NetworkDomain, Callable[[dict], dict]] = {
    NetworkDomain.VLAN: _normalize_vlan_desired_state,
}
