import pytest
from pydantic import ValidationError

from net_agent_harness.models.artifacts import (
    Finding,
    OperationType,
    RenderTarget,
    VlanRenderOp,
    VlanRenderPayload,
)
from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk, NetworkDomain


def test_pydantic_bounds_validation():
    from net_agent_harness.models.changes import PortSpec, VlanSpec

    # Test VLAN ID bounds (must be between 1 and 4094)
    with pytest.raises(ValidationError):
        VlanSpec(id=-5, name="Invalid")

    with pytest.raises(ValidationError):
        VlanSpec(id=5000, name="Invalid")

    # Valid VLAN ID should pass
    valid_vlan = VlanSpec(id=10, name="Valid")
    assert valid_vlan.id == 10

    # Test PortSpec mode enum
    with pytest.raises(ValidationError):
        PortSpec(interface="ge-0/0/1", vlan_id=220, mode="hybrid")

    # Valid PortSpec should pass
    valid_port = PortSpec(interface="ge-0/0/1", vlan_id=220, mode="access")
    assert valid_port.mode == "access"

def test_strict_structural_validation():
    from net_agent_harness.models.changes import (
        VlanAttributes,
        VlanDesiredState,
        VlanDesiredStateOperation,
    )

    # Test forbid extra properties
    with pytest.raises(ValidationError):
        VlanDesiredStateOperation(
            object_type="vlan",
            operation="ensure_present",
            attributes=VlanAttributes(vlan_id=10),
            invented_property="should fail"
        )

    with pytest.raises(ValidationError):
        VlanDesiredState(
            operations=[],
            apply_immediately=True
        )

def test_change_request_model():
    model = ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="change-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            requested_by="tester",
            intent="Add VLAN 220 to sw1",
        ),
        target_scope="device",
        rollback_plan=RollbackPlan(
            summary="Revert",
            trigger_conditions=["Error"],
            rollback_steps=["Undo"]
        ),
        risk=ChangeRisk.LOW,
    )
    assert model.scope.site == "HQ"


def test_requested_change_prefers_vlan_desired_state_model():
    requested = RequestedChange(
        summary="Update VLAN intent",
        intent="Ensure VLAN 220 exists",
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 220, "name": "Engineering"},
                }
            ]
        },
    )
    assert requested.desired_state.__class__.__name__ == "VlanDesiredState"


def test_finding_severity_is_constrained():
    with pytest.raises(ValidationError):
        Finding(code="X", severity="urgent", message="bad")


def test_vlan_render_payload_has_ops_and_describe_ops_with_operations():
    payload = VlanRenderPayload(
        vlan_ops=[
            VlanRenderOp(
                target=RenderTarget(name="sw1"),
                vlan_id=10,
                operation=OperationType.ENSURE_PRESENT,
                vlan_name="users",
            )
        ]
    )

    assert payload.has_ops() is True
    assert payload.describe_ops() == [
        "VLAN Operations:",
        "  - VLAN 10, name=users, operation=ensure_present, target=sw1",
    ]



def test_vlan_render_payload_has_ops_and_describe_ops_without_operations():
    payload = VlanRenderPayload()

    assert payload.has_ops() is False
    assert payload.describe_ops() == []


def test_vlan_render_input_runtime_type_hints() -> None:
    """VlanRenderInput field types resolve via get_type_hints at runtime without NameError."""
    import typing
    from net_agent_harness.models.artifacts import PortSpec, VlanRenderInput, VlanSpec

    hints = typing.get_type_hints(VlanRenderInput)
    assert hints["vlans_to_create"] == list[VlanSpec]
    assert hints["ports_to_update"] == list[PortSpec]


def test_change_request_runtime_type_hints() -> None:
    """ChangeRequest field types resolve via get_type_hints at runtime without NameError."""
    import typing
    from net_agent_harness.models.artifacts import RoutingRenderPayload
    from net_agent_harness.models.changes import ChangeRequest

    hints = typing.get_type_hints(ChangeRequest)
    assert hints["routing_payload"] == (RoutingRenderPayload | None)


def test_artifacts_all_contains_render_models() -> None:
    """artifacts module exports key models via __all__."""
    import net_agent_harness.models.artifacts as artifacts_mod

    assert hasattr(artifacts_mod, "__all__")
    assert "VlanRenderInput" in artifacts_mod.__all__
    assert "VlanSpec" in artifacts_mod.__all__
    assert "PortSpec" in artifacts_mod.__all__
    assert "RoutingRenderPayload" in artifacts_mod.__all__
    assert "StaticRouteOp" in artifacts_mod.__all__


def test_device_change_typed_vlan_validation() -> None:
    """DeviceChange enforces typed validation for VLAN domain and rejects primitives."""
    from net_agent_harness.models.changes import DeviceChange, VlanChange

    # 1. Reject int
    with pytest.raises(ValidationError):
        DeviceChange(device="sw1", domain=NetworkDomain.VLAN, changes=123)

    # 2. Reject string
    with pytest.raises(ValidationError):
        DeviceChange(device="sw1", domain=NetworkDomain.VLAN, changes="malformed")

    # 3. Valid VlanChange passes
    dc = DeviceChange(device="sw1", domain=NetworkDomain.VLAN, changes=VlanChange(operations=[]))
    assert isinstance(dc.changes, VlanChange)


def test_device_change_typed_routing_validation() -> None:
    """DeviceChange enforces typed validation for ROUTING domain and rejects malformed entries."""
    from net_agent_harness.models.artifacts import OperationType, RenderTarget, StaticRouteOp
    from net_agent_harness.models.changes import DeviceChange

    # 1. Reject primitive int
    with pytest.raises(ValidationError):
        DeviceChange(device="r1", domain=NetworkDomain.ROUTING, changes=123)

    # 2. Reject None
    with pytest.raises(ValidationError):
        DeviceChange(device="r1", domain=NetworkDomain.ROUTING, changes=None)

    # 3. Reject primitive elements in list
    with pytest.raises(ValidationError):
        DeviceChange(device="r1", domain=NetworkDomain.ROUTING, changes=[123])

    # 4. Valid StaticRouteOp list passes
    op = StaticRouteOp(
        prefix="10.0.0.0/24",
        next_hop="192.168.1.1",
        operation=OperationType.ENSURE_PRESENT,
        target=RenderTarget(name="r1", platform="ios"),
    )
    dc = DeviceChange(device="r1", domain=NetworkDomain.ROUTING, changes=[op])
    assert len(dc.changes) == 1


def test_vlan_change_rejects_unknown_keys() -> None:
    """VlanChange extra='forbid' is not bypassed by unknown keys."""
    from net_agent_harness.models.changes import VlanChange

    with pytest.raises(ValidationError):
        VlanChange.model_validate({"bogus_key": 999})

