from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings
from ..models.topology import TopologyUpdatePlan
from ..policies.approvals import (
    WriteApprovalContext,
    WriteCapability,
    deny_unimplemented_write,
)


class TopologyWriteRequest(BaseModel):
    """Approved future-write payload for a topology source of truth."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Human-readable summary of the topology update.")
    plan: TopologyUpdatePlan = Field(
        description="Topology plan that would be committed once write support is enabled."
    )


class TopologyAdapter(Protocol):
    """Topology adapter contract with policy-gated future write hooks."""

    def apply_topology_update(
        self,
        request: TopologyWriteRequest,
        *,
        approval: WriteApprovalContext,
        s: Settings | None = None,
    ) -> None:
        """Apply an approved topology write once deliberate implementations are enabled."""


class GuardedTopologyWriteAdapter:
    """Default deny-by-policy implementation for future topology writes."""

    def apply_topology_update(
        self,
        request: TopologyWriteRequest,
        *,
        approval: WriteApprovalContext,
        s: Settings | None = None,
    ) -> None:
        _ = request
        deny_unimplemented_write(WriteCapability.TOPOLOGY, approval, s=s)
