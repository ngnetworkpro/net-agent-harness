"""vlan_state.py — Pure helpers for evaluating VLAN provisioning intent against live state.

These functions operate directly on Pydantic model objects and have no side-effects,
making them trivially testable and safe to call from any layer.
"""

from ..models.inventory import DeviceInfo, InterfaceInfo
from ..models.enums import SwitchportMode, AllowedVlansMode, NetworkDomain
from ..models.changes import DeviceChange, VlanChange


def compute_vlan_diff(intent: dict, current_state: DeviceInfo) -> list[DeviceChange]:
    """Compare a VLAN provisioning intent against the current device state.

    Parameters
    ----------
    intent:
        A dict with the following keys:

        ``vlan_id`` *(int, required)*
            The VLAN ID to provision.
        ``target_interfaces`` *(list[str], required)*
            Interface names that should carry the VLAN.
        ``mode`` *(str, default "trunk")*
            ``"trunk"`` or ``"access"`` — how the VLAN should be presented
            on each target interface.
        ``vlan_name`` *(str | None, optional)*
            Human-readable label; used only in reason strings.

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
                        vlans_to_create=[<int>, ...],
                        ports_to_update=["<iface_name>", ...],
                    ),
                )
            ]

        The entry may have empty vlans_to_create and ports_to_update if no
        changes are required for this device.
    """
    vlan_id: int = intent["vlan_id"]
    target_names: list[str] = list(intent.get("target_interfaces") or [])
    mode: str = intent.get("mode", "trunk").lower()
    vlan_label: str = (
        f"VLAN {vlan_id} ({intent['vlan_name']})"
        if intent.get("vlan_name")
        else f"VLAN {vlan_id}"
    )

    vlans_to_create: list[int] = []
    ports_to_update: list[str] = []
    unknown_interfaces: list[str] = []

    if not vlan_exists(current_state, vlan_id):
        vlans_to_create.append(vlan_id)

    iface_map: dict[str, InterfaceInfo] = {
        iface.name: iface for iface in current_state.interfaces
    }

    for iface_name in target_names:
        iface = iface_map.get(iface_name)
        if iface is None:
            unknown_interfaces.append(iface_name)
            continue

        if mode == "trunk":
            if iface.mode != SwitchportMode.TRUNK:
                ports_to_update.append(iface_name)
            elif not trunk_allows_vlan(iface, vlan_id):
                ports_to_update.append(iface_name)

        elif mode == "access":
            if iface.mode != SwitchportMode.ACCESS:
                ports_to_update.append(iface_name)
            elif not access_vlan_matches(iface, vlan_id):
                ports_to_update.append(iface_name)

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
