import pytest
from unittest.mock import patch

from net_agent_harness.adapters.backends.direct_api import DirectAPIBackendAdapter
from net_agent_harness.models.artifacts import ArtifactMeta
from net_agent_harness.models.changes import ChangeRequest, PlanDecision, DeviceChange, VlanChange, VlanSpec, PortSpec, ResolvedTarget
from net_agent_harness.models.enums import DeviceVendor, NetworkDomain, PlanDecisionType, RenderBackendType, RenderRole

@pytest.fixture
def adapter():
    return DirectAPIBackendAdapter()

@pytest.fixture
def change_request():
    return ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="cr-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope={"site": "HQ", "device_names": ["sw1"]},
        requested_change={"summary": "Add VLAN", "intent": "Add VLAN to switch", "requested_by": "test"},
        target_scope="device",
        risk="low",
        rollback_plan={"summary": "none"},
        resolved_targets=[
            ResolvedTarget(name="sw1", platform="mist", vendor=DeviceVendor.JUNIPER)
        ],
        plan_decision=PlanDecision(
            decision=PlanDecisionType.APPLY,
            reason="test apply",
            diff=[
                DeviceChange(
                    device="sw1",
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[VlanSpec(id=10, name="users")],
                        ports_to_update=[PortSpec(interface="ge-0/0/1", vlan_id=10, mode="access")]
                    )
                )
            ]
        )
    )

@pytest.mark.asyncio
async def test_direct_api_render_returns_api_primary_snippets(adapter, change_request):
    render_output = await adapter.render(change_request)
    
    assert render_output.snippets
    primary_snippets = [s for s in render_output.snippets if s.render_role == RenderRole.PRIMARY]
    assert len(primary_snippets) == 1
    
    snippet = primary_snippets[0]
    assert snippet.device_name == "sw1"
    assert snippet.backend_type == RenderBackendType.API
    assert snippet.api_payload is not None
    assert snippet.commands == []

@pytest.mark.asyncio
async def test_direct_api_render_api_capable_device_shape(adapter, change_request):
    render_output = await adapter.render(change_request)

    assert len(render_output.snippets) == 2
    primary = next(s for s in render_output.snippets if s.render_role == RenderRole.PRIMARY)
    fallback = next(s for s in render_output.snippets if s.render_role == RenderRole.FALLBACK)

    assert primary.backend_type == RenderBackendType.API
    assert primary.api_payload is not None
    assert primary.api_payload.get("operations")
    assert primary.commands == []
    assert primary.rendered_text

    assert fallback.backend_type == RenderBackendType.CLI
    assert fallback.api_payload is None
    assert fallback.commands
    assert fallback.rendered_text

@pytest.mark.asyncio
async def test_direct_api_render_returns_cli_fallback_snippets(adapter, change_request):
    render_output = await adapter.render(change_request)
    
    assert render_output.snippets
    fallback_snippets = [s for s in render_output.snippets if s.render_role == RenderRole.FALLBACK]
    assert len(fallback_snippets) == 1
    
    snippet = fallback_snippets[0]
    assert snippet.device_name == "sw1"
    assert snippet.backend_type == RenderBackendType.CLI
    assert snippet.api_payload is None
    assert len(snippet.commands) > 0

@pytest.mark.asyncio
async def test_direct_api_render_noop_returns_early(adapter, change_request):
    change_request.plan_decision.decision = PlanDecisionType.NO_OP
    change_request.plan_decision.reason = "no_op reason"
    
    render_output = await adapter.render(change_request)
    
    assert "No changes required" in render_output.summary
    assert not render_output.snippets

@pytest.mark.asyncio
async def test_direct_api_render_blocked_returns_early(adapter, change_request):
    change_request.plan_decision.decision = PlanDecisionType.BLOCKED
    change_request.plan_decision.reason = "blocked reason"
    
    render_output = await adapter.render(change_request)
    
    assert "No changes required" in render_output.summary
    assert not render_output.snippets

@pytest.mark.asyncio
async def test_direct_api_render_does_not_reinterpret_plan_reason(adapter, change_request):
    change_request.plan_decision.reason = "blocked by policy text that should be ignored by render"

    render_output = await adapter.render(change_request)

    assert render_output.snippets

@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_direct_api_render_no_network_calls(mock_async_client, adapter, change_request):
    await adapter.render(change_request)
    mock_async_client.assert_not_called()
