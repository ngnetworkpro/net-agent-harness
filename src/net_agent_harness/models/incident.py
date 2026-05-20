"""Incident and review workflow models.

This module defines models for the ``review.incident`` workflow path.
The incident workflow is read-only by default: it consumes evidence
(logs, recent changes, validation artifacts, device facts) and produces
a structured ``IncidentSummary`` artifact without writing any device
configuration.

Artifact filename: ``incidentsummary.json``
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import ArtifactMeta, ScopeRef


class IncidentEvidence(BaseModel):
    """Structured evidence inputs for an incident summary.

    All fields are optional so that partial evidence can be captured
    without blocking the workflow.  Each evidence source is modelled
    as a list of strings or a free-form dict to remain flexible across
    different backend integrations.
    """

    model_config = ConfigDict(extra="forbid")

    logs: list[str] = Field(
        default_factory=list,
        description="Raw or filtered log lines related to the incident",
    )
    recent_changes: list[str] = Field(
        default_factory=list,
        description=(
            "Run IDs or human-readable descriptions of recent changes "
            "that may be related to the incident"
        ),
    )
    validation_artifacts: list[str] = Field(
        default_factory=list,
        description="Artifact IDs or paths for validation reports captured around the incident",
    )
    device_facts: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Keyed device fact snapshots, e.g. "
            "{'sw1': {'interfaces': [...], 'vlans': [...]}}"
        ),
    )


class IncidentSummary(BaseModel):
    """Structured output of an incident review workflow.

    Produced by the ``review.incident`` path after analysing the
    available evidence.  This is a read-only artifact — no device
    configuration is generated or applied.

    Artifact filename: ``incidentsummary.json``
    """

    model_config = ConfigDict(extra="forbid")

    meta: ArtifactMeta
    scope: ScopeRef
    title: str = Field(description="Short title for the incident, e.g. 'Link failure on sw1 uplink'")
    summary: str = Field(description="Human-readable narrative of the incident and its timeline")
    severity: str = Field(
        default="unknown",
        description="Assessed severity: 'critical', 'high', 'medium', 'low', or 'unknown'",
    )
    affected_devices: list[str] = Field(
        default_factory=list,
        description="Hostnames of devices confirmed to be affected",
    )
    impact_description: str | None = Field(
        default=None,
        description="Description of the business or service impact",
    )
    findings: list[str] = Field(
        default_factory=list,
        description="Structured findings from the evidence analysis",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="Recommended remediation or investigation steps",
    )
    evidence: IncidentEvidence = Field(
        default_factory=IncidentEvidence,
        description="Evidence inputs used to produce this summary",
    )
    related_change_run_ids: list[str] = Field(
        default_factory=list,
        description="Run IDs of change workflows that may have contributed to the incident",
    )
