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
async def test_stage_coordinator_pipeline(mock_run, tmp_path):
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
