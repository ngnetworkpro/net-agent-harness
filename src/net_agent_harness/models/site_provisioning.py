"""Site provisioning intent model.

This module defines ``SiteProvisioningIntent``, the top-level artifact for
the ``plan.site`` workflow family.  A site provisioning intent coordinates
topology planning, IPAM allocation, and change planning as a single tracked
intent with child artifact references.

Workflow graph (all stages read-only or mock-backed initially):
    discover → allocate_ipam → plan_topology → plan_changes → validate

Each stage produces a child artifact that is linked back to the intent via
``child_artifacts``.  No live infrastructure changes are attempted.

Artifact filename: ``siteprovisioningintent.json``
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import ArtifactMeta, ScopeRef
from .enums import IntentStatus
from .intent import ArtifactRef


class SubnetAllocation(BaseModel):
    """A planned subnet allocation within a site provisioning intent."""

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(
        description="Intended use, e.g. 'management', 'servers', 'guest', 'voice'"
    )
    prefix: str | None = Field(
        default=None,
        description="Proposed CIDR allocation, e.g. '10.10.5.0/24'; None when not yet resolved",
    )
    vlan_id: int | None = Field(
        default=None,
        description="VLAN ID associated with this subnet, if applicable",
        ge=1,
        le=4094,
    )
    prefix_allocation_run_id: str | None = Field(
        default=None,
        description="Run ID of the PrefixAllocationPlan artifact that reserved this prefix",
    )


class SiteProvisioningIntent(BaseModel):
    """Top-level intent artifact for the site provisioning workflow.

    A single ``SiteProvisioningIntent`` coordinates:
    - IPAM prefix and address reservations
    - Topology link and device role planning
    - Per-device change planning

    Each stage produces a child artifact linked via ``child_artifacts``.

    All stages remain read-only or mock-backed until explicit approval
    gates are wired in a later phase.

    Artifact filename: ``siteprovisioningintent.json``
    """

    model_config = ConfigDict(extra="forbid")

    meta: ArtifactMeta
    scope: ScopeRef
    site_name: str = Field(description="Name of the site being provisioned, e.g. 'BRANCH-07'")
    summary: str = Field(
        description="Short human-readable description of the provisioning intent"
    )
    subnet_allocations: list[SubnetAllocation] = Field(
        default_factory=list,
        description="Planned subnet allocations for this site",
    )
    vlan_assignments: list[int] = Field(
        default_factory=list,
        description="VLAN IDs that will be provisioned at this site",
    )
    device_roles: list[str] = Field(
        default_factory=list,
        description="Expected device roles at this site, e.g. ['core', 'access', 'firewall']",
    )
    template_name: str | None = Field(
        default=None,
        description="Name of the site template used to seed this intent, if any",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made when formulating this intent",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints that must be respected",
    )
    status: IntentStatus = Field(
        default=IntentStatus.DRAFT,
        description="Lifecycle status of the intent",
    )
    desired_state: dict[str, Any] = Field(
        default_factory=dict,
        description="High-level desired network state for this site",
    )
    child_artifacts: list[ArtifactRef] = Field(
        default_factory=list,
        description=(
            "References to child artifacts produced during provisioning: "
            "PrefixAllocationPlan, TopologyUpdatePlan, ChangeRequest, etc."
        ),
    )
    # Stage cross-references for quick lookup
    ipam_allocation_run_id: str | None = Field(
        default=None,
        description="Run ID of the IPAM allocation stage, if completed",
    )
    topology_plan_run_id: str | None = Field(
        default=None,
        description="Run ID of the topology planning stage, if completed",
    )
    change_plan_run_ids: list[str] = Field(
        default_factory=list,
        description="Run IDs of per-device change planning stages, if completed",
    )
