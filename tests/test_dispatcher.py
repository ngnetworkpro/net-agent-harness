from net_agent_harness.models.enums import Capability, RequestKind, RoutingStatus, RunStage
from net_agent_harness.models.routing import RoutedRequest
from net_agent_harness.orchestration.dispatcher import DispatchMode, dispatch_request


def test_dispatch_request_sends_ask_topology_to_direct_answer() -> None:
    routed = RoutedRequest(
        status=RoutingStatus.ROUTED,
        kind=RequestKind.ASK,
        capability=Capability.TOPOLOGY,
        confidence=0.9,
        requires_run=False,
        requires_approval=False,
        rationale=["connected", "device-reference"],
    )

    decision = dispatch_request(routed)

    assert decision.mode is DispatchMode.DIRECT_ANSWER
    assert decision.handler == "topology_answer"
    assert decision.initial_stage is None


def test_dispatch_request_sends_plan_change_to_workflow() -> None:
    routed = RoutedRequest(
        status=RoutingStatus.ROUTED,
        kind=RequestKind.PLAN,
        capability=Capability.CHANGE,
        confidence=0.95,
        requires_run=True,
        requires_approval=True,
        rationale=["add", "vlan:vlan"],
    )

    decision = dispatch_request(routed)

    assert decision.mode is DispatchMode.WORKFLOW_RUN
    assert decision.handler == "change_workflow"
    assert decision.initial_stage is RunStage.PLAN


def test_dispatch_request_blocks_non_routed_requests() -> None:
    routed = RoutedRequest(
        status=RoutingStatus.NEEDS_CLARIFICATION,
        confidence=0.35,
        requires_run=False,
        requires_approval=False,
        rationale=["weak signals"],
    )

    decision = dispatch_request(routed)

    assert decision.mode is DispatchMode.BLOCKED
    assert decision.handler == "clarification_required"


def test_dispatch_request_blocks_incident_review_until_workflow_exists() -> None:
    routed = RoutedRequest(
        status=RoutingStatus.ROUTED,
        kind=RequestKind.REVIEW,
        capability=Capability.INCIDENT,
        confidence=0.8,
        requires_run=False,
        requires_approval=False,
        rationale=["outage", "down"],
    )

    decision = dispatch_request(routed)

    assert decision.mode is DispatchMode.BLOCKED
    assert decision.handler == "incident_review"
