"""vlan_state.py — Pure helpers for evaluating VLAN provisioning intent against live state.

These functions operate directly on Pydantic model objects and have no side-effects,
making them trivially testable and safe to call from any layer.
"""

from ..models.inventory import DeviceInfo, InterfaceInfo
from ..models.enums import SwitchportMode, AllowedVlansMode, NetworkDomain
from ..models.changes import DeviceChange, VlanChange, VlanSpec, PortSpec


def compute_vlan_diff(intent: dict, current_state: DeviceInfo) -> list[DeviceChange]:
    """Compare a VLAN provisioning intent against the current device state.

    Parameters
    ----------
    intent:
        A dict with the following keys:

        ``vlan_id`` *(int, required)*
            The VLAN ID to provision (used for VLAN creation check).
        ``vlan_name`` *(str | None, optional)*
            Human-readable label; used only in reason strings.
        ``interfaces`` *(list[dict], optional)*
            List of interface dicts, each with:
            - ``name``: interface name
            - ``switchport_mode``: "access" or "trunk"
            - ``access_vlan``: VLAN ID for access ports

    current_state:
        The fully-populated ``DeviceInfo`` for the target device, including
        its ``vlans`` table and ``interfaces`` list.

    Returns
    -------
    list[DeviceChange]
        A list containing one DeviceChange entry for the current device::

            [
                DeviceChange(
                    device="switch-01",
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[VlanSpec(id=220, name="Finance"), ...],
                        ports_to_update=[PortSpec(interface="ge-0/0/1", vlan_id=220, mode="access"), ...],
                    ),
                )
            ]

        The entry may have empty vlans_to_create and ports_to_update if no
        changes are required for this device.
    """
    vlan_id: int = intent["vlan_id"]
    vlan_name: str = intent.get("vlan_name", "")
    interfaces: list[dict] = intent.get("interfaces", [])

    vlans_to_create: list[VlanSpec] = []
    ports_to_update: list[PortSpec] = []
    unknown_interfaces: list[str] = []

    if not vlan_exists(current_state, vlan_id):
        vlans_to_create.append(VlanSpec(id=vlan_id, name=vlan_name))

    iface_map: dict[str, InterfaceInfo] = {
        iface.name: iface for iface in current_state.interfaces
    }

    for iface in interfaces:
        if "interface_id" in iface.keys():
            iface_name = iface.get("interface_id")
        elif "name" in iface.keys():
            iface_name = iface.get("name")
        else:
            continue

        iface_obj = iface_map.get(iface_name)
        if iface_obj is None:
            unknown_interfaces.append(iface_name)
            continue

        mode = iface.get("switchport_mode", "trunk").lower()
        iface_vlan_id = iface.get("access_vlan") or vlan_id

        if mode == "trunk":
            if iface_obj.mode != SwitchportMode.TRUNK:
                ports_to_update.append(PortSpec(interface=iface_name, vlan_id=iface_vlan_id, mode=mode))
            elif not trunk_allows_vlan(iface_obj, iface_vlan_id):
                ports_to_update.append(PortSpec(interface=iface_name, vlan_id=iface_vlan_id, mode=mode))

        elif mode == "access":
            if iface_obj.mode != SwitchportMode.ACCESS:
                ports_to_update.append(PortSpec(interface=iface_name, vlan_id=iface_vlan_id, mode=mode))
            elif not access_vlan_matches(iface_obj, iface_vlan_id):
                ports_to_update.append(PortSpec(interface=iface_name, vlan_id=iface_vlan_id, mode=mode))

    device_change = DeviceChange(
        device=current_state.name,
        domain=NetworkDomain.VLAN,
        changes=VlanChange(
            vlans_to_create=vlans_to_create,
            ports_to_update=ports_to_update,
        ),
    )

    return [device_change]


def vlan_exists(device: DeviceInfo, vlan_id: int) -> bool:
    """Return True if *vlan_id* is present in the device's VLAN table."""
    return any(v.id == vlan_id for v in device.vlans)


def trunk_allows_vlan(interface: InterfaceInfo, vlan_id: int) -> bool:
    """Return True if a trunk interface will carry *vlan_id*.

    - ``allowed_vlans_mode=ALL``  → always True
    - ``allowed_vlans_mode=NONE`` → always False
    - ``allowed_vlans_mode=LIST`` → True only when *vlan_id* is in ``vlan_ids``

    Raises
    ------
    ValueError
        If called on a non-trunk interface, so callers are alerted to logic
        mistakes rather than silently returning False.
    """
    if interface.mode != SwitchportMode.TRUNK:
        raise ValueError(
            f"trunk_allows_vlan called on non-trunk interface '{interface.name}' "
            f"(mode={interface.mode})"
        )
    if interface.allowed_vlans_mode == AllowedVlansMode.ALL:
        return True
    if interface.allowed_vlans_mode == AllowedVlansMode.NONE:
        return False
    # LIST mode
    return vlan_id in interface.vlan_ids


def access_vlan_matches(interface: InterfaceInfo, vlan_id: int) -> bool:
    """Return True if an access port is already assigned to *vlan_id*.

    Raises
    ------
    ValueError
        If called on a non-access interface.
    """
    if interface.mode != SwitchportMode.ACCESS:
        raise ValueError(
            f"access_vlan_matches called on non-access interface '{interface.name}' "
            f"(mode={interface.mode})"
        )
    return interface.access_vlan == vlan_id
