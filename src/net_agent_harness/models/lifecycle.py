"""Lifecycle state transitions and planned-change models.

This module defines:
- ``ALLOWED_TRANSITIONS`` — the set of valid next states for each lifecycle state.
- ``validate_transition`` — enforces that a state change is allowed.
- ``PlannedTopologyUpdate`` — a topology change that carries an explicit
  lifecycle state so it can be tracked from *planned* through *verified*
  before the device is touched.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field

from .enums import NetworkDomain, ResourceLifecycleState

# ---------------------------------------------------------------------------
# Allowed state transitions
# ---------------------------------------------------------------------------

#: Maps each state to the set of states it may transition into.
#:
#: Key design decisions:
#: - ``current`` → ``planned``: a new planned change starts against current state.
#: - ``intended`` → ``planned``: intent is refined into a concrete diff.
#: - ``planned`` → ``approved``: change passes an approval gate.
#: - ``planned`` → ``current``: a planned change is abandoned or rejected;
#:   the resource reverts to reflecting current deployed state.
#: - ``approved`` → ``applied``: the approved change is executed.
#: - ``applied`` → ``verified``: the applied change is confirmed against intent.
#: - ``applied`` → ``current``: verification step is skipped; treated as current.
ALLOWED_TRANSITIONS: dict[ResourceLifecycleState, set[ResourceLifecycleState]] = {
    ResourceLifecycleState.CURRENT: {
        ResourceLifecycleState.PLANNED,
    },
    ResourceLifecycleState.INTENDED: {
        ResourceLifecycleState.PLANNED,
    },
    ResourceLifecycleState.PLANNED: {
        ResourceLifecycleState.APPROVED,
        ResourceLifecycleState.CURRENT,  # abandoned or rejected
    },
    ResourceLifecycleState.APPROVED: {
        ResourceLifecycleState.APPLIED,
    },
    ResourceLifecycleState.APPLIED: {
        ResourceLifecycleState.VERIFIED,
        ResourceLifecycleState.CURRENT,  # verification skipped
    },
    ResourceLifecycleState.VERIFIED: set(),  # terminal state
}


def validate_transition(
    from_state: ResourceLifecycleState,
    to_state: ResourceLifecycleState,
) -> bool:
    """Return ``True`` if transitioning *from_state* → *to_state* is allowed.

    Raises ``ValueError`` when the transition is not permitted so callers that
    need hard enforcement can rely on the exception rather than checking the
    return value.

    Parameters
    ----------
    from_state:
        The current lifecycle state of the resource.
    to_state:
        The proposed next lifecycle state.

    Returns
    -------
    bool
        ``True`` when the transition is allowed.

    Raises
    ------
    ValueError
        When the transition is not in ``ALLOWED_TRANSITIONS``.
    """
    allowed = ALLOWED_TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise ValueError(
            f"Invalid lifecycle transition: {from_state.value!r} → {to_state.value!r}. "
            f"Allowed next states for {from_state.value!r}: "
            f"{sorted(s.value for s in allowed) or 'none (terminal state)'}."
        )
    return True


# ---------------------------------------------------------------------------
# Topology planned-change model
# ---------------------------------------------------------------------------


class PlannedTopologyUpdate(BaseModel):
    """A topology change that exists at an explicit lifecycle state.

    A topology update can be created as ``planned`` and then transitioned
    through ``approved`` → ``applied`` → ``verified`` before it is considered
    done.  This allows topology and IPAM to be updated safely before
    activation.

    Workflow access
    ---------------
    - **plan** stage: creates records with ``lifecycle_state=planned``.
    - **execute** stage (approval-gated): advances state to ``applied``.
    - **review** stage: advances state to ``verified``.
    - **discovery / read-only** workflows: read any state; write is not permitted.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Run ID that produced this planned topology update")
    domain: NetworkDomain = Field(description="Network domain for this update (vlan, routing, …)")
    device_name: str = Field(description="Hostname of the target device")
    change_summary: str = Field(description="Human-readable description of what will change")
    lifecycle_state: ResourceLifecycleState = Field(
        default=ResourceLifecycleState.PLANNED,
        description="Current lifecycle state of this topology update",
    )
    approved_by: str | None = Field(
        default=None,
        description="Identity that approved this update; populated when state is approved or later",
    )
    applied_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when this update was applied to the device",
    )
    verified_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the applied change was verified",
    )

    def advance(self, to_state: ResourceLifecycleState, **kwargs: object) -> "PlannedTopologyUpdate":
        """Return a *copy* of this update with the lifecycle state advanced.

        Uses ``validate_transition`` to guard against invalid moves.

        Parameters
        ----------
        to_state:
            The target lifecycle state.
        **kwargs:
            Additional field overrides applied to the returned copy
            (e.g. ``approved_by="alice"``).

        Raises
        ------
        ValueError
            If the transition is not permitted.
        """
        validate_transition(self.lifecycle_state, to_state)
        data = self.model_dump()
        data["lifecycle_state"] = to_state
        if to_state == ResourceLifecycleState.APPLIED and data.get("applied_at") is None:
            data["applied_at"] = datetime.now(timezone.utc)
        if to_state == ResourceLifecycleState.VERIFIED and data.get("verified_at") is None:
            data["verified_at"] = datetime.now(timezone.utc)
        data.update(kwargs)
        return PlannedTopologyUpdate(**data)
