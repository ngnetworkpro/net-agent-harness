from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan, PlanDecision
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk, NetworkDomain, PlanDecisionType
from net_agent_harness.orchestration.coordinator import StageCoordinator
from net_agent_harness.services.artifact_store import ArtifactStore


from unittest.mock import patch, AsyncMock
from net_agent_harness.models.artifacts import ConfigRenderOutput, ConfigSnippet
from net_agent_harness.models.enums import RenderBackendType, RenderRole

import pytest

@pytest.mark.asyncio
@patch("net_agent_harness.orchestration.coordinator.change_render_agent.run", new_callable=AsyncMock)
async def test_stage_coordinator_pipeline_api_backend(mock_run, tmp_path, monkeypatch):
    """When backend is direct_api with a supported platform, the LLM agent is used."""
    from net_agent_harness.config import settings
    monkeypatch.setattr(settings, "execution_backend", "direct_api")

    mock_run.return_value.output = ConfigRenderOutput(
        summary="Test Render",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                rendered_text="{}",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
            )
        ],
    )
    store = ArtifactStore(tmp_path)
    coordinator = StageCoordinator(store)
    change_request = ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="change-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            requested_by="tester",
            intent="Add VLAN 220 to access switch sw1 at HQ",
        ),
        target_scope="device",
        rollback_plan=RollbackPlan(
            summary="Revert",
            trigger_conditions=["Error"],
            rollback_steps=["Undo"]
        ),
        risk=ChangeRisk.LOW,
        plan_decision=PlanDecision(decision=PlanDecisionType.APPLY, reason="test", diff=[])
    )

    summary = await coordinator.run_pipeline(change_request)
    assert summary["status"] in {"pass", "warn", "fail"}
    assert "run_summary" in summary["artifacts"]
    assert "config_render" in summary["artifacts"]
    assert "validation_report" in summary["artifacts"]
    mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_stage_coordinator_terraform_skips_llm(tmp_path, monkeypatch):
    """When backend is terraform, the LLM render agent must NOT be called."""
    from net_agent_harness.config import settings
    from net_agent_harness.models.changes import (
        DeviceChange, VlanChange, VlanSpec, PortSpec, ResolvedTarget,
    )

    monkeypatch.setattr(settings, "execution_backend", "terraform")
    monkeypatch.setattr(settings, "terraform_render_source", "local")

    # Create local terraform source files
    source_dir = tmp_path / "tf-source"
    source_dir.mkdir()
    (source_dir / "mist_networks.json").write_text('{"Access": {"vlan_id": "11"}}')
    (source_dir / "mist.tf").write_text('resource "mist_org_networktemplate" "offices" {}')
    monkeypatch.setattr(settings, "terraform_source_dir", str(source_dir))
    monkeypatch.setattr(settings, "terraform_source_networks_file", "mist_networks.json")
    monkeypatch.setattr(settings, "terraform_source_template_file", "mist.tf")

    store = ArtifactStore(tmp_path / "artifacts")
    coordinator = StageCoordinator(store)
    change_request = ChangeRequest(
        meta=ArtifactMeta(run_id="run-tf", artifact_id="cr-tf", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            requested_by="tester",
            intent="Add VLAN 220 to access switch sw1 at HQ",
        ),
        target_scope="device",
        resolved_targets=[ResolvedTarget(name="sw1", platform="mist")],
        rollback_plan=RollbackPlan(summary="Revert"),
        risk=ChangeRisk.LOW,
        plan_decision=PlanDecision(
            decision=PlanDecisionType.APPLY,
            reason="test",
            diff=[
                DeviceChange(
                    device="sw1",
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[VlanSpec(id=220, name="Engineering")],
                        ports_to_update=[PortSpec(interface="ge-0/0/1", vlan_id=220, mode="access")],
                    ),
                ),
            ],
        ),
    )

    render_result, render_path = await coordinator.render(change_request)

    # Must produce real Terraform HCL, not LLM output
    primary_snippets = [
        s for s in render_result.snippets
        if s.render_role == RenderRole.PRIMARY
    ]
    assert len(primary_snippets) == 1
    assert primary_snippets[0].backend_type == RenderBackendType.TERRAFORM
    assert "locals {" in primary_snippets[0].rendered_text
    assert "resource " in primary_snippets[0].rendered_text

    # Must have a CLI fallback with real commands
    fallback_snippets = [
        s for s in render_result.snippets
        if s.render_role == RenderRole.FALLBACK
    ]
    assert len(fallback_snippets) == 1
    assert fallback_snippets[0].backend_type == RenderBackendType.CLI
    assert "vlan 220" in fallback_snippets[0].rendered_text
    assert "set interfaces ge-0/0/1" in fallback_snippets[0].rendered_text
