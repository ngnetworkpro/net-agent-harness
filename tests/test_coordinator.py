from net_agent_harness.models.changes import ChangeRequest, RequestedChange
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
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            requested_by="tester",
            intent="Add VLAN 220 to access switch sw1 at HQ",
        ),
        risk=ChangeRisk.LOW,
    )

    summary = coordinator.run_pipeline(change_request)
    assert summary["status"] in {"pass", "warn", "fail"}
    assert "run_summary" in summary["artifacts"]
