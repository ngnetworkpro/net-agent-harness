import pytest
from pydantic import ValidationError

from net_agent_harness.models.enums import Capability, NetworkDomain, RequestKind, RoutingStatus
from net_agent_harness.models.routing import RoutedRequest
from net_agent_harness.orchestration.intent_router import route_intent


@pytest.mark.parametrize(
    ("prompt", "domain"),
    [
        ("Add VLAN 220 to trunk port Gi0/1 on sw1 at HQ", NetworkDomain.VLAN),
        ("permit ip any any", NetworkDomain.ACL),
        ("add static route to 10.0.0.0/8 via 192.168.1.1", NetworkDomain.ROUTING),
        ("create a new ssid called corp-guest", NetworkDomain.WIRELESS),
    ],
)
def test_route_intent_routes_change_requests_to_plan_change(
    prompt: str, domain: NetworkDomain
) -> None:
    routed = route_intent(prompt)

    assert routed.status is RoutingStatus.ROUTED
    assert routed.kind is RequestKind.PLAN
    assert routed.capability is Capability.CHANGE
    assert routed.domain is domain
    assert routed.requires_run is True
    assert routed.requires_approval is True


def test_route_intent_routes_topology_questions_to_direct_answer() -> None:
    routed = route_intent("What is connected to sw1?")

    assert routed.status is RoutingStatus.ROUTED
    assert routed.kind is RequestKind.ASK
    assert routed.capability is Capability.TOPOLOGY
    assert routed.requires_run is False
    assert routed.matches


def test_route_intent_routes_ipam_questions() -> None:
    routed = route_intent("Is 10.10.20.0/24 assigned anywhere?")

    assert routed.status is RoutingStatus.ROUTED
    assert routed.kind is RequestKind.ASK
    assert routed.capability is Capability.IPAM
    assert routed.requires_run is False


def test_route_intent_routes_incident_review_requests() -> None:
    routed = route_intent("Review the outage impact for sw1 because it is down")

    assert routed.status is RoutingStatus.ROUTED
    assert routed.kind is RequestKind.REVIEW
    assert routed.capability is Capability.INCIDENT


def test_route_intent_returns_needs_clarification_for_weak_signals() -> None:
    routed = route_intent("fix the thing on sw1")

    assert routed.status is RoutingStatus.NEEDS_CLARIFICATION
    assert routed.kind is None
    assert routed.capability is None
    assert routed.ambiguous is True
    assert routed.confidence > 0.0


def test_route_intent_blocks_unknown_requests() -> None:
    routed = route_intent("lorem ipsum")

    assert routed.status is RoutingStatus.BLOCKED
    assert routed.kind is None
    assert routed.capability is None
    assert routed.confidence == 0.0


def test_routed_request_rejects_invalid_kind_capability_combination() -> None:
    with pytest.raises(ValidationError):
        RoutedRequest(
            status=RoutingStatus.ROUTED,
            kind=RequestKind.ASK,
            capability=Capability.CHANGE,
            confidence=0.9,
            requires_run=False,
            requires_approval=False,
            rationale=["invalid combination"],
        )


def test_routed_request_is_serializable() -> None:
    routed = route_intent("Add VLAN 10 to sw1")

    dumped = routed.model_dump()

    assert dumped["kind"] == RequestKind.PLAN
    assert dumped["capability"] == Capability.CHANGE
    assert dumped["relevant_domains"] == [NetworkDomain.VLAN]
