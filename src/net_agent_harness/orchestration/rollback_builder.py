"""rollback_builder.py — Build structured rollback plans from forward diffs.

Pure deterministic function that takes a PlanDecision and produces a
RollbackPlan with operation-specific rollback steps.

Rollback ordering follows reverse dependency order:
  interface changes (first to undo) → SVI → VLAN (last to undo)

Only 'apply' operations produce rollback steps — skip and blocked operations
are excluded since they don't change device state.
"""

from __future__ import annotations

from ..models.changes import (
    ChangeOperation,
    InterfaceChangeOperation,
    PlanDecision,
    RollbackPlan,
    RollbackStep,
    SviChangeOperation,
    VlanChangeOperation,
)


# Reverse dependency priority: lower number = undo first.
# Interfaces depend on SVIs and VLANs, so they are removed first.
_OBJECT_TYPE_PRIORITY: dict[str, int] = {
    "interface": 0,
    "svi": 1,
    "vlan": 2,
}

# Inverse operation mappings per (object_type, forward_op)
_INVERSE_OP: dict[tuple[str, str], str] = {
    ("vlan", "create"): "remove",
    ("vlan", "remove"): "create",
    ("svi", "create"): "remove",
    ("svi", "remove"): "create",
    ("interface", "set_access_vlan"): "reset_access_vlan",
    ("interface", "set_trunk"): "reset_trunk",
}


def _rollback_description(
    op: ChangeOperation,
    device_name: str,
    inverse_op: str,
) -> str:
    """Build a human-readable rollback description for one operation."""
    if isinstance(op, VlanChangeOperation):
        name_part = f" ({op.name})" if op.name else ""
        if inverse_op == "remove":
            return f"Remove VLAN {op.vlan_id}{name_part} from {device_name}"
        return f"Re-create VLAN {op.vlan_id}{name_part} on {device_name}"

    if isinstance(op, SviChangeOperation):
        iface_part = f" on interface {op.interface}" if op.interface else ""
        if inverse_op == "remove":
            return f"Remove SVI for VLAN {op.vlan_id}{iface_part} from {device_name}"
        return f"Re-create SVI for VLAN {op.vlan_id}{iface_part} on {device_name}"

    if isinstance(op, InterfaceChangeOperation):
        if inverse_op == "reset_access_vlan":
            return (
                f"Reset access VLAN on {op.interface} to previous value on {device_name}"
            )
        return f"Reset trunk config on {op.interface} on {device_name}"

    return f"Undo {op.change_type} {op.op} on {device_name}"


def _rollback_attributes(op: ChangeOperation) -> dict[str, object]:
    """Extract the key attributes needed for rollback execution."""
    attrs: dict[str, object] = {}
    if isinstance(op, VlanChangeOperation):
        attrs["vlan_id"] = op.vlan_id
        if op.name:
            attrs["name"] = op.name
    elif isinstance(op, SviChangeOperation):
        attrs["vlan_id"] = op.vlan_id
        if op.interface:
            attrs["interface"] = op.interface
        if op.ip_address:
            attrs["ip_address"] = op.ip_address
        if op.prefix_length is not None:
            attrs["prefix_length"] = op.prefix_length
    elif isinstance(op, InterfaceChangeOperation):
        attrs["interface"] = op.interface
        attrs["vlan_id"] = op.vlan_id
    return attrs


def build_rollback_plan(plan_decision: PlanDecision) -> RollbackPlan:
    """Build a structured rollback plan from the forward diff.

    Parameters
    ----------
    plan_decision:
        The ``PlanDecision`` whose ``diff`` contains the forward operations.

    Returns
    -------
    RollbackPlan
        Contains both ``structured_rollback_steps`` (typed) and
        ``rollback_steps`` (human-readable text) for backward compatibility.
    """
    if not plan_decision.diff:
        return RollbackPlan(
            summary="No operations to roll back.",
            rollback_steps=[],
            structured_rollback_steps=[],
        )

    # Collect all apply operations across all devices
    raw_steps: list[tuple[int, RollbackStep]] = []

    for device_change in plan_decision.diff:
        device_name = device_change.device
        for op in device_change.changes.operations:
            if op.status != "apply":
                continue

            inverse_op = _INVERSE_OP.get((op.change_type, op.op))
            if inverse_op is None:
                # Unknown operation pair — skip rather than crash
                continue

            priority = _OBJECT_TYPE_PRIORITY.get(op.change_type, 99)
            step = RollbackStep(
                order=0,  # Will be set after sorting
                object_type=op.change_type,  # type: ignore[arg-type]
                operation=inverse_op,
                target_device=device_name,
                attributes=_rollback_attributes(op),
                description=_rollback_description(op, device_name, inverse_op),
            )
            raw_steps.append((priority, step))

    if not raw_steps:
        return RollbackPlan(
            summary="No applicable operations to roll back.",
            rollback_steps=[],
            structured_rollback_steps=[],
        )

    # Sort by priority (interface first → SVI → VLAN) for reverse dependency order
    raw_steps.sort(key=lambda pair: pair[0])

    # Assign 1-indexed order
    structured_steps: list[RollbackStep] = []
    text_steps: list[str] = []
    for idx, (_, step) in enumerate(raw_steps, start=1):
        step.order = idx
        structured_steps.append(step)
        text_steps.append(step.description)

    # Build summary from the device names involved
    devices = sorted({s.target_device for s in structured_steps})
    summary = f"Roll back operations on {', '.join(devices)}"

    return RollbackPlan(
        summary=summary,
        rollback_steps=text_steps,
        structured_rollback_steps=structured_steps,
    )
