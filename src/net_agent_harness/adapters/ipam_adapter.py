from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings
from ..models.ipam import IpamAddressAssignment, IpamPrefix, IpamSnapshot
from ..policies.approvals import (
    WriteApprovalContext,
    WriteCapability,
    deny_unimplemented_write,
)


class IPAMWriteRequest(BaseModel):
    """Approved future-write payload for an IPAM source of truth."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Human-readable summary of the IPAM update.")
    snapshot: IpamSnapshot = Field(description="Desired IPAM snapshot delta or reservation set.")


class IPAMAdapter(Protocol):
    """IPAM adapter contract with future write hooks kept gated by policy."""

    def list_prefixes(self) -> list[IpamPrefix]:
        """Return known prefixes."""

    def list_assignments(self) -> list[IpamAddressAssignment]:
        """Return known IP assignments."""

    def write_ipam_snapshot(
        self,
        request: IPAMWriteRequest,
        *,
        approval: WriteApprovalContext,
        s: Settings | None = None,
    ) -> None:
        """Apply an approved IPAM write once deliberate implementations are enabled."""


class GuardedIPAMWriteAdapter:
    """Default deny-by-policy implementation for future IPAM writes."""

    def write_ipam_snapshot(
        self,
        request: IPAMWriteRequest,
        *,
        approval: WriteApprovalContext,
        s: Settings | None = None,
    ) -> None:
        _ = request
        deny_unimplemented_write(WriteCapability.IPAM, approval, s=s)
