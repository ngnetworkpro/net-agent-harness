from net_agent_harness.models.changes import ChangeRequest, RequestedChange
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk


def test_change_request_model():
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
    assert model.scope.site == "HQ"
