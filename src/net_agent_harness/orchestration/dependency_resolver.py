"""Cross-domain dependency resolver for change requests.

This module provides deterministic, side-effect-free functions that check
whether the structured cross-domain dependencies on a ``ChangeRequest``
are in the required lifecycle state before rendering is allowed.

Dependency types
----------------
- ``ipam_allocation``   — an upstream ``PrefixAllocationPlan`` or
  ``IPAssignmentPlan`` must be at least ``approved``.
- ``topology_plan``     — an upstream ``TopologyUpdatePlan`` must be at
  least ``approved``.
- ``device_availability`` — a target device must be reachable and not
  already under an active change.
- ``policy_check``      — a design-policy validation must have passed.

Lifecycle ordering
------------------
The resolver treats the ``ResourceLifecycleState`` values as an ordered
progression:

    current < intended < planned < approved < applied < verified

A dependency is satisfied when its ``current_lifecycle_state`` is at or
beyond the ``required_lifecycle_state``.
"""

from __future__ import annotations

from ..models.changes import ChangeRequestDependency
from ..models.enums import ResourceLifecycleState

# Ordered lifecycle states from least to most advanced.
_LIFECYCLE_ORDER: list[ResourceLifecycleState] = [
    ResourceLifecycleState.CURRENT,
    ResourceLifecycleState.INTENDED,
    ResourceLifecycleState.PLANNED,
    ResourceLifecycleState.APPROVED,
    ResourceLifecycleState.APPLIED,
    ResourceLifecycleState.VERIFIED,
]


def _lifecycle_rank(state: ResourceLifecycleState) -> int:
    """Return the ordinal rank of a lifecycle state (higher = more advanced)."""
    try:
        return _LIFECYCLE_ORDER.index(state)
    except ValueError:
        return -1


def _is_state_satisfied(
    current: ResourceLifecycleState,
    required: ResourceLifecycleState,
) -> bool:
    """Return True when *current* is at or beyond *required* in the lifecycle."""
    return _lifecycle_rank(current) >= _lifecycle_rank(required)


def resolve_dependencies(
    dependencies: list[ChangeRequestDependency],
) -> tuple[bool, list[str]]:
    """Check all cross-domain dependencies and report whether they are satisfied.

    Only blocking dependencies (``dep.blocking is True``) are evaluated.
    Non-blocking dependencies are skipped silently.

    Parameters
    ----------
    dependencies:
        The list of ``ChangeRequestDependency`` entries from a
        ``ChangeRequest.cross_domain_dependencies`` field.

    Returns
    -------
    tuple[bool, list[str]]
        ``(all_resolved, blocking_reasons)`` where:

        - ``all_resolved`` is ``True`` when every blocking dependency is
          satisfied.
        - ``blocking_reasons`` contains a human-readable explanation for
          each unsatisfied blocking dependency.  Empty when all resolved.
    """
    blocking_reasons: list[str] = []

    for dep in dependencies:
        if not dep.blocking:
            continue

        # No observed state recorded — dependency cannot be satisfied.
        if dep.current_lifecycle_state is None:
            blocking_reasons.append(
                f"Dependency '{dep.description}' (type: {dep.dependency_type}) "
                "has no recorded lifecycle state and cannot be verified."
            )
            continue

        # No required state means any observed state is acceptable.
        if dep.required_lifecycle_state is None:
            continue

        if not _is_state_satisfied(
            dep.current_lifecycle_state, dep.required_lifecycle_state
        ):
            blocking_reasons.append(
                f"Dependency '{dep.description}' (type: {dep.dependency_type}) "
                f"is at state '{dep.current_lifecycle_state.value}' but requires "
                f"at least '{dep.required_lifecycle_state.value}'."
            )

    return (len(blocking_reasons) == 0, blocking_reasons)
