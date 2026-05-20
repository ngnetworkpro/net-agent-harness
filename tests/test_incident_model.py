"""Tests for IncidentEvidence and IncidentSummary models (Issue #51)."""
import pytest
from pydantic import ValidationError

from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.incident import IncidentEvidence, IncidentSummary


def _meta(run_id: str = "run-inc-1") -> ArtifactMeta:
    return ArtifactMeta(
        run_id=run_id,
        artifact_id=f"art-{run_id}",
        created_by="test",
    )


def _scope() -> ScopeRef:
    return ScopeRef(site="HQ", device_names=["sw1"])


class TestIncidentEvidence:
    def test_defaults_are_empty(self):
        evidence = IncidentEvidence()
        assert evidence.logs == []
        assert evidence.recent_changes == []
        assert evidence.validation_artifacts == []
        assert evidence.device_facts == {}

    def test_accepts_log_lines(self):
        evidence = IncidentEvidence(logs=["Dec 10 sw1: link down", "Dec 10 sw1: STP change"])
        assert len(evidence.logs) == 2

    def test_accepts_device_facts(self):
        evidence = IncidentEvidence(
            device_facts={"sw1": {"interfaces": ["ge-0/0/1"], "vlans": [10, 20]}}
        )
        assert "sw1" in evidence.device_facts

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            IncidentEvidence(unexpected="nope")  # type: ignore[call-arg]


class TestIncidentSummary:
    def test_minimal_creation(self):
        summary = IncidentSummary(
            meta=_meta(),
            scope=_scope(),
            title="Link failure on sw1",
            summary="The uplink on sw1 went down at 14:00 UTC.",
        )
        assert summary.title == "Link failure on sw1"
        assert summary.severity == "unknown"
        assert summary.affected_devices == []
        assert summary.findings == []
        assert summary.recommended_actions == []
        assert summary.related_change_run_ids == []

    def test_full_creation(self):
        evidence = IncidentEvidence(
            logs=["14:00 link down"],
            recent_changes=["run-change-123"],
            validation_artifacts=["art-val-1"],
            device_facts={"sw1": {"uptime": "5d"}},
        )
        summary = IncidentSummary(
            meta=_meta(),
            scope=_scope(),
            title="Uplink failure",
            summary="sw1 uplink went down due to cable fault.",
            severity="high",
            affected_devices=["sw1"],
            impact_description="Access switches behind sw1 lost connectivity.",
            findings=["Cable fault on ge-0/0/0", "STP topology change observed"],
            recommended_actions=["Replace cable on ge-0/0/0", "Verify STP topology"],
            evidence=evidence,
            related_change_run_ids=["run-change-123"],
        )
        assert summary.severity == "high"
        assert len(summary.findings) == 2
        assert len(summary.recommended_actions) == 2
        assert summary.evidence.logs == ["14:00 link down"]
        assert summary.related_change_run_ids == ["run-change-123"]

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            IncidentSummary(
                meta=_meta(),
                scope=_scope(),
                title="test",
                summary="test",
                unexpected="nope",  # type: ignore[call-arg]
            )

    def test_evidence_defaults_when_not_provided(self):
        summary = IncidentSummary(
            meta=_meta(),
            scope=_scope(),
            title="Minor outage",
            summary="Brief connectivity issue.",
        )
        assert isinstance(summary.evidence, IncidentEvidence)
        assert summary.evidence.logs == []

    def test_impact_description_optional(self):
        summary = IncidentSummary(
            meta=_meta(),
            scope=_scope(),
            title="No impact",
            summary="Nothing happened.",
        )
        assert summary.impact_description is None
