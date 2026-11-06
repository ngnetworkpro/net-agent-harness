"""Unit tests for build_routing_render_input."""
import pytest

from net_agent_harness.models.artifacts import (
    OperationType,
    RenderRequest,
    RenderTarget,
    RoutingRenderPayload,
    StaticRouteOp,
)
from net_agent_harness.models.changes import (
    ChangeRequest,
    DeviceChange,
    PlanDecision,
    RequestedChange,
    ResolvedTarget,
    RollbackPlan,
)
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import (
    ChangeRisk,
    DeviceVendor,
    NetworkDomain,
    PlanDecisionType,
    TargetScope,
)
from net_agent_harness.orchestration.build_render import (
    build_render_input,
    build_routing_render_input,
)


def _base_routing_change_request(
    plan_decision: PlanDecision | None,
    routing_payload: RoutingRenderPayload | None = None,
    resolved_targets: list[ResolvedTarget] | None = None,
) -> ChangeRequest:
    if resolved_targets is None:
        resolved_targets = [
            ResolvedTarget(
                name="r1",
                site="HQ",
                role="core-router",
                platform="ios",
                primary_ip="10.0.0.1/24",
                vendor=DeviceVendor.CISCO,
            )
        ]
    return ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="cr-routing-1", created_by="test"),
        domain=NetworkDomain.ROUTING,
        scope=ScopeRef(site="HQ", device_names=["r1"]),
        target_scope=TargetScope.device,
        requested_change=RequestedChange(
            summary="Add static route to 10.10.10.0/24 via 192.168.1.1",
            intent="add static route",
        ),
        rollback_plan=RollbackPlan(summary="Remove static route"),
        risk=ChangeRisk.LOW,
        resolved_targets=resolved_targets,
        plan_decision=plan_decision,
        routing_payload=routing_payload,
    )


def test_build_routing_render_input_with_populated_routing_payload() -> None:
    """Verify build_routing_render_input returns RenderRequest with expected StaticRouteOps."""
    route_op = StaticRouteOp(
        prefix="10.10.10.0/24",
        next_hop="192.168.1.1",
        operation=OperationType.ENSURE_PRESENT,
        target=RenderTarget(
            name="r1",
            site="HQ",
            role="core-router",
            platform="ios",
            primary_ip="10.0.0.1/24",
        ),
        description="Branch route",
        admin_distance=10,
    )
    payload = RoutingRenderPayload(route_ops=[route_op])
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add route to r1",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=payload,
            )
        ],
    )
    cr = _base_routing_change_request(plan_decision=decision, routing_payload=payload)

    render_request = build_routing_render_input(cr)

    assert isinstance(render_request, RenderRequest)
    assert render_request.domain == NetworkDomain.ROUTING
    assert render_request.intent_type == "add static route"
    assert isinstance(render_request.payload, RoutingRenderPayload)
    assert len(render_request.payload.route_ops) == 1

    actual_op = render_request.payload.route_ops[0]
    assert actual_op.prefix == "10.10.10.0/24"
    assert actual_op.next_hop == "192.168.1.1"
    assert actual_op.operation == OperationType.ENSURE_PRESENT
    assert actual_op.target.name == "r1"
    assert actual_op.target.platform == "ios"
    assert actual_op.description == "Branch route"
    assert actual_op.admin_distance == 10


def test_build_render_input_dispatcher_routes_to_routing() -> None:
    """Verify build_render_input dispatcher routes domain=ROUTING to build_routing_render_input."""
    route_op = StaticRouteOp(
        prefix="172.16.0.0/12",
        next_hop="10.0.0.254",
        operation=OperationType.ENSURE_PRESENT,
        target=RenderTarget(name="r1", platform="ios"),
    )
    payload = RoutingRenderPayload(route_ops=[route_op])
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add corporate route",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=payload,
            )
        ],
    )
    cr = _base_routing_change_request(plan_decision=decision, routing_payload=payload)

    result = build_render_input(cr)

    assert isinstance(result, RenderRequest)
    assert result.domain == NetworkDomain.ROUTING
    assert isinstance(result.payload, RoutingRenderPayload)
    assert len(result.payload.route_ops) == 1
    assert result.payload.route_ops[0].prefix == "172.16.0.0/12"


def test_build_routing_render_rejects_missing_plan_decision() -> None:
    """Render building fails when plan_decision is None."""
    cr = _base_routing_change_request(plan_decision=None)
    with pytest.raises(ValueError, match="plan_decision is required"):
        build_routing_render_input(cr)


def test_build_routing_render_rejects_non_apply_plan_decision() -> None:
    """Render building rejects plan_decision with NO_OP or BLOCKED."""
    # NO_OP rejection
    cr_noop = _base_routing_change_request(
        plan_decision=PlanDecision(
            decision=PlanDecisionType.NO_OP,
            reason="Route already present",
            diff=[],
        )
    )
    with pytest.raises(ValueError, match="Render rejected.*expected 'apply'"):
        build_routing_render_input(cr_noop)

    # BLOCKED rejection
    cr_blocked = _base_routing_change_request(
        plan_decision=PlanDecision(
            decision=PlanDecisionType.BLOCKED,
            reason="Target unreachable",
            diff=[],
        )
    )
    with pytest.raises(ValueError, match="Render rejected.*expected 'apply'"):
        build_routing_render_input(cr_blocked)


def test_build_routing_render_rejects_unresolved_device_target() -> None:
    """Render building rejects if a device in diff is missing from resolved_targets."""
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add route",
        diff=[
            DeviceChange(
                device="unresolved_router",
                domain=NetworkDomain.ROUTING,
                changes=RoutingRenderPayload(
                    route_ops=[
                        StaticRouteOp(
                            prefix="10.0.0.0/8",
                            next_hop="192.168.1.1",
                            operation=OperationType.ENSURE_PRESENT,
                            target=RenderTarget(name="unresolved_router"),
                        )
                    ]
                ),
            )
        ],
    )
    cr = _base_routing_change_request(plan_decision=decision)
    with pytest.raises(ValueError, match="not present in resolved_targets"):
        build_routing_render_input(cr)


def test_build_routing_render_rejects_missing_platform() -> None:
    """Render building rejects if a device in resolved_targets is missing platform."""
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add route",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=[
                    StaticRouteOp(
                        prefix="10.0.0.0/8",
                        next_hop="192.168.1.1",
                        operation=OperationType.ENSURE_PRESENT,
                        target=RenderTarget(name="r1"),
                    )
                ],
            )
        ],
    )
    resolved = [
        ResolvedTarget(
            name="r1",
            site="HQ",
            role="core-router",
            platform="",  # Empty platform
            primary_ip="10.0.0.1/24",
            vendor=DeviceVendor.CISCO,
        )
    ]
    cr = _base_routing_change_request(plan_decision=decision, resolved_targets=resolved)
    with pytest.raises(ValueError, match="missing platform in resolved_targets"):
        build_routing_render_input(cr)


def test_build_routing_render_from_plan_decision_diff_when_payload_none() -> None:
    """When routing_payload is None, operations are extracted directly from plan_decision.diff."""
    route_op = StaticRouteOp(
        prefix="192.168.50.0/24",
        next_hop="10.0.0.1",
        operation=OperationType.ENSURE_PRESENT,
        target=RenderTarget(name="r1", platform="ios"),
    )
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add route from diff",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=[route_op],
            )
        ],
    )
    cr = _base_routing_change_request(plan_decision=decision, routing_payload=None)

    result = build_routing_render_input(cr)

    assert isinstance(result, RenderRequest)
    assert result.domain == NetworkDomain.ROUTING
    assert isinstance(result.payload, RoutingRenderPayload)
    assert len(result.payload.route_ops) == 1
    assert result.payload.route_ops[0].prefix == "192.168.50.0/24"
    assert result.payload.route_ops[0].target.platform == "ios"


def test_build_routing_render_empty_payload() -> None:
    """Empty route operations produce empty payload."""
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="No ops",
        diff=[],
    )
    cr = _base_routing_change_request(
        plan_decision=decision,
        routing_payload=RoutingRenderPayload(route_ops=[]),
    )
    result = build_routing_render_input(cr)
    assert isinstance(result, RenderRequest)
    assert isinstance(result.payload, RoutingRenderPayload)
    assert not result.payload.has_ops()


def test_build_routing_render_from_plan_decision_diff_raw_dict_operations() -> None:
    """Raw dictionary operations inside diff fallback (e.g. from JSON deserialization)
    are successfully parsed into StaticRouteOps with authoritative target metadata.
    """
    raw_dict_op = {
        "prefix": "10.40.0.0/24",
        "next_hop": "192.168.1.254",
        "operation": "ensure_present",
        "description": "Deserialized route from JSON diff",
        "admin_distance": 15,
    }
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add route from raw dict diff",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=[raw_dict_op],
            )
        ],
    )
    cr = _base_routing_change_request(plan_decision=decision, routing_payload=None)

    result = build_routing_render_input(cr)

    assert isinstance(result, RenderRequest)
    assert result.domain == NetworkDomain.ROUTING
    assert isinstance(result.payload, RoutingRenderPayload)
    assert len(result.payload.route_ops) == 1

    actual_op = result.payload.route_ops[0]
    assert isinstance(actual_op, StaticRouteOp)
    assert actual_op.prefix == "10.40.0.0/24"
    assert actual_op.next_hop == "192.168.1.254"
    assert actual_op.operation == OperationType.ENSURE_PRESENT
    assert actual_op.target.name == "r1"
    assert actual_op.target.platform == "ios"
    assert actual_op.target.site == "HQ"
    assert actual_op.description == "Deserialized route from JSON diff"
    assert actual_op.admin_distance == 15


def test_build_routing_render_json_roundtrip_diff_fallback() -> None:
    """When ChangeRequest without routing_payload is serialized to JSON and deserialized,
    raw dicts in DeviceChange.changes are successfully parsed into StaticRouteOps.
    """
    route_op = StaticRouteOp(
        prefix="10.60.0.0/24",
        next_hop="192.168.10.1",
        operation=OperationType.ENSURE_PRESENT,
        target=RenderTarget(name="r1", platform="ios"),
        description="Roundtrip route",
        admin_distance=50,
    )
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Route for roundtrip",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=[route_op],
            )
        ],
    )
    cr = _base_routing_change_request(plan_decision=decision, routing_payload=None)

    # Serialize to JSON and deserialize back
    json_str = cr.model_dump_json()
    deserialized_cr = ChangeRequest.model_validate_json(json_str)

    # Confirm that after deserialization without routing_payload,
    # diff[0].changes contains raw dictionaries
    assert deserialized_cr.plan_decision is not None
    assert deserialized_cr.plan_decision.diff is not None
    raw_changes = deserialized_cr.plan_decision.diff[0].changes
    assert isinstance(raw_changes, list)
    assert isinstance(raw_changes[0], dict)

    result = build_routing_render_input(deserialized_cr)

    assert isinstance(result, RenderRequest)
    assert result.domain == NetworkDomain.ROUTING
    assert isinstance(result.payload, RoutingRenderPayload)
    assert len(result.payload.route_ops) == 1
    actual_op = result.payload.route_ops[0]
    assert isinstance(actual_op, StaticRouteOp)
    assert actual_op.prefix == "10.60.0.0/24"
    assert actual_op.next_hop == "192.168.10.1"
    assert actual_op.operation == OperationType.ENSURE_PRESENT
    assert actual_op.target.name == "r1"
    assert actual_op.target.platform == "ios"
    assert actual_op.description == "Roundtrip route"
    assert actual_op.admin_distance == 50


def test_build_routing_render_rejects_malformed_dict_in_diff() -> None:
    """Malformed dictionary in plan_decision.diff.changes raises ValueError."""
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add invalid route",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=[{"invalid_key": "bad_value"}],
            )
        ],
    )
    cr = _base_routing_change_request(plan_decision=decision, routing_payload=None)
    with pytest.raises(ValueError, match="invalid static route operation in diff"):
        build_routing_render_input(cr)


def test_build_routing_render_rejects_whitespace_platform() -> None:
    """Whitespace-only platform is rejected."""
    decision = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="Add route",
        diff=[
            DeviceChange(
                device="r1",
                domain=NetworkDomain.ROUTING,
                changes=[],
            )
        ],
    )
    resolved = [
        ResolvedTarget(
            name="r1",
            site="HQ",
            role="core-router",
            platform="   ",  # Whitespace only
            primary_ip="10.0.0.1/24",
            vendor=DeviceVendor.CISCO,
        )
    ]
    cr = _base_routing_change_request(plan_decision=decision, resolved_targets=resolved)
    with pytest.raises(ValueError, match="missing platform in resolved_targets"):
        build_routing_render_input(cr)

