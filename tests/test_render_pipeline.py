import pytest

from net_agent_harness.agents.config_render_agent import _enforce_snippets, render_system_prompt
from net_agent_harness.models.artifacts import (
    ApiRequestPayload,
    ConfigRenderOutput,
    ConfigSnippet,
    OperationType,
    RenderRequest,
    RenderTarget,
    RoutingRenderPayload,
    StaticRouteOp,
    VlanRenderOp,
    VlanRenderPayload,
)
from net_agent_harness.models.enums import NetworkDomain, RenderBackendType, RenderRole


class DummyCtx:
    def __init__(self, req: RenderRequest) -> None:
        self.deps = req


def _vlan_request() -> RenderRequest:
    return RenderRequest(
        domain=NetworkDomain.VLAN,
        intent_type="set_access_vlan",
        payload=VlanRenderPayload(
            vlan_ops=[
                VlanRenderOp(
                    target=RenderTarget(name="sw1"),
                    vlan_id=10,
                    vlan_name="users",
                    operation=OperationType.ENSURE_PRESENT,
                )
            ]
        ),
    )


def _routing_request() -> RenderRequest:
    return RenderRequest(
        domain=NetworkDomain.ROUTING,
        intent_type="ensure_static_route",
        payload=RoutingRenderPayload(
            route_ops=[
                StaticRouteOp(
                    target=RenderTarget(name="r1"),
                    prefix="10.10.10.0/24",
                    next_hop="192.168.1.1",
                    operation=OperationType.ENSURE_PRESENT,
                )
            ]
        ),
    )


@pytest.mark.asyncio
async def test_vlan_prompt_and_snippet_enforcement() -> None:
    req = _vlan_request()
    ctx = DummyCtx(req)
    prompt = render_system_prompt(ctx)
    assert "specialized in VLAN operations" in prompt
    assert "specialized in routing operations" not in prompt

    good_output = ConfigRenderOutput(
        summary="Rendered VLAN 10",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(
                    method="POST",
                    path="/vlans",
                    body={"vlan_id": 10},
                ),
                commands=[],
            )
        ],
    )
    assert await _enforce_snippets(ctx, good_output) == good_output

    with pytest.raises(ValueError, match="Produce at least one ConfigSnippet"):
        await _enforce_snippets(ctx, ConfigRenderOutput(summary="empty", snippets=[]))


@pytest.mark.asyncio
async def test_routing_prompt_and_validate_snippets_next_hop_guard() -> None:
    req = _routing_request()
    ctx = DummyCtx(req)
    prompt = render_system_prompt(ctx)
    assert "specialized in routing operations" in prompt
    assert "specialized in VLAN operations" not in prompt

    bad_output = ConfigRenderOutput(
        summary="Rendered route",
        snippets=[
            ConfigSnippet(
                device_name="r1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(
                    method="POST",
                    path="/staticRoutes",
                    body={"prefix": "10.10.10.0/24"},
                ),
                commands=[],
            )
        ],
    )
    with pytest.raises(ValueError, match="missing 'next_hop'"):
        await _enforce_snippets(ctx, bad_output)


def test_prompt_rejects_unsupported_domain_acl() -> None:
    req = RenderRequest(
        domain=NetworkDomain.ACL,
        intent_type="deny_any_any",
        payload=VlanRenderPayload(),
    )
    with pytest.raises(ValueError, match="Unsupported render domain 'acl'"):
        render_system_prompt(DummyCtx(req))


@pytest.mark.asyncio
async def test_empty_payload_does_not_require_snippets() -> None:
    req = RenderRequest(
        domain=NetworkDomain.ROUTING,
        intent_type="ensure_static_route",
        payload=RoutingRenderPayload(),
    )
    output = ConfigRenderOutput(summary="No changes", snippets=[])
    assert await _enforce_snippets(DummyCtx(req), output) == output
