from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings
from ..models.inventory import InventorySnapshot
from ..policies.approvals import (
    WriteApprovalContext,
    WriteCapability,
    deny_unimplemented_write,
)


class InventoryWriteRequest(BaseModel):
    """Approved future-write payload for an inventory source of truth."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Human-readable summary of the inventory update.")
    snapshot: InventorySnapshot = Field(
        description="Desired inventory snapshot or patch to commit once writes are enabled."
    )


class InventoryAdapter(Protocol):
    """Inventory adapter contract with policy-gated future write hooks."""

    def write_inventory_snapshot(
        self,
        request: InventoryWriteRequest,
        *,
        approval: WriteApprovalContext,
        s: Settings | None = None,
    ) -> None:
        """Apply an approved inventory write once deliberate implementations are enabled."""


class GuardedInventoryWriteAdapter:
    """Default deny-by-policy implementation for future inventory writes."""

    def write_inventory_snapshot(
        self,
        request: InventoryWriteRequest,
        *,
        approval: WriteApprovalContext,
        s: Settings | None = None,
    ) -> None:
        _ = request
        deny_unimplemented_write(WriteCapability.INVENTORY, approval, s=s)
