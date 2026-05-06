from ..models.enums import NetworkDomain


def normalize_desired_state(domain: NetworkDomain, desired_state: dict) -> dict:
    normalizer = _NORMALIZERS.get(domain)
    if normalizer:
        return normalizer(desired_state)
    return desired_state


def _normalize_vlan_desired_state(state: dict) -> dict:
    if "vlans" in state:
        return state

    if "vlan_id" in state or "name" in state:
        return {
            "vlans": [{
                "vlan_id": state.get("vlan_id"),
                "name": state.get("name", ""),
            }],
            "interfaces": state.get("interfaces", []),
        }
    return state


_NORMALIZERS: dict[NetworkDomain, callable] = {
    NetworkDomain.VLAN: _normalize_vlan_desired_state,
}