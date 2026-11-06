"""Unit tests for routing domain evaluation."""
import pytest

from net_agent_harness.models.artifacts import OperationType, StaticRouteOp
from net_agent_harness.models.enums import NetworkDomain, PlanDecisionType
from net_agent_harness.tools.evaluation import evaluate_intent_state


def test_evaluate_routing_simple_static_route_returns_apply() -> None:
    """Mock inventory and simple static-route intent assert APPLY and non-empty diff."""
    decision = evaluate_intent_state(
        run_id="run-routing-1",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.20.0.0/24",
                        "next_hop": "192.168.1.1",
                        "description": "Branch office route",
                    },
                }
            ]
        },
        inventory_source="mock",
    )

    assert decision.decision == PlanDecisionType.APPLY
    assert decision.decision.value == "apply"
    assert decision.diff, "diff must be non-empty"
    assert len(decision.diff) == 1

    device_change = decision.diff[0]
    assert device_change.device == "sw1"
    assert device_change.domain == NetworkDomain.ROUTING

    # Verify the StaticRouteOp payload
    changes = device_change.changes
    route_ops = (
        changes.route_ops
        if hasattr(changes, "route_ops")
        else (changes if isinstance(changes, list) else [changes])
    )
    assert len(route_ops) == 1
    op = route_ops[0]
    assert isinstance(op, StaticRouteOp)
    assert op.prefix == "10.20.0.0/24"
    assert op.next_hop == "192.168.1.1"
    assert op.operation == OperationType.ENSURE_PRESENT
    assert op.target.name == "sw1"


def test_evaluate_routing_device_not_found_returns_blocked() -> None:
    """Unknown device in inventory returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id="run-routing-2",
        domain="routing",
        site="HQ",
        device_names=["unknown-core-router"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.10.10.0/24", "next_hop": "192.168.1.1"},
                }
            ]
        },
        inventory_source="mock",
    )

    assert decision.decision == PlanDecisionType.BLOCKED
    assert "not found" in decision.reason.lower()


def test_evaluate_routing_missing_site_returns_blocked() -> None:
    """Missing site returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id="run-routing-3",
        domain="routing",
        site=None,
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.10.10.0/24", "next_hop": "192.168.1.1"},
                }
            ]
        },
        inventory_source="mock",
    )

    assert decision.decision == PlanDecisionType.BLOCKED
    assert "site is required" in decision.reason.lower()


def test_evaluate_routing_empty_device_names_returns_blocked() -> None:
    """Empty device list returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id="run-routing-4",
        domain="routing",
        site="HQ",
        device_names=[],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.10.10.0/24", "next_hop": "192.168.1.1"},
                }
            ]
        },
        inventory_source="mock",
    )

    assert decision.decision == PlanDecisionType.BLOCKED
    assert "target device is required" in decision.reason.lower()


def test_evaluate_routing_missing_prefix_or_nexthop_returns_blocked() -> None:
    """Static route missing prefix or next_hop returns BLOCKED decision."""
    # Missing next_hop
    decision_no_hop = evaluate_intent_state(
        run_id="run-routing-5",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.10.10.0/24"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision_no_hop.decision == PlanDecisionType.BLOCKED
    assert "next_hop" in decision_no_hop.reason.lower()

    # Missing prefix
    decision_no_pfx = evaluate_intent_state(
        run_id="run-routing-6",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"next_hop": "192.168.1.1"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision_no_pfx.decision == PlanDecisionType.BLOCKED
    assert "prefix" in decision_no_pfx.reason.lower()


def test_evaluate_routing_invalid_prefix_or_nexthop_returns_blocked() -> None:
    """Invalid CIDR prefix or invalid next_hop IP returns BLOCKED decision."""
    decision_bad_pfx = evaluate_intent_state(
        run_id="run-routing-bad-pfx",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "not-a-cidr", "next_hop": "192.168.1.1"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision_bad_pfx.decision == PlanDecisionType.BLOCKED
    assert "invalid prefix" in decision_bad_pfx.reason.lower()

    decision_bad_hop = evaluate_intent_state(
        run_id="run-routing-bad-hop",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.0.0.0/24", "next_hop": "not-an-ip"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision_bad_hop.decision == PlanDecisionType.BLOCKED
    assert "invalid next_hop" in decision_bad_hop.reason.lower()


def test_evaluate_routing_custom_monkeypatch_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify routing evaluation with a custom monkeypatched device context."""
    def _fake_lookup_device_context_sync(
        inventory_source: str, site: str | None, device_name: str | None
    ) -> dict[str, object]:
        return {
            "source": "custom-mock",
            "device": {
                "name": device_name,
                "vendor": "cisco",
                "role": "core-router",
                "site": site,
                "platform": "ios",
                "management_ip": "10.254.0.1",
            },
            "interfaces": [],
            "ip_addresses": [],
        }

    monkeypatch.setattr(
        "net_agent_harness.tools.inventory_tools.lookup_device_context_sync",
        _fake_lookup_device_context_sync,
    )

    decision = evaluate_intent_state(
        run_id="run-routing-7",
        domain="routing",
        site="Branch1",
        device_names=["cisco_core1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "172.16.0.0/16",
                        "next_hop": "10.254.0.2",
                        "admin_distance": 5,
                    },
                }
            ]
        },
        inventory_source="custom-mock",
    )

    assert decision.decision == PlanDecisionType.APPLY
    assert len(decision.diff) == 1
    assert decision.diff[0].device == "cisco_core1"


def test_evaluate_routing_multi_device_evaluates_all() -> None:
    """Multi-device intent returns apply diff for all targets."""
    decision = evaluate_intent_state(
        run_id="run-routing-8",
        domain="routing",
        site="HQ",
        device_names=["sw1", "fw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "192.168.100.0/24", "next_hop": "10.0.0.254"},
                }
            ]
        },
        inventory_source="mock",
    )

    assert decision.decision == PlanDecisionType.APPLY
    assert len(decision.diff) == 2
    assert {d.device for d in decision.diff} == {"sw1", "fw1"}


@pytest.mark.parametrize(
    "invalid_state",
    [
        "non_dict_string_state",
        ["list", "of", "routes"],
        12345,
        99.9,
        True,
    ],
)
def test_evaluate_routing_non_dict_desired_state_returns_blocked(invalid_state: object) -> None:
    """Non-dict desired_state (string, list, number, bool) returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id="run-routing-non-dict-state",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state=invalid_state,  # type: ignore[arg-type]
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert not decision.diff
    assert "dictionary" in decision.reason.lower() or "desired_state" in decision.reason.lower()


@pytest.mark.parametrize(
    "invalid_operations",
    [
        12345,
        "not-a-list",
        True,
        {"prefix": "10.0.0.0/24"},
        3.14,
    ],
)
def test_evaluate_routing_non_list_operations_returns_blocked(
    invalid_operations: object,
) -> None:
    """Non-list / integer operations field in desired_state returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id="run-routing-non-list-ops",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={"operations": invalid_operations},  # type: ignore[dict-item]
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert not decision.diff
    assert "operations" in decision.reason.lower()


def test_evaluate_routing_operations_rejects_non_dict_operation_item() -> None:
    """Non-dict element inside operations list fails safe to BLOCKED."""
    decision = evaluate_intent_state(
        run_id="run-bad-op-item",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={"operations": ["invalid_string_op"]},  # type: ignore[list-item]
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "must be a dictionary" in decision.reason


@pytest.mark.parametrize(
    "bad_target_devices",
    [
        12345,
        True,
        45.67,
    ],
)
def test_evaluate_routing_integer_target_devices_handled_safely(
    bad_target_devices: object,
) -> None:
    """Non-collection target_devices field in operation returns BLOCKED."""
    decision = evaluate_intent_state(
        run_id="run-routing-bad-target-devices",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "target_devices": bad_target_devices,
                    "attributes": {
                        "prefix": "10.50.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "target_devices" in decision.reason
    assert not decision.diff


@pytest.mark.parametrize("bool_admin_distance", [True, False])
def test_evaluate_routing_boolean_admin_distance_returns_blocked(
    bool_admin_distance: bool,
) -> None:
    """Boolean admin_distance (True/False) returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id=f"run-routing-bool-ad-{bool_admin_distance}",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.0.0.0/24",
                        "next_hop": "192.168.1.1",
                        "admin_distance": bool_admin_distance,
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "admin_distance" in decision.reason.lower()
    assert not decision.diff


@pytest.mark.parametrize(
    ("raw_prefix", "expected_canonical_prefix"),
    [
        ("10.0.0.1/24", "10.0.0.0/24"),
        ("192.168.1.254/24", "192.168.1.0/24"),
        ("172.16.50.1/16", "172.16.0.0/16"),
        ("10.0.0.1/32", "10.0.0.1/32"),
    ],
)
def test_evaluate_routing_host_bit_normalization(
    raw_prefix: str, expected_canonical_prefix: str
) -> None:
    """Prefix with host bits set (e.g. 10.0.0.1/24) is normalized to canonical network CIDR."""
    decision = evaluate_intent_state(
        run_id="run-routing-host-bits",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": raw_prefix,
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.APPLY
    assert decision.diff, "diff must be non-empty for apply decision"
    device_change = decision.diff[0]
    changes = device_change.changes
    route_ops = (
        changes.route_ops
        if hasattr(changes, "route_ops")
        else (changes if isinstance(changes, list) else [changes])
    )
    assert len(route_ops) == 1
    op = route_ops[0]
    assert isinstance(op, StaticRouteOp)
    assert op.prefix == expected_canonical_prefix
