from collections.abc import Callable

from ..models.changes import DeviceChange


def _validate_mist_constraints(changes: list[DeviceChange]) -> list[str]:
    errors = []
    for dc in changes:
        if dc.changes:
            for vlan in dc.changes.vlans_to_create:
                if not vlan.name:
                    errors.append(
                        f"Platform 'mist' requires a non-empty VLAN name for VLAN {vlan.id} creation on device '{dc.device}'."
                    )
    return errors


_PLATFORM_VALIDATORS: dict[str, Callable[[list[DeviceChange]], list[str]]] = {
    "mist": _validate_mist_constraints,
}


def validate_platform_constraints(platform: str | None, changes: list[DeviceChange]) -> list[str]:
    """Validate a planned diff against platform-specific constraints.

    Returns a list of error strings. If the list is empty, validation passed.
    """
    if not platform:
        return []

    validator = _PLATFORM_VALIDATORS.get(platform.lower())
    if not validator:
        return []

    return validator(changes)
