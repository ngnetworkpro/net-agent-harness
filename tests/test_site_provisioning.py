"""Tests for SiteProvisioningIntent model (Issue #59)."""
import pytest
from pydantic import ValidationError

from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import IntentStatus
from net_agent_harness.models.intent import ArtifactRef
from net_agent_harness.models.site_provisioning import SiteProvisioningIntent, SubnetAllocation


def _meta(run_id: str = "run-site-1") -> ArtifactMeta:
    return ArtifactMeta(run_id=run_id, artifact_id=f"art-{run_id}", created_by="test")


def _scope() -> ScopeRef:
    return ScopeRef(site="BRANCH-07")


class TestSubnetAllocation:
    def test_minimal_allocation(self):
        alloc = SubnetAllocation(purpose="management")
        assert alloc.purpose == "management"
        assert alloc.prefix is None
        assert alloc.vlan_id is None
        assert alloc.prefix_allocation_run_id is None

    def test_with_prefix_and_vlan(self):
        alloc = SubnetAllocation(purpose="servers", prefix="10.10.5.0/24", vlan_id=100)
        assert alloc.prefix == "10.10.5.0/24"
        assert alloc.vlan_id == 100

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            SubnetAllocation(purpose="mgmt", unexpected="nope")  # type: ignore[call-arg]


class TestSiteProvisioningIntent:
    def test_minimal_creation(self):
        intent = SiteProvisioningIntent(
            meta=_meta(),
            scope=_scope(),
            site_name="BRANCH-07",
            summary="Provision new branch office site",
        )
        assert intent.site_name == "BRANCH-07"
        assert intent.summary == "Provision new branch office site"
        assert intent.status == IntentStatus.DRAFT
        assert intent.subnet_allocations == []
        assert intent.vlan_assignments == []
        assert intent.device_roles == []
        assert intent.child_artifacts == []
        assert intent.ipam_allocation_run_id is None
        assert intent.topology_plan_run_id is None
        assert intent.change_plan_run_ids == []

    def test_full_creation(self):
        intent = SiteProvisioningIntent(
            meta=_meta(),
            scope=_scope(),
            site_name="BRANCH-07",
            summary="Full site provisioning",
            subnet_allocations=[
                SubnetAllocation(purpose="management", prefix="10.7.0.0/24", vlan_id=10),
                SubnetAllocation(purpose="servers", prefix="10.7.1.0/24", vlan_id=20),
            ],
            vlan_assignments=[10, 20, 30],
            device_roles=["core", "access", "firewall"],
            template_name="standard-branch-v2",
            assumptions=["Site has existing internet circuit"],
            constraints=["No maintenance window before 18:00"],
            status=IntentStatus.IN_PROGRESS,
            ipam_allocation_run_id="run-ipam-abc",
            topology_plan_run_id="run-topo-def",
            change_plan_run_ids=["run-change-001", "run-change-002"],
        )
        assert len(intent.subnet_allocations) == 2
        assert len(intent.vlan_assignments) == 3
        assert intent.template_name == "standard-branch-v2"
        assert intent.status == IntentStatus.IN_PROGRESS
        assert intent.ipam_allocation_run_id == "run-ipam-abc"
        assert intent.topology_plan_run_id == "run-topo-def"
        assert len(intent.change_plan_run_ids) == 2

    def test_child_artifacts_can_be_linked(self):
        ref = ArtifactRef(
            artifact_id="art-ipam-1",
            artifact_type="prefix_allocation_plan",
            run_id="run-ipam-abc",
            description="IPAM allocation for management subnet",
        )
        intent = SiteProvisioningIntent(
            meta=_meta(),
            scope=_scope(),
            site_name="BRANCH-07",
            summary="Site with child refs",
            child_artifacts=[ref],
        )
        assert len(intent.child_artifacts) == 1
        assert intent.child_artifacts[0].artifact_type == "prefix_allocation_plan"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            SiteProvisioningIntent(
                meta=_meta(),
                scope=_scope(),
                site_name="X",
                summary="X",
                unexpected="nope",  # type: ignore[call-arg]
            )

    def test_desired_state_defaults_to_empty_dict(self):
        intent = SiteProvisioningIntent(
            meta=_meta(), scope=_scope(), site_name="B1", summary="test"
        )
        assert intent.desired_state == {}
