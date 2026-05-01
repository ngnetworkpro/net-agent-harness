"""vlan_state.py — Pure helpers for evaluating VLAN provisioning intent against live state.

These functions operate directly on Pydantic model objects and have no side-effects,
making them trivially testable and safe to call from any layer.
"""

from ..models.inventory import DeviceInfo, InterfaceInfo
from ..models.enums import SwitchportMode, AllowedVlansMode


# ---------------------------------------------------------------------------
# Atomic state queries
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_vlan_diff(intent: dict, current_state: DeviceInfo) -> dict:
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
    dict
        A PlanDecision-compatible structure::

            {
                "decision": "apply" | "no_op" | "blocked",
                "reason": "<human-readable explanation>",
                "diff": {
                    "vlans_to_create": [<int>, ...],
                    "ports_to_update": ["<iface_name>", ...],
                },
            }

        ``no_op``   — intent is already fully satisfied; no work needed.
        ``apply``   — one or more changes are required.
        ``blocked`` — the request references interfaces that do not exist on
                      this device; the plan cannot proceed safely.
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

    # ---- 1. VLAN existence ------------------------------------------------
    if not vlan_exists(current_state, vlan_id):
        vlans_to_create.append(vlan_id)

    # ---- 2. Per-interface state -------------------------------------------
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
                # Port exists but is in the wrong mode entirely
                ports_to_update.append(iface_name)
            elif not trunk_allows_vlan(iface, vlan_id):
                ports_to_update.append(iface_name)

        elif mode == "access":
            if iface.mode != SwitchportMode.ACCESS:
                ports_to_update.append(iface_name)
            elif not access_vlan_matches(iface, vlan_id):
                ports_to_update.append(iface_name)

    # ---- 3. Blocked: unknown interfaces -----------------------------------
    if unknown_interfaces:
        return {
            "decision": "blocked",
            "reason": (
                f"The following interfaces do not exist on {current_state.name}: "
                + ", ".join(unknown_interfaces)
                + ". Verify interface names before proceeding."
            ),
            "diff": {
                "vlans_to_create": vlans_to_create,
                "ports_to_update": ports_to_update,
            },
        }

    # ---- 4. No-op: nothing to do -----------------------------------------
    if not vlans_to_create and not ports_to_update:
        iface_clause = (
            f"and is already {mode}-configured on all {len(target_names)} target interface(s)"
            if target_names
            else "on this device"
        )
        return {
            "decision": "no_op",
            "reason": f"{vlan_label} already exists {iface_clause}.",
            "diff": {"vlans_to_create": [], "ports_to_update": []},
        }

    # ---- 5. Apply: work is required --------------------------------------
    parts: list[str] = []
    if vlans_to_create:
        parts.append(f"{vlan_label} must be created on {current_state.name}")
    if ports_to_update:
        parts.append(
            f"{len(ports_to_update)} interface(s) require {mode} update: "
            + ", ".join(ports_to_update)
        )

    return {
        "decision": "apply",
        "reason": "; ".join(parts) + ".",
        "diff": {
            "vlans_to_create": vlans_to_create,
            "ports_to_update": ports_to_update,
        },
    }
