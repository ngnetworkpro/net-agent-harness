from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk
from net_agent_harness.orchestration.coordinator import StageCoordinator
from net_agent_harness.services.artifact_store import ArtifactStore


def test_stage_coordinator_pipeline(tmp_path):
    store = ArtifactStore(tmp_path)
    coordinator = StageCoordinator(store)
    change_request = ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="change-1", created_by="test"),
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        domain="vlan",
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
        plan_decision=None, # This mock will need to be properly addressed, but testing pipeline is tricky without mocking the Agent
    )

    from net_agent_harness.models.changes import PlanDecision, DeviceChange, VlanChange, VlanSpec
    from net_agent_harness.models.enums import PlanDecisionType, NetworkDomain
    from net_agent_harness.models.artifacts import ConfigRender, ConfigSnippet
    from unittest.mock import patch

    change_request.plan_decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Test",
        diff=[
            DeviceChange(
                device="sw1",
                domain=NetworkDomain.VLAN,
                changes=VlanChange(
                    vlans_to_create=[VlanSpec(id=220, name="TEST")],
                    ports_to_update=[],
                )
            )
        ]
    )

    # Mock the run_pipeline steps which depend on the agent
    async def mock_render_vlan_config(*args, **kwargs):
        return ConfigRender(
            meta=ArtifactMeta(run_id="run-1", artifact_id="config-render-001", created_by="test"),
            summary="Mock Render",
            snippets=[
                ConfigSnippet(
                    device_name="sw1",
                    cli_commands=["! Candidate config", "vlan 220", "name TEST"],
                )
            ]
        )

    with patch('net_agent_harness.orchestration.coordinator.render_vlan_config', side_effect=mock_render_vlan_config):
        summary = coordinator.run_pipeline(change_request)

    assert summary["status"] in {"pass", "warn", "fail"}
    assert "run_summary" in summary["artifacts"]
    assert "config_render" in summary["artifacts"]
    assert "validation_report" in summary["artifacts"]
