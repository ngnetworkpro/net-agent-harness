from ..models.enums import NetworkDomain


def normalize_desired_state(domain: NetworkDomain, desired_state: dict) -> dict:
    normalizer = _NORMALIZERS.get(domain)
    if normalizer:
        return normalizer(desired_state)
    return desired_state


def _normalize_vlan_desired_state(state: dict) -> dict:
    if "operations" in state:
        return state

    operations = []

    if "vlans" in state and state["vlans"]:
        first_vlan = state["vlans"][0]
        operations.append({
            "object_type": "vlan",
            "operation": "ensure_present",
            "attributes": {
                "vlan_id": first_vlan.get("vlan_id"),
                "name": first_vlan.get("name", ""),
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


_NORMALIZERS: dict[NetworkDomain, callable] = {
    NetworkDomain.VLAN: _normalize_vlan_desired_state,
}