from pathlib import Path
from net_agent_harness.models.changes import ChangeRequest, RequestedChange
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk
from net_agent_harness.services.artifact_store import ArtifactStore


def test_save_model(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    model = ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="change-1", created_by="test"),
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            requested_by="tester",
            intent="Add VLAN 220 to sw1",
        ),
        risk=ChangeRisk.LOW,
    )
    path = store.save_model("run-1", "change_request", model)
    assert path.exists()
    assert path.name == "change_request.json"
