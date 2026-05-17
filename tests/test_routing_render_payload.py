"""Tests for RoutingRenderPayload and routing render domain."""
import pytest
from net_agent_harness.agents.config_render_agent import (
    _enforce_snippets,
    SUPPORTED_RENDER_DOMAINS,
    render_system_prompt,
)
from net_agent_harness.models.artifacts import (
    ApiRequestPayload,
    ConfigRenderOutput,
    ConfigSnippet,
    OperationType,
    RenderRequest,
    RenderTarget,
    RoutingRenderPayload,
    StaticRouteOp,
)
from net_agent_harness.models.enums import NetworkDomain, RenderBackendType, RenderRole


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_route_op(
    prefix: str = "10.10.10.0/24",
    next_hop: str = "192.168.1.1",
    device: str = "meraki_router1",
) -> StaticRouteOp:
    return StaticRouteOp(
        prefix=prefix,
        next_hop=next_hop,
        operation=OperationType.ENSURE_PRESENT,
        target=RenderTarget(name=device),
    )


def _make_routing_request(route_ops: list | None = None) -> RenderRequest:
    ops = route_ops if route_ops is not None else [_make_route_op()]
    return RenderRequest(
        domain=NetworkDomain.ROUTING,
        intent_type="add_static_route",
        payload=RoutingRenderPayload(route_ops=ops),
    )


class DummyCtx:
    """Minimal stand-in for RunContext."""
    def __init__(self, deps: RenderRequest) -> None:
        self.deps = deps


# ── RoutingRenderPayload.has_ops() ────────────────────────────────────────────

def test_has_ops_returns_false_when_empty() -> None:
    payload = RoutingRenderPayload()
    assert payload.has_ops() is False


def test_has_ops_returns_true_with_route_ops() -> None:
    payload = RoutingRenderPayload(route_ops=[_make_route_op()])
    assert payload.has_ops() is True


# ── RoutingRenderPayload.describe_ops() ───────────────────────────────────────

def test_describe_ops_empty_payload_returns_empty_list() -> None:
    payload = RoutingRenderPayload()
    assert payload.describe_ops() == []


def test_describe_ops_assembles_correct_lines() -> None:
    payload = RoutingRenderPayload(
        route_ops=[
            StaticRouteOp(
                prefix="10.10.10.0/24",
                next_hop="192.168.1.1",
                operation=OperationType.ENSURE_PRESENT,
                target=RenderTarget(name="meraki_router1"),
            ),
            StaticRouteOp(
                prefix="172.16.0.0/12",
                next_hop="10.0.0.1",
                operation=OperationType.REMOVE,
                target=RenderTarget(name="cisco_r1"),
            ),
        ]
    )
    lines = payload.describe_ops()
    assert lines[0] == "Route Operations:"
    assert "10.10.10.0/24" in lines[1]
    assert "192.168.1.1" in lines[1]
    assert "ensure_present" in lines[1]
    assert "meraki_router1" in lines[1]
    assert "172.16.0.0/12" in lines[2]
    assert "remove" in lines[2]
    assert "cisco_r1" in lines[2]


# ── RoutingRenderPayload.validate_snippets() ──────────────────────────────────

def test_validate_snippets_passes_when_next_hop_present() -> None:
    payload = RoutingRenderPayload(route_ops=[_make_route_op()])
    snippet = ConfigSnippet(
        device_name="meraki_router1",
        backend_type=RenderBackendType.API,
        render_role=RenderRole.PRIMARY,
        api_payload=ApiRequestPayload(
            method="POST",
            path="/networks/n1/appliance/staticRoutes",
            body={"subnet": "10.10.10.0/24", "next_hop": "192.168.1.1"},
        ),
        commands=[],
    )
    errors = payload.validate_snippets([snippet])
    assert errors == []


def test_validate_snippets_catches_missing_next_hop() -> None:
    payload = RoutingRenderPayload(route_ops=[_make_route_op()])
    snippet = ConfigSnippet(
        device_name="meraki_router1",
        backend_type=RenderBackendType.API,
        render_role=RenderRole.PRIMARY,
        api_payload=ApiRequestPayload(
            method="POST",
            path="/networks/n1/appliance/staticRoutes",
            body={"subnet": "10.10.10.0/24"},
        ),
        commands=[],
    )
    errors = payload.validate_snippets([snippet])
    assert len(errors) == 1
    assert "next_hop" in errors[0]
    assert "meraki_router1" in errors[0]


def test_validate_snippets_ignores_cli_fallback_snippets() -> None:
    payload = RoutingRenderPayload(route_ops=[_make_route_op()])
    snippet = ConfigSnippet(
        device_name="cisco_r1",
        backend_type=RenderBackendType.CLI,
        render_role=RenderRole.FALLBACK,
        api_payload=None,
        commands=["ip route 10.10.10.0 255.255.255.0 192.168.1.1"],
    )
    errors = payload.validate_snippets([snippet])
    assert errors == []


def test_validate_snippets_catches_missing_api_payload_body() -> None:
    payload = RoutingRenderPayload(route_ops=[_make_route_op()])
    snippet = ConfigSnippet(
        device_name="meraki_router1",
        backend_type=RenderBackendType.API,
        render_role=RenderRole.PRIMARY,
        api_payload=ApiRequestPayload(
            method="POST",
            path="/networks/n1/appliance/staticRoutes",
            body=None,
        ),
        commands=[],
    )
    errors = payload.validate_snippets([snippet])
    assert len(errors) == 1
    assert "next_hop" in errors[0]


# ── _enforce_snippets integration ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enforce_snippets_passes_for_valid_routing_snippet() -> None:
    req = _make_routing_request()
    ctx = DummyCtx(req)
    output = ConfigRenderOutput(
        summary="Rendered static route to 10.10.10.0/24 via 192.168.1.1 on meraki_router1",
        snippets=[
            ConfigSnippet(
                device_name="meraki_router1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(
                    method="POST",
                    path="/networks/n1/appliance/staticRoutes",
                    body={"subnet": "10.10.10.0/24", "next_hop": "192.168.1.1"},
                ),
                commands=[],
            )
        ],
    )
    result = await _enforce_snippets(ctx, output)
    assert result == output


@pytest.mark.asyncio
async def test_enforce_snippets_rejects_routing_snippet_missing_next_hop() -> None:
    req = _make_routing_request()
    ctx = DummyCtx(req)
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="meraki_router1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(
                    method="POST",
                    path="/networks/n1/appliance/staticRoutes",
                    body={"subnet": "10.10.10.0/24"},
                ),
                commands=[],
            )
        ],
    )
    with pytest.raises(ValueError, match="next_hop"):
        await _enforce_snippets(ctx, output)


@pytest.mark.asyncio
async def test_enforce_snippets_returns_early_when_no_routing_ops() -> None:
    req = RenderRequest(
        domain=NetworkDomain.ROUTING,
        intent_type="add_static_route",
        payload=RoutingRenderPayload(route_ops=[]),
    )
    ctx = DummyCtx(req)
    output = ConfigRenderOutput(summary="Nothing to do", snippets=[])
    result = await _enforce_snippets(ctx, output)
    assert result == output


# ── SUPPORTED_RENDER_DOMAINS ─────────────────────────────────────────────────

def test_routing_not_in_supported_render_domains() -> None:
    assert "routing" not in SUPPORTED_RENDER_DOMAINS


def test_vlan_in_supported_render_domains() -> None:
    assert "vlan" in SUPPORTED_RENDER_DOMAINS


# ── System prompt content ────────────────────────────────────────────────────

def test_routing_system_prompt_rejects_unsupported_domain_with_clear_error() -> None:
    req = _make_routing_request()
    ctx = DummyCtx(req)
    with pytest.raises(ValueError) as exc_info:
        render_system_prompt(ctx)
    assert "Unsupported render domain 'routing'" in str(exc_info.value)
    assert "Supported render domains: vlan." in str(exc_info.value)


def test_routing_system_prompt_rejects_even_with_empty_payload() -> None:
    req = _make_routing_request()
    req.payload = RoutingRenderPayload(route_ops=[])
    ctx = DummyCtx(req)
    with pytest.raises(ValueError, match="Unsupported render domain 'routing'"):
        render_system_prompt(ctx)
