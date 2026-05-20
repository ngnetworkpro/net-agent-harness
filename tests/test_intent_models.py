"""Tests for intent artifact models (desired-state intent artifacts issue)."""

import pytest
from pydantic import ValidationError

from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import IntentStatus, NetworkDomain
from net_agent_harness.models.intent import (
    ArtifactRef,
    IPAMIntent,
    ProvisioningIntent,
    SiteIntent,
    TopologyIntent,
)


def _meta(run_id: str = "run-intent-1") -> ArtifactMeta:
    return ArtifactMeta(
        run_id=run_id,
        artifact_id=f"intent-{run_id}",
        created_by="test",
    )


def _scope(site: str = "HQ") -> ScopeRef:
    return ScopeRef(site=site)


# ---------------------------------------------------------------------------
# ArtifactRef
# ---------------------------------------------------------------------------


class TestArtifactRef:
    def test_valid_ref(self):
        ref = ArtifactRef(
            artifact_id="change-run-1",
            artifact_type="change_request",
            run_id="run-1",
        )
        assert ref.artifact_id == "change-run-1"
        assert ref.description is None

    def test_with_description(self):
        ref = ArtifactRef(
            artifact_id="render-run-1",
            artifact_type="config_render",
            run_id="run-1",
            description="VLAN 300 render for sw1",
        )
        assert ref.description == "VLAN 300 render for sw1"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ArtifactRef(
                artifact_id="x",
                artifact_type="change_request",
                run_id="run-1",
                unexpected="oops",
            )


# ---------------------------------------------------------------------------
# BaseIntent shared fields
# ---------------------------------------------------------------------------


class TestBaseIntentSharedFields:
    """BaseIntent cannot be instantiated directly (no intent_type literal),
    so we verify shared-field behaviour through SiteIntent."""

    def test_defaults(self):
        intent = SiteIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Roll out VLAN 300 at HQ",
        )
        assert intent.assumptions == []
        assert intent.dependencies == []
        assert intent.constraints == []
        assert intent.desired_state == {}
        assert intent.approval_required is False
        assert intent.approval_notes is None
        assert intent.status is IntentStatus.DRAFT
        assert intent.child_artifacts == []

    def test_full_shared_fields(self):
        ref = ArtifactRef(
            artifact_id="change-run-2",
            artifact_type="change_request",
            run_id="run-2",
        )
        intent = SiteIntent(
            meta=_meta("run-2"),
            scope=ScopeRef(site="HQ", device_names=["sw1", "sw2"]),
            summary="Migrate VLAN 100 to VLAN 200 at HQ",
            assumptions=["VLAN 100 is not in use after migration"],
            dependencies=["ticket-4321"],
            desired_state={"vlan_200_present": True, "vlan_100_absent": True},
            constraints=["No changes before 22:00"],
            approval_required=True,
            approval_notes="Network lead must sign off",
            status=IntentStatus.APPROVED,
            child_artifacts=[ref],
        )
        assert intent.scope.site == "HQ"
        assert "ticket-4321" in intent.dependencies
        assert intent.approval_required is True
        assert intent.status is IntentStatus.APPROVED
        assert len(intent.child_artifacts) == 1
        assert intent.child_artifacts[0].artifact_type == "change_request"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            SiteIntent(
                meta=_meta(),
                scope=_scope(),
                summary="Test",
                invented_field="should fail",
            )

    def test_status_enum_values(self):
        for value in ("draft", "approved", "in_progress", "completed", "blocked", "cancelled"):
            intent = SiteIntent(
                meta=_meta(),
                scope=_scope(),
                summary="Test",
                status=value,
            )
            assert intent.status.value == value

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            SiteIntent(
                meta=_meta(),
                scope=_scope(),
                summary="Test",
                status="pending",
            )


# ---------------------------------------------------------------------------
# SiteIntent
# ---------------------------------------------------------------------------


class TestSiteIntent:
    def test_default_intent_type(self):
        intent = SiteIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Deploy VLAN 300 at HQ",
        )
        assert intent.intent_type == "site"
        assert intent.domain is None

    def test_with_domain(self):
        intent = SiteIntent(
            meta=_meta(),
            scope=_scope(),
            summary="ACL rollout at HQ",
            domain=NetworkDomain.ACL,
        )
        assert intent.domain is NetworkDomain.ACL

    def test_multiple_child_refs(self):
        refs = [
            ArtifactRef(artifact_id=f"change-{i}", artifact_type="change_request", run_id=f"run-{i}")
            for i in range(3)
        ]
        intent = SiteIntent(
            meta=_meta(),
            scope=ScopeRef(site="HQ", device_names=["sw1", "sw2", "sw3"]),
            summary="Site-wide VLAN 300 rollout",
            child_artifacts=refs,
        )
        assert len(intent.child_artifacts) == 3

    def test_serialisation_round_trip(self):
        intent = SiteIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Round-trip test",
            domain=NetworkDomain.VLAN,
        )
        data = intent.model_dump()
        restored = SiteIntent.model_validate(data)
        assert restored.summary == intent.summary
        assert restored.domain is NetworkDomain.VLAN


# ---------------------------------------------------------------------------
# TopologyIntent
# ---------------------------------------------------------------------------


class TestTopologyIntent:
    def test_defaults(self):
        intent = TopologyIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Re-address the core routing layer",
        )
        assert intent.intent_type == "topology"
        assert intent.topology_changes == []

    def test_with_topology_changes(self):
        intent = TopologyIntent(
            meta=_meta(),
            scope=ScopeRef(region="US-West"),
            summary="Migrate WAN links from OSPF to BGP",
            topology_changes=[
                "Replace OSPF process 1 with BGP AS 65001",
                "Redistribute connected networks into BGP",
            ],
        )
        assert len(intent.topology_changes) == 2
        assert "BGP" in intent.topology_changes[0]

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            TopologyIntent(
                meta=_meta(),
                scope=_scope(),
                summary="Test",
                unknown_key="oops",
            )


# ---------------------------------------------------------------------------
# IPAMIntent
# ---------------------------------------------------------------------------


class TestIPAMIntent:
    def test_defaults(self):
        intent = IPAMIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Allocate a /24 for new building",
        )
        assert intent.intent_type == "ipam"
        assert intent.prefix_requested is None
        assert intent.assignment_type is None

    def test_with_prefix_and_type(self):
        intent = IPAMIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Allocate management prefix",
            prefix_requested="10.10.5.0/24",
            assignment_type="management",
        )
        assert intent.prefix_requested == "10.10.5.0/24"
        assert intent.assignment_type == "management"

    def test_child_artifacts_config_render(self):
        ref = ArtifactRef(
            artifact_id="render-ipam-1",
            artifact_type="config_render",
            run_id="run-ipam-1",
        )
        intent = IPAMIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Assign /24 and configure gateway",
            child_artifacts=[ref],
        )
        assert intent.child_artifacts[0].artifact_type == "config_render"


# ---------------------------------------------------------------------------
# ProvisioningIntent
# ---------------------------------------------------------------------------


class TestProvisioningIntent:
    def test_defaults(self):
        intent = ProvisioningIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Onboard 5 new access switches at HQ",
        )
        assert intent.intent_type == "provisioning"
        assert intent.devices_to_provision == []
        assert intent.target_state == {}

    def test_with_devices_and_target_state(self):
        intent = ProvisioningIntent(
            meta=_meta(),
            scope=ScopeRef(site="HQ", device_names=["sw10", "sw11"]),
            summary="Bootstrap new access switches",
            devices_to_provision=["sw10", "sw11"],
            target_state={
                "vlans": [100, 200, 300],
                "management_vlan": 999,
            },
        )
        assert "sw10" in intent.devices_to_provision
        assert intent.target_state["management_vlan"] == 999

    def test_serialisation_round_trip(self):
        intent = ProvisioningIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Provision test",
            devices_to_provision=["sw1"],
            target_state={"baseline": True},
        )
        data = intent.model_dump()
        restored = ProvisioningIntent.model_validate(data)
        assert restored.devices_to_provision == ["sw1"]
        assert restored.target_state["baseline"] is True


# ---------------------------------------------------------------------------
# Relationship to lower-level artifacts: all ref types
# ---------------------------------------------------------------------------


class TestChildArtifactRelationships:
    """A single intent can reference ChangeRequest, ConfigRender, ExecutionPlan artifacts."""

    def test_intent_references_multiple_artifact_types(self):
        refs = [
            ArtifactRef(artifact_id="cr-1", artifact_type="change_request", run_id="run-1"),
            ArtifactRef(artifact_id="cr-2", artifact_type="change_request", run_id="run-2"),
            ArtifactRef(artifact_id="render-1", artifact_type="config_render", run_id="run-1"),
            ArtifactRef(artifact_id="ep-1", artifact_type="execution_plan", run_id="run-1"),
        ]
        intent = SiteIntent(
            meta=_meta(),
            scope=_scope(),
            summary="Multi-device VLAN rollout",
            child_artifacts=refs,
        )
        types = {r.artifact_type for r in intent.child_artifacts}
        assert "change_request" in types
        assert "config_render" in types
        assert "execution_plan" in types

    def test_intent_is_persistable_as_json(self):
        """Verify the model produces clean JSON suitable for ArtifactStore.save_model."""
        intent = SiteIntent(
            meta=_meta(),
            scope=ScopeRef(site="HQ", device_names=["sw1"]),
            summary="Persistable intent",
            domain=NetworkDomain.VLAN,
            child_artifacts=[
                ArtifactRef(artifact_id="cr-1", artifact_type="change_request", run_id="run-1"),
            ],
        )
        json_str = intent.model_dump_json(indent=2)
        assert "persistable intent" in json_str.lower()
        assert "change_request" in json_str
