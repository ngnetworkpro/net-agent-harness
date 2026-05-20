"""Higher-level intent artifact models for multi-device and multi-domain workflows.

Intent artifacts sit above ``ChangeRequest`` in the artifact hierarchy and are
intended for workflows that span more than a single device change (e.g. a full
site VLAN rollout, a topology re-addressing, an IPAM allocation, or a device
provisioning batch).  A single intent can reference multiple child plans,
renders, and execution outputs via ``ArtifactRef`` entries.

Artifact relationships
----------------------
Intent artifact  →  one or more  →  ChangeRequest  (change_request.json)
                 →  one or more  →  ConfigRender   (config_render.json)
                 →  one or more  →  ExecutionPlan  (execution_plan.json)

All intent models carry ``ArtifactMeta`` so they can be versioned and persisted
by ``ArtifactStore`` in the same way as existing artifacts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import ArtifactMeta, ScopeRef
from .enums import IntentStatus, NetworkDomain


class ArtifactRef(BaseModel):
    """A typed reference to a lower-level artifact produced under this intent.

    Use ``artifact_type`` values that match the canonical artifact file names
    used by ``ArtifactStore``:
    - ``"change_request"``   → ``change_request.json``
    - ``"config_render"``    → ``config_render.json``
    - ``"execution_plan"``   → ``execution_plan.json``
    - ``"validation_report"`` → ``validation_report.json``
    """

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(description="Unique artifact identifier from ArtifactMeta.artifact_id")
    artifact_type: str = Field(
        description=(
            "Canonical artifact type: change_request, config_render, "
            "execution_plan, validation_report, or similar."
        )
    )
    run_id: str = Field(description="Run ID under which the artifact was produced")
    description: str | None = Field(
        default=None,
        description="Optional human-readable note about this reference",
    )


class BaseIntent(BaseModel):
    """Shared fields for all intent artifact types.

    Intent artifacts are versioned and persistable via ``ArtifactStore``.
    They act as the durable parent record for larger workflows that span
    multiple ``ChangeRequest`` artifacts, renders, and execution outputs.
    """

    model_config = ConfigDict(extra="forbid")

    meta: ArtifactMeta
    scope: ScopeRef
    summary: str = Field(description="Short human-readable description of the overall intent")
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made when formulating this intent",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Other changes or conditions this intent depends on",
    )
    desired_state: dict[str, Any] = Field(
        default_factory=dict,
        description="High-level desired network state this intent aims to achieve",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints that must be respected (e.g. maintenance windows, exclusions)",
    )
    approval_required: bool = Field(
        default=False,
        description="Whether this intent requires explicit approval before execution",
    )
    approval_notes: str | None = Field(
        default=None,
        description="Who or what must approve; approval criteria or ticket reference",
    )
    status: IntentStatus = Field(
        default=IntentStatus.DRAFT,
        description="Lifecycle status of the intent",
    )
    child_artifacts: list[ArtifactRef] = Field(
        default_factory=list,
        description=(
            "References to lower-level artifacts produced while executing this intent, "
            "such as ChangeRequest, ConfigRender, and ExecutionPlan records."
        ),
    )


class SiteIntent(BaseIntent):
    """Intent artifact for a site-scoped change that may target many devices.

    Examples
    --------
    - Roll out VLAN 300 to all access switches at site HQ.
    - Apply a new ACL policy to every edge device at Branch-A.
    """

    intent_type: Literal["site"] = "site"
    domain: NetworkDomain | None = Field(
        default=None,
        description="Primary network domain for this site intent, e.g. vlan or acl",
    )


class TopologyIntent(BaseIntent):
    """Intent artifact for topology-level changes spanning sites or the full network.

    Examples
    --------
    - Re-address the core routing layer across all sites.
    - Migrate WAN links from OSPF to BGP.
    """

    intent_type: Literal["topology"] = "topology"
    topology_changes: list[str] = Field(
        default_factory=list,
        description="High-level descriptions of each topology change included in this intent",
    )


class IPAMIntent(BaseIntent):
    """Intent artifact for IP address management workflows.

    Examples
    --------
    - Allocate a /24 from the corporate pool for a new building.
    - Reclaim and reassign the 10.10.5.0/24 prefix.
    """

    intent_type: Literal["ipam"] = "ipam"
    prefix_requested: str | None = Field(
        default=None,
        description="CIDR prefix requested or under management (e.g. '10.10.5.0/24')",
    )
    assignment_type: str | None = Field(
        default=None,
        description="Type of address assignment, e.g. loopback, management, server",
    )


class ProvisioningIntent(BaseIntent):
    """Intent artifact for device or service provisioning workflows.

    Examples
    --------
    - Onboard five new access switches at site HQ.
    - Bootstrap a new firewall pair with baseline config.
    """

    intent_type: Literal["provisioning"] = "provisioning"
    devices_to_provision: list[str] = Field(
        default_factory=list,
        description="Hostnames or identifiers of devices to be provisioned",
    )
    target_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Target configuration state to be applied during provisioning",
    )
