from typing import Protocol

from ..models.ipam import IpamAddressAssignment, IpamPrefix


class IPAMAdapter(Protocol):
    """Read-only IPAM adapter contract."""

    def list_prefixes(self) -> list[IpamPrefix]:
        """Return known prefixes."""

    def list_assignments(self) -> list[IpamAddressAssignment]:
        """Return known IP assignments."""
