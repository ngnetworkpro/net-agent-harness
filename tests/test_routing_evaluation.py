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


def test_evaluate_routing_unresolved_explicit_target_device_returns_blocked() -> None:
    """Explicit target_device not found in inventory snapshot returns BLOCKED."""
    decision = evaluate_intent_state(
        run_id="run-routing-unresolved-target",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "target_device": "ghost-switch-99",
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.0.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "not found in the inventory snapshot for site 'HQ'" in decision.reason


def test_evaluate_routing_unresolved_top_level_target_device_returns_blocked() -> None:
    """Top-level explicit target_device not found in inventory snapshot returns BLOCKED."""
    decision = evaluate_intent_state(
        run_id="run-routing-unresolved-top-target",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "target_device": "ghost-switch-top",
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.0.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ],
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "not found in the inventory snapshot for site 'HQ'" in decision.reason


def test_evaluate_routing_unsupported_operation_returns_blocked() -> None:
    """Unsupported routing operation string returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id="run-routing-unsupported-op",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "bgp_neighbor",
                    "attributes": {
                        "prefix": "10.0.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "Unsupported routing operation 'bgp_neighbor'" in decision.reason


def test_evaluate_routing_unsupported_object_type_returns_blocked() -> None:
    """Unsupported routing object_type returns BLOCKED decision."""
    decision = evaluate_intent_state(
        run_id="run-routing-unsupported-obj",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "ospf_area",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.0.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "Unsupported routing object_type 'ospf_area'" in decision.reason


@pytest.mark.parametrize("op_name", ["ensure_present", "create", "add"])
def test_evaluate_routing_permitted_add_operations(op_name: str) -> None:
    """Permitted add/create static route operations resolve to APPLY with ENSURE_PRESENT."""
    decision = evaluate_intent_state(
        run_id=f"run-routing-add-{op_name}",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": op_name,
                    "attributes": {
                        "prefix": "10.33.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.APPLY
    assert decision.diff[0].changes[0].operation == OperationType.ENSURE_PRESENT


@pytest.mark.parametrize("op_name", ["ensure_absent", "remove", "delete"])
def test_evaluate_routing_permitted_remove_operations(monkeypatch: pytest.MonkeyPatch, op_name: str) -> None:
    """Permitted remove static route operations on existing route resolve to APPLY with REMOVE."""
    import net_agent_harness.tools.evaluation as eval_module
    from net_agent_harness.models.enums import DeviceVendor
    from net_agent_harness.models.inventory import DeviceInfo, RouteInfo

    fake_device = DeviceInfo(
        name="sw1",
        vendor=DeviceVendor.CISCO,
        site="HQ",
        role="switch",
        routes=[RouteInfo(prefix="10.33.0.0/24", next_hop="192.168.1.1")],
    )
    monkeypatch.setattr(eval_module, "_load_device_from_inventory", lambda *args, **kwargs: fake_device)

    decision = evaluate_intent_state(
        run_id=f"run-routing-remove-{op_name}",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": op_name,
                    "attributes": {
                        "prefix": "10.33.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.APPLY
    assert decision.diff[0].changes[0].operation == OperationType.REMOVE


def test_evaluate_routing_desired_route_already_present_returns_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """When desired static route already exists in authoritative current state, return NO_OP."""
    import net_agent_harness.tools.evaluation as eval_module
    from net_agent_harness.models.enums import DeviceVendor
    from net_agent_harness.models.inventory import DeviceInfo, RouteInfo

    fake_device = DeviceInfo(
        name="sw1",
        vendor=DeviceVendor.CISCO,
        site="HQ",
        role="switch",
        routes=[RouteInfo(prefix="10.50.0.0/24", next_hop="192.168.1.1")],
    )
    monkeypatch.setattr(eval_module, "_load_device_from_inventory", lambda *args, **kwargs: fake_device)

    decision = evaluate_intent_state(
        run_id="run-routing-noop-exists",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.50.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.NO_OP
    assert "No routing changes required for sw1" in decision.reason
    assert not decision.diff


def test_evaluate_routing_remove_nonexistent_route_returns_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """When attempting to remove a route not in authoritative state, return NO_OP."""
    import net_agent_harness.tools.evaluation as eval_module
    from net_agent_harness.models.enums import DeviceVendor
    from net_agent_harness.models.inventory import DeviceInfo

    fake_device = DeviceInfo(
        name="sw1",
        vendor=DeviceVendor.CISCO,
        site="HQ",
        role="switch",
        routes=[],
    )
    monkeypatch.setattr(eval_module, "_load_device_from_inventory", lambda *args, **kwargs: fake_device)

    decision = evaluate_intent_state(
        run_id="run-routing-noop-absent",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_absent",
                    "attributes": {
                        "prefix": "10.99.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.NO_OP
    assert "No routing changes required for sw1" in decision.reason
    assert not decision.diff


def test_evaluate_routing_partial_diff_against_current_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """When one route exists and another is new, diff contains only the new route."""
    import net_agent_harness.tools.evaluation as eval_module
    from net_agent_harness.models.enums import DeviceVendor
    from net_agent_harness.models.inventory import DeviceInfo, RouteInfo

    fake_device = DeviceInfo(
        name="sw1",
        vendor=DeviceVendor.CISCO,
        site="HQ",
        role="switch",
        routes=[RouteInfo(prefix="10.10.0.0/24", next_hop="192.168.1.1")],
    )
    monkeypatch.setattr(eval_module, "_load_device_from_inventory", lambda *args, **kwargs: fake_device)

    decision = evaluate_intent_state(
        run_id="run-routing-partial",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.10.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                },
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {
                        "prefix": "10.20.0.0/24",
                        "next_hop": "192.168.1.1",
                    },
                },
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.APPLY
    assert len(decision.diff[0].changes) == 1
    assert decision.diff[0].changes[0].prefix == "10.20.0.0/24"


def test_routing_evaluation_deterministic_route_ops_order() -> None:
    """Static route operations in diff are deterministically ordered."""
    decision = evaluate_intent_state(
        run_id="run-routing-deterministic",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.90.0.0/24", "next_hop": "192.168.1.1"},
                },
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.10.0.0/24", "next_hop": "192.168.1.1"},
                },
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.50.0.0/24", "next_hop": "192.168.1.1"},
                },
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.APPLY
    prefixes = [op.prefix for op in decision.diff[0].changes]
    assert prefixes == ["10.10.0.0/24", "10.50.0.0/24", "10.90.0.0/24"]


def test_evaluate_routing_centralized_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unhandled exceptions during routing evaluation are caught and returned as BLOCKED."""
    import net_agent_harness.tools.evaluation as eval_module

    def _broken_loader(*args, **kwargs):
        raise RuntimeError("database disk image is malformed")

    monkeypatch.setattr(eval_module, "_load_device_from_inventory", _broken_loader)

    decision = evaluate_intent_state(
        run_id="run-routing-exception",
        domain="routing",
        site="HQ",
        device_names=["sw1"],
        desired_state={
            "operations": [
                {
                    "object_type": "static_route",
                    "operation": "ensure_present",
                    "attributes": {"prefix": "10.0.0.0/24", "next_hop": "192.168.1.1"},
                }
            ]
        },
        inventory_source="mock",
    )
    assert decision.decision == PlanDecisionType.BLOCKED
    assert "Routing evaluation failed with error: database disk image is malformed" in decision.reason

