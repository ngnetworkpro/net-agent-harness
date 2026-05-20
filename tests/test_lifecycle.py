"""Tests for resource lifecycle state enums, transitions, and planned-change models.

Covers acceptance criteria from the issue:
- A topology update can exist as ``planned`` before it is applied.
- An IPAM allocation can be reserved or planned before device configuration exists.
- State transitions are explicit and testable.
"""

import pytest
from pydantic import ValidationError

from net_agent_harness.models.enums import NetworkDomain, ResourceLifecycleState
from net_agent_harness.models.ipam import IpamAddressAssignment, IpamPrefix
from net_agent_harness.models.lifecycle import (
    ALLOWED_TRANSITIONS,
    PlannedTopologyUpdate,
    validate_transition,
)


# ---------------------------------------------------------------------------
# ResourceLifecycleState enum
# ---------------------------------------------------------------------------


def test_lifecycle_state_enum_has_required_values() -> None:
    """All six states from the issue must be present."""
    values = {s.value for s in ResourceLifecycleState}
    assert values == {"current", "intended", "planned", "approved", "applied", "verified"}


def test_lifecycle_state_is_str_enum() -> None:
    assert isinstance(ResourceLifecycleState.PLANNED, str)
    assert ResourceLifecycleState.PLANNED == "planned"


# ---------------------------------------------------------------------------
# validate_transition — allowed paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_state, to_state",
    [
        (ResourceLifecycleState.CURRENT, ResourceLifecycleState.PLANNED),
        (ResourceLifecycleState.INTENDED, ResourceLifecycleState.PLANNED),
        (ResourceLifecycleState.PLANNED, ResourceLifecycleState.APPROVED),
        (ResourceLifecycleState.PLANNED, ResourceLifecycleState.CURRENT),
        (ResourceLifecycleState.APPROVED, ResourceLifecycleState.APPLIED),
        (ResourceLifecycleState.APPLIED, ResourceLifecycleState.VERIFIED),
        (ResourceLifecycleState.APPLIED, ResourceLifecycleState.CURRENT),
    ],
)
def test_validate_transition_allows_valid_paths(
    from_state: ResourceLifecycleState,
    to_state: ResourceLifecycleState,
) -> None:
    assert validate_transition(from_state, to_state) is True


# ---------------------------------------------------------------------------
# validate_transition — forbidden paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_state, to_state",
    [
        (ResourceLifecycleState.CURRENT, ResourceLifecycleState.APPLIED),
        (ResourceLifecycleState.CURRENT, ResourceLifecycleState.VERIFIED),
        (ResourceLifecycleState.PLANNED, ResourceLifecycleState.APPLIED),
        (ResourceLifecycleState.PLANNED, ResourceLifecycleState.VERIFIED),
        (ResourceLifecycleState.APPROVED, ResourceLifecycleState.VERIFIED),
        (ResourceLifecycleState.VERIFIED, ResourceLifecycleState.PLANNED),
        (ResourceLifecycleState.VERIFIED, ResourceLifecycleState.CURRENT),
    ],
)
def test_validate_transition_rejects_invalid_paths(
    from_state: ResourceLifecycleState,
    to_state: ResourceLifecycleState,
) -> None:
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        validate_transition(from_state, to_state)


def test_validate_transition_terminal_state_raises() -> None:
    """VERIFIED is a terminal state; no transitions out of it are allowed."""
    with pytest.raises(ValueError, match="terminal state"):
        validate_transition(ResourceLifecycleState.VERIFIED, ResourceLifecycleState.VERIFIED)


def test_allowed_transitions_covers_all_states() -> None:
    """Every state must appear as a key in ALLOWED_TRANSITIONS."""
    for state in ResourceLifecycleState:
        assert state in ALLOWED_TRANSITIONS, f"{state} missing from ALLOWED_TRANSITIONS"


# ---------------------------------------------------------------------------
# PlannedTopologyUpdate — creation
# ---------------------------------------------------------------------------


def test_planned_topology_update_defaults_to_planned_state() -> None:
    """A topology update can exist as planned before it is applied."""
    update = PlannedTopologyUpdate(
        run_id="run-1",
        domain=NetworkDomain.VLAN,
        device_name="sw1",
        change_summary="Add VLAN 220 to sw1",
    )
    assert update.lifecycle_state == ResourceLifecycleState.PLANNED
    assert update.approved_by is None
    assert update.applied_at is None
    assert update.verified_at is None


def test_planned_topology_update_accepts_explicit_state() -> None:
    update = PlannedTopologyUpdate(
        run_id="run-2",
        domain=NetworkDomain.VLAN,
        device_name="sw1",
        change_summary="Add VLAN 220",
        lifecycle_state=ResourceLifecycleState.APPROVED,
        approved_by="alice",
    )
    assert update.lifecycle_state == ResourceLifecycleState.APPROVED
    assert update.approved_by == "alice"


def test_planned_topology_update_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PlannedTopologyUpdate(  # type: ignore[call-arg]
            run_id="run-3",
            domain=NetworkDomain.VLAN,
            device_name="sw1",
            change_summary="test",
            unexpected_field="not allowed",
        )


# ---------------------------------------------------------------------------
# PlannedTopologyUpdate.advance() — lifecycle transitions
# ---------------------------------------------------------------------------


def test_advance_planned_to_approved() -> None:
    update = PlannedTopologyUpdate(
        run_id="run-1",
        domain=NetworkDomain.VLAN,
        device_name="sw1",
        change_summary="Add VLAN 220",
    )
    approved = update.advance(ResourceLifecycleState.APPROVED, approved_by="bob")
    assert approved.lifecycle_state == ResourceLifecycleState.APPROVED
    assert approved.approved_by == "bob"
    # Original is unchanged
    assert update.lifecycle_state == ResourceLifecycleState.PLANNED


def test_advance_approved_to_applied_sets_timestamp() -> None:
    update = PlannedTopologyUpdate(
        run_id="run-1",
        domain=NetworkDomain.VLAN,
        device_name="sw1",
        change_summary="Add VLAN 220",
        lifecycle_state=ResourceLifecycleState.APPROVED,
    )
    applied = update.advance(ResourceLifecycleState.APPLIED)
    assert applied.lifecycle_state == ResourceLifecycleState.APPLIED
    assert applied.applied_at is not None


def test_advance_applied_to_verified_sets_verified_timestamp() -> None:
    update = PlannedTopologyUpdate(
        run_id="run-1",
        domain=NetworkDomain.VLAN,
        device_name="sw1",
        change_summary="Add VLAN 220",
        lifecycle_state=ResourceLifecycleState.APPLIED,
    )
    verified = update.advance(ResourceLifecycleState.VERIFIED)
    assert verified.lifecycle_state == ResourceLifecycleState.VERIFIED
    assert verified.verified_at is not None


def test_advance_rejects_invalid_transition() -> None:
    update = PlannedTopologyUpdate(
        run_id="run-1",
        domain=NetworkDomain.VLAN,
        device_name="sw1",
        change_summary="Add VLAN 220",
    )
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        update.advance(ResourceLifecycleState.APPLIED)  # skips APPROVED


def test_full_lifecycle_chain() -> None:
    """Walk a topology update through the complete happy-path chain."""
    update = PlannedTopologyUpdate(
        run_id="run-chain",
        domain=NetworkDomain.VLAN,
        device_name="sw1",
        change_summary="Provision VLAN 300",
    )
    assert update.lifecycle_state == ResourceLifecycleState.PLANNED

    approved = update.advance(ResourceLifecycleState.APPROVED, approved_by="mgr")
    assert approved.lifecycle_state == ResourceLifecycleState.APPROVED

    applied = approved.advance(ResourceLifecycleState.APPLIED)
    assert applied.lifecycle_state == ResourceLifecycleState.APPLIED

    verified = applied.advance(ResourceLifecycleState.VERIFIED)
    assert verified.lifecycle_state == ResourceLifecycleState.VERIFIED


# ---------------------------------------------------------------------------
# IPAM models — lifecycle_state support
# ---------------------------------------------------------------------------


def test_ipam_prefix_defaults_to_current_state() -> None:
    """An existing IPAM prefix defaults to current lifecycle state."""
    prefix = IpamPrefix(cidr="10.10.20.0/24", site="HQ", vlan_id=20)
    assert prefix.lifecycle_state == ResourceLifecycleState.CURRENT


def test_ipam_prefix_can_be_planned() -> None:
    """An IPAM allocation can be reserved/planned before device config exists."""
    prefix = IpamPrefix(
        cidr="10.10.99.0/24",
        site="HQ",
        vlan_id=99,
        lifecycle_state=ResourceLifecycleState.PLANNED,
    )
    assert prefix.lifecycle_state == ResourceLifecycleState.PLANNED


def test_ipam_prefix_rejects_invalid_lifecycle_state() -> None:
    with pytest.raises(ValidationError):
        IpamPrefix(cidr="10.0.0.0/8", lifecycle_state="nonexistent")  # type: ignore[arg-type]


def test_ipam_address_assignment_defaults_to_current_state() -> None:
    assignment = IpamAddressAssignment(address="10.0.0.10/24", device_name="sw1")
    assert assignment.lifecycle_state == ResourceLifecycleState.CURRENT


def test_ipam_address_assignment_can_be_planned() -> None:
    """An IP assignment can be planned before the device configuration exists."""
    assignment = IpamAddressAssignment(
        address="10.0.0.99/24",
        device_name="sw-new",
        interface="ge-0/0/1",
        lifecycle_state=ResourceLifecycleState.PLANNED,
    )
    assert assignment.lifecycle_state == ResourceLifecycleState.PLANNED
    assert assignment.device_name == "sw-new"


def test_ipam_address_assignment_can_be_approved() -> None:
    assignment = IpamAddressAssignment(
        address="10.0.0.100/24",
        device_name="sw2",
        lifecycle_state=ResourceLifecycleState.APPROVED,
    )
    assert assignment.lifecycle_state == ResourceLifecycleState.APPROVED
