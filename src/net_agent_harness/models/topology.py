"""Topology update plan models.

This module defines the ``TopologyUpdatePlan`` artifact that is produced
by the ``plan.topology`` workflow.  A topology plan explicitly records the
current topology state, the desired topology state, and the delta between
them.

Plans live at ``ResourceLifecycleState.PLANNED`` until approved and are
not allowed to generate device configuration — that remains a render step.

Artifact filename: ``topologyupdateplan.json``
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .common import ArtifactMeta, ScopeRef
from .enums import PlanDecisionType, ResourceLifecycleState


class TopologyLink(BaseModel):
    """A single logical link between two device endpoints."""

    model_config = ConfigDict(extra="forbid")

    endpoint_a_device: str = Field(description="Hostname of the first endpoint device")
    endpoint_a_interface: str | None = Field(
        default=None, description="Interface name on the first endpoint, if known"
    )
    endpoint_b_device: str = Field(description="Hostname of the second endpoint device")
    endpoint_b_interface: str | None = Field(
        default=None, description="Interface name on the second endpoint, if known"
    )
    link_type: str | None = Field(
        default=None,
        description="Logical link type, e.g. 'uplink', 'peer', 'transit', 'mgmt'",
    )


class TopologyState(BaseModel):
    """A snapshot of the topology at a point in time."""

    model_config = ConfigDict(extra="forbid")

    devices: list[str] = Field(
        default_factory=list,
        description="Hostnames of devices present in this topology snapshot",
    )
    links: list[TopologyLink] = Field(
        default_factory=list,
        description="Logical links present in this topology snapshot",
    )


class TopologyDelta(BaseModel):
    """The set of changes between a current and desired topology state."""

    model_config = ConfigDict(extra="forbid")

    devices_added: list[str] = Field(
        default_factory=list,
        description="Devices present in desired state but absent from current state",
    )
    devices_removed: list[str] = Field(
        default_factory=list,
        description="Devices present in current state but absent from desired state",
    )
    links_added: list[TopologyLink] = Field(
        default_factory=list,
        description="Links present in desired state but absent from current state",
    )
    links_removed: list[TopologyLink] = Field(
        default_factory=list,
        description="Links present in current state but absent from desired state",
    )

    @property
    def is_empty(self) -> bool:
        """Return True when there are no differences between states."""
        return (
            not self.devices_added
            and not self.devices_removed
            and not self.links_added
            and not self.links_removed
        )


class TopologyUpdatePlan(BaseModel):
    """A planned topology change artifact.

    Records the current topology state, the desired topology state, and
    the computed delta.  Plans start at ``lifecycle_state=planned`` and
    must pass an approval gate before any device configuration is rendered.

    Plans can be blocked when device facts are missing or when the delta
    cannot be safely computed from available inventory.

    Artifact filename: ``topologyupdateplan.json``
    """

    model_config = ConfigDict(extra="forbid")

    meta: ArtifactMeta
    scope: ScopeRef
    summary: str = Field(
        description="Short human-readable description of the topology change being planned"
    )
    current_state: TopologyState = Field(
        default_factory=TopologyState,
        description="Topology state as observed from inventory at planning time",
    )
    desired_state: TopologyState = Field(
        default_factory=TopologyState,
        description="Desired topology state after the change is applied",
    )
    delta: TopologyDelta = Field(
        default_factory=TopologyDelta,
        description="Computed difference between current and desired state",
    )
    decision: PlanDecisionType = Field(
        default=PlanDecisionType.BLOCKED,
        description=(
            "apply — delta is valid and safe to render; "
            "no_op — desired state already matches current state; "
            "blocked — cannot proceed safely"
        ),
    )
    blocking_reason: str | None = Field(
        default=None,
        description="Human-readable reason when decision is blocked",
    )
    missing_device_facts: list[str] = Field(
        default_factory=list,
        description="Device names whose facts could not be resolved from inventory",
    )
    lifecycle_state: ResourceLifecycleState = Field(
        default=ResourceLifecycleState.PLANNED,
        description="Lifecycle state of this topology plan; starts at 'planned'",
    )
