from net_agent_harness.models.changes import ChangeRequest, RequestedChange
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk
from net_agent_harness.tools.config_tools import build_stub_config_render


def test_build_stub_config_render():
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

    render = build_stub_config_render(change_request)
    assert render.snippets[0].device_name == "sw1"
    assert any("vlan 220" in cmd for cmd in render.snippets[0].commands)
