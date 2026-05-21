"""Tests for deterministic deduplication of resource refs and relationships.

Covers:
- canonical_key() identity on resource refs
- canonical_key() identity on relationship models
- _merge_unique_resources deduplication
- _merge_unique_relationships deduplication
- regression test for the run-f83a3df1 duplicate scenario
"""

from net_agent_harness.main import _merge_unique_relationships, _merge_unique_resources
from net_agent_harness.models.resources import (
    DeviceResourceRef,
    InterfaceResourceRef,
    InterfaceToSubnetRelationship,
    SiteResourceRef,
    SiteToDeviceRelationship,
    SubnetResourceRef,
    TopologyLinkResourceRef,
    DeviceToTopologyLinkRelationship,
    VlanResourceRef,
)


# ── canonical_key tests ──────────────────────────────────────────────────────


class TestResourceRefCanonicalKey:
    def test_site_key(self) -> None:
        ref = SiteResourceRef(site_name="HQ")
        assert ref.canonical_key() == "site:HQ"

    def test_device_key_ignores_site_name(self) -> None:
        a = DeviceResourceRef(device_name="sw1", site_name=None)
        b = DeviceResourceRef(device_name="sw1", site_name="HQ")
        assert a.canonical_key() == b.canonical_key()

    def test_device_key_distinct(self) -> None:
        a = DeviceResourceRef(device_name="sw1")
        b = DeviceResourceRef(device_name="sw2")
        assert a.canonical_key() != b.canonical_key()

    def test_interface_key(self) -> None:
        ref = InterfaceResourceRef(device_name="sw1", interface_name="ge-0/0/1")
        assert ref.canonical_key() == "interface:sw1:ge-0/0/1"

    def test_vlan_key(self) -> None:
        ref = VlanResourceRef(vlan_id=23, site_name="HQ")
        assert ref.canonical_key() == "vlan:23"

    def test_topology_link_key_direction_independent(self) -> None:
        a = TopologyLinkResourceRef(endpoint_a_device="sw1", endpoint_b_device="sw2")
        b = TopologyLinkResourceRef(endpoint_a_device="sw2", endpoint_b_device="sw1")
        assert a.canonical_key() == b.canonical_key()


class TestRelationshipCanonicalKey:
    def test_site_to_device_ignores_device_site_name(self) -> None:
        """Same site+device with different site_name on device ref → same key."""
        a = SiteToDeviceRelationship(
            site=SiteResourceRef(site_name="HQ"),
            device=DeviceResourceRef(device_name="sw1", site_name=None),
        )
        b = SiteToDeviceRelationship(
            site=SiteResourceRef(site_name="HQ"),
            device=DeviceResourceRef(device_name="sw1", site_name="HQ"),
        )
        assert a.canonical_key() == b.canonical_key()

    def test_site_to_device_distinct_devices(self) -> None:
        a = SiteToDeviceRelationship(
            site=SiteResourceRef(site_name="HQ"),
            device=DeviceResourceRef(device_name="sw1"),
        )
        b = SiteToDeviceRelationship(
            site=SiteResourceRef(site_name="HQ"),
            device=DeviceResourceRef(device_name="fw1"),
        )
        assert a.canonical_key() != b.canonical_key()

    def test_interface_to_subnet_key(self) -> None:
        rel = InterfaceToSubnetRelationship(
            interface=InterfaceResourceRef(device_name="sw1", interface_name="ge-0/0/1"),
            subnet=SubnetResourceRef(cidr="10.10.20.0/24"),
        )
        assert "sw1" in rel.canonical_key()
        assert "10.10.20.0/24" in rel.canonical_key()

    def test_device_to_topology_link_key_direction_independent(self) -> None:
        a = DeviceToTopologyLinkRelationship(
            device=DeviceResourceRef(device_name="sw1"),
            topology_link=TopologyLinkResourceRef(
                endpoint_a_device="sw1", endpoint_b_device="sw2"
            ),
        )
        b = DeviceToTopologyLinkRelationship(
            device=DeviceResourceRef(device_name="sw1"),
            topology_link=TopologyLinkResourceRef(
                endpoint_a_device="sw2", endpoint_b_device="sw1"
            ),
        )
        assert a.canonical_key() == b.canonical_key()


# ── merge deduplication tests ─────────────────────────────────────────────────


class TestMergeUniqueResources:
    def test_dedup_device_refs_with_different_site_name(self) -> None:
        """DeviceResourceRef with site_name=None and site_name='HQ' → one entry."""
        planned = [DeviceResourceRef(device_name="sw1", site_name=None)]
        authoritative = [DeviceResourceRef(device_name="sw1", site_name="HQ")]
        merged = _merge_unique_resources(planned, authoritative)
        assert len(merged) == 1
        # Authoritative wins
        assert merged[0].site_name == "HQ"  # type: ignore[union-attr]

    def test_distinct_resources_preserved(self) -> None:
        planned = [SiteResourceRef(site_name="HQ")]
        authoritative = [DeviceResourceRef(device_name="sw1", site_name="HQ")]
        merged = _merge_unique_resources(planned, authoritative)
        assert len(merged) == 2


class TestMergeUniqueRelationships:
    def test_dedup_site_to_device_with_different_device_site_name(self) -> None:
        """The exact run-f83a3df1 scenario: planner emits device with site_name=null,
        orchestration emits with site_name='HQ'. Should collapse to one."""
        planned = [
            SiteToDeviceRelationship(
                site=SiteResourceRef(site_name="HQ"),
                device=DeviceResourceRef(device_name="sw1", site_name=None),
            ),
            SiteToDeviceRelationship(
                site=SiteResourceRef(site_name="HQ"),
                device=DeviceResourceRef(device_name="fw1", site_name=None),
            ),
        ]
        authoritative = [
            SiteToDeviceRelationship(
                site=SiteResourceRef(site_name="HQ"),
                device=DeviceResourceRef(device_name="sw1", site_name="HQ"),
            ),
            SiteToDeviceRelationship(
                site=SiteResourceRef(site_name="HQ"),
                device=DeviceResourceRef(device_name="fw1", site_name="HQ"),
            ),
        ]
        merged = _merge_unique_relationships(planned, authoritative)
        assert len(merged) == 2
        # Authoritative entries win (device.site_name populated)
        for rel in merged:
            assert isinstance(rel, SiteToDeviceRelationship)
            assert rel.device.site_name == "HQ"

    def test_identical_relationships_collapsed(self) -> None:
        rel = SiteToDeviceRelationship(
            site=SiteResourceRef(site_name="HQ"),
            device=DeviceResourceRef(device_name="sw1", site_name="HQ"),
        )
        merged = _merge_unique_relationships([rel], [rel])
        assert len(merged) == 1

    def test_distinct_relationships_preserved(self) -> None:
        a = SiteToDeviceRelationship(
            site=SiteResourceRef(site_name="HQ"),
            device=DeviceResourceRef(device_name="sw1"),
        )
        b = SiteToDeviceRelationship(
            site=SiteResourceRef(site_name="HQ"),
            device=DeviceResourceRef(device_name="fw1"),
        )
        merged = _merge_unique_relationships([a], [b])
        assert len(merged) == 2

    def test_order_preserving_authoritative_first(self) -> None:
        """Authoritative entries appear first in the merged list."""
        planned = [
            SiteToDeviceRelationship(
                site=SiteResourceRef(site_name="HQ"),
                device=DeviceResourceRef(device_name="fw1", site_name=None),
            ),
        ]
        authoritative = [
            SiteToDeviceRelationship(
                site=SiteResourceRef(site_name="HQ"),
                device=DeviceResourceRef(device_name="sw1", site_name="HQ"),
            ),
        ]
        merged = _merge_unique_relationships(planned, authoritative)
        assert len(merged) == 2
        # Authoritative sw1 first, then planned fw1
        assert merged[0].device.device_name == "sw1"  # type: ignore[union-attr]
        assert merged[1].device.device_name == "fw1"  # type: ignore[union-attr]
