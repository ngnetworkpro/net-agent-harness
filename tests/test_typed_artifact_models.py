"""Tests for new typed artifact models (Issue #47)."""
import pytest

from net_agent_harness.models.artifacts import (
    AnswerArtifact,
    IPAMQueryResult,
    IncidentSummary,
    InventoryQueryResult,
    QueryFinding,
    TopologyQueryResult,
)
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import Capability


def _meta(run_id: str = "run-test") -> ArtifactMeta:
    return ArtifactMeta(
        run_id=run_id,
        artifact_id=f"artifact-{run_id}",
        created_by="test",
    )


class TestQueryFinding:
    def test_valid_finding(self):
        f = QueryFinding(code="NO_LINKS", severity="low", message="No links found.")
        assert f.code == "NO_LINKS"
        assert f.severity == "low"
        assert f.source is None

    def test_finding_with_source(self):
        f = QueryFinding(code="MISSING_IP", severity="medium", message="IP missing.", source="netbox")
        assert f.source == "netbox"

    def test_invalid_severity_rejected(self):
        with pytest.raises(Exception):
            QueryFinding(code="X", severity="unknown", message="bad")


class TestTopologyQueryResult:
    def test_defaults(self):
        result = TopologyQueryResult(
            meta=_meta(),
            question="What connects to sw1?",
            answer="sw1 connects to core1.",
        )
        assert result.capability is Capability.TOPOLOGY
        assert result.confidence == 1.0
        assert result.links == []
        assert result.findings == []
        assert result.evidence == []
        assert result.missing_data == []
        assert result.scope is None

    def test_with_scope_and_links(self):
        scope = ScopeRef(site="HQ", device_names=["sw1"])
        result = TopologyQueryResult(
            meta=_meta(),
            question="Links?",
            answer="Two links found.",
            scope=scope,
            links=[{"source_device": "sw1", "target_device": "core1"}],
            evidence=["inventory"],
            confidence=0.9,
        )
        assert result.scope.site == "HQ"
        assert len(result.links) == 1
        assert result.confidence == 0.9

    def test_confidence_clamped(self):
        with pytest.raises(Exception):
            TopologyQueryResult(meta=_meta(), question="Q", answer="A", confidence=1.5)

    def test_rejects_extra_fields(self):
        with pytest.raises(Exception):
            TopologyQueryResult(
                meta=_meta(), question="Q", answer="A", unexpected_field="oops"
            )


class TestIPAMQueryResult:
    def test_defaults(self):
        result = IPAMQueryResult(
            meta=_meta(),
            question="What is 10.0.0.0/24?",
            answer="Assigned at HQ.",
        )
        assert result.capability is Capability.IPAM
        assert result.prefix is None
        assert result.assignment is None

    def test_with_prefix(self):
        result = IPAMQueryResult(
            meta=_meta(),
            question="CIDR?",
            answer="Found.",
            prefix={"cidr": "10.0.0.0/24", "site": "HQ"},
        )
        assert result.prefix["cidr"] == "10.0.0.0/24"


class TestInventoryQueryResult:
    def test_defaults(self):
        result = InventoryQueryResult(
            meta=_meta(),
            question="List devices at HQ",
            answer="3 devices found.",
        )
        assert result.capability is Capability.TOPOLOGY
        assert result.devices == []

    def test_with_devices(self):
        result = InventoryQueryResult(
            meta=_meta(),
            question="Devices?",
            answer="Found sw1.",
            devices=[{"name": "sw1", "site": "HQ"}],
        )
        assert len(result.devices) == 1


class TestAnswerArtifact:
    def test_minimal(self):
        art = AnswerArtifact(
            meta=_meta(),
            capability=Capability.TOPOLOGY,
            question="Is sw1 up?",
            answer="Yes.",
        )
        assert art.confidence == 1.0
        assert art.scope is None
        assert art.findings == []
        assert art.data == {}

    def test_full(self):
        art = AnswerArtifact(
            meta=_meta(),
            capability=Capability.IPAM,
            question="Who owns 10.0.0.1?",
            answer="sw1",
            scope=ScopeRef(site="HQ"),
            findings=[QueryFinding(code="OK", severity="low", message="Found.")],
            evidence=["ipam"],
            missing_data=["dhcp-range"],
            confidence=0.85,
            data={"ip": "10.0.0.1"},
        )
        assert art.scope.site == "HQ"
        assert len(art.findings) == 1
        assert art.confidence == 0.85


class TestIncidentSummary:
    def test_defaults(self):
        summary = IncidentSummary(
            meta=_meta(),
            title="Link down on sw1",
            description="Interface ge-0/0/1 went down.",
        )
        assert summary.capability is Capability.INCIDENT
        assert summary.severity == "medium"
        assert summary.affected_devices == []
        assert summary.recommended_actions == []

    def test_full(self):
        summary = IncidentSummary(
            meta=_meta(),
            title="Incident",
            description="Desc",
            scope=ScopeRef(site="HQ"),
            affected_devices=["sw1", "sw2"],
            findings=[QueryFinding(code="LINK_DOWN", severity="high", message="Down.")],
            evidence=["syslog"],
            missing_data=["SNMP traps"],
            severity="high",
            confidence=0.8,
            recommended_actions=["Bounce interface"],
        )
        assert summary.severity == "high"
        assert len(summary.affected_devices) == 2
        assert summary.confidence == 0.8
