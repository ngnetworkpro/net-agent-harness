from ..models.ipam import IpamAddressAssignment, IpamPrefix
from .ipam_adapter import GuardedIPAMWriteAdapter


class MockIPAMAdapter(GuardedIPAMWriteAdapter):
    """Read-only seeded IPAM data for local development."""

    def __init__(self) -> None:
        self._prefixes = [
            IpamPrefix(cidr="10.0.0.0/24", site="HQ", vlan_id=1, role="management"),
            IpamPrefix(cidr="10.10.11.0/24", site="HQ", vlan_id=11, role="users"),
            IpamPrefix(cidr="10.10.21.0/24", site="HQ", vlan_id=21, role="printers"),
            IpamPrefix(cidr="10.10.31.0/24", site="HQ", vlan_id=31, role="security"),
        ]
        self._assignments = [
            IpamAddressAssignment(
                address="10.0.0.1/24",
                device_name="fw1",
                interface="LAN5",
                dns_name="fw1.hq.example.com",
            ),
            IpamAddressAssignment(
                address="10.0.0.10/24",
                device_name="sw1",
                interface="vlan.1",
                dns_name="sw1.hq.example.com",
            ),
            IpamAddressAssignment(
                address="10.10.21.12/24",
                device_name="printer-1",
                interface="eth0",
                dns_name="printer-1.hq.example.com",
            ),
            IpamAddressAssignment(
                address="10.10.31.50/24",
                device_name="camera-1",
                interface="eth0",
                dns_name="camera-1.hq.example.com",
            ),
        ]

    def list_prefixes(self) -> list[IpamPrefix]:
        return self._prefixes.copy()

    def list_assignments(self) -> list[IpamAddressAssignment]:
        return self._assignments.copy()
