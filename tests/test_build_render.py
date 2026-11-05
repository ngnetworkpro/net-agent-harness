import pytest

from net_agent_harness.models.artifacts import (
    OperationType,
    RenderTarget,
    SviRenderOp,
    VlanInterfaceRenderOp,
    VlanRenderPayload,
)
from net_agent_harness.models.changes import (
    ChangeRequest,
    DeviceChange,
    PlanDecision,
    PortSpec,
    RequestedChange,
    ResolvedTarget,
    RollbackPlan,
    SviChangeOperation,
    VlanChange,
    VlanSpec,
)
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import (
    AllowedVlansMode,
    ChangeRisk,
    NetworkDomain,
    PlanDecisionType,
    SwitchportMode,
)
from net_agent_harness.orchestration.build_render import build_render_input


def _base_change_request(plan_decision: PlanDecision | None) -> ChangeRequest:
    return ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="cr-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        target_scope="device",
        requested_change=RequestedChange(summary="test", intent="test"),
        rollback_plan=RollbackPlan(summary="rollback"),
        risk=ChangeRisk.LOW,
        resolved_targets=[
            ResolvedTarget(
                name="sw1",
                site="HQ",
                role="access-switch",
                platform="mist",
                primary_ip="10.0.0.10/24",
            )
        ],
        plan_decision=plan_decision,
    )


def test_build_render_rejects_missing_plan_decision():
    with pytest.raises(ValueError, match="plan_decision is required"):
        build_render_input(_base_change_request(plan_decision=None))


def test_build_render_rejects_non_apply_plan_decision():
    with pytest.raises(ValueError, match="Render rejected"):
        build_render_input(
            _base_change_request(
                plan_decision=PlanDecision(
                    decision=PlanDecisionType.NO_OP,
                    reason="done",
                    diff=[],
                )
            )
        )


def test_build_render_supports_vlan_removal():
    render_input = build_render_input(
        _base_change_request(
            plan_decision=PlanDecision(
                decision=PlanDecisionType.APPLY,
                reason="remove",
                diff=[
                    DeviceChange(
                        device="sw1",
                        domain=NetworkDomain.VLAN,
                        changes=VlanChange(
                            vlans_to_remove=[VlanSpec(id=11, name="users")],
                        ),
                    )
                ],
            )
        )
    )
    assert isinstance(render_input.payload, VlanRenderPayload)
    assert len(render_input.payload.vlan_ops) == 1
    vlan_op = render_input.payload.vlan_ops[0]
    assert vlan_op.vlan_id == 11
    assert vlan_op.vlan_name == "users"
    assert vlan_op.operation == OperationType.REMOVE
    assert vlan_op.target.name == "sw1"


def test_build_render_supports_svi_operations():
    render_input = build_render_input(
        _base_change_request(
            plan_decision=PlanDecision(
                decision=PlanDecisionType.APPLY,
                reason="svi ops",
                diff=[
                    DeviceChange(
                        device="sw1",
                        domain=NetworkDomain.VLAN,
                        changes=VlanChange(
                            operations=[
                                SviChangeOperation(
                                    op="create",
                                    vlan_id=220,
                                    interface="Vlan220",
                                    ip_address="10.220.0.1",
                                    prefix_length=24,
                                    status="apply",
                                ),
                                SviChangeOperation(
                                    op="remove",
                                    vlan_id=11,
                                    interface="Vlan11",
                                    status="apply",
                                ),
                                SviChangeOperation(
                                    op="create",
                                    vlan_id=300,
                                    interface="Vlan300",
                                    ip_address="10.300.0.1",
                                    prefix_length=24,
                                    status="skip",
                                ),
                            ]
                        ),
                    )
                ],
            )
        )
    )
    assert isinstance(render_input.payload, VlanRenderPayload)
    assert len(render_input.payload.svi_ops) == 2

    create_op = render_input.payload.svi_ops[0]
    assert create_op.vlan_id == 220
    assert create_op.interface_name == "Vlan220"
    assert create_op.ip_address == "10.220.0.1"
    assert create_op.prefix_length == 24
    assert create_op.operation == OperationType.ENSURE_PRESENT
    assert create_op.target.name == "sw1"

    remove_op = render_input.payload.svi_ops[1]
    assert remove_op.vlan_id == 11
    assert remove_op.interface_name == "Vlan11"
    assert remove_op.ip_address is None
    assert remove_op.prefix_length is None
    assert remove_op.operation == OperationType.REMOVE
    assert remove_op.target.name == "sw1"


def test_vlan_render_payload_has_ops_and_describe_ops_with_svi_and_trunk_attrs():
    payload = VlanRenderPayload(
        interface_ops=[
            VlanInterfaceRenderOp(
                target=RenderTarget(name="sw1"),
                interface_name="ge-0/0/24",
                switchport_mode=SwitchportMode.TRUNK,
                native_vlan=10,
                allowed_vlans=[10, 20, 30],
            )
        ],
        svi_ops=[
            SviRenderOp(
                target=RenderTarget(name="sw1"),
                vlan_id=220,
                operation=OperationType.ENSURE_PRESENT,
                interface_name="Vlan220",
                ip_address="10.220.0.1",
                prefix_length=24,
            ),
            SviRenderOp(
                target=RenderTarget(name="sw1"),
                vlan_id=11,
                operation=OperationType.REMOVE,
            ),
        ],
    )
    assert payload.has_ops() is True
    lines = payload.describe_ops()
    assert "Interface Operations:" in lines
    assert "  - ge-0/0/24: mode=trunk, native_vlan=10, allowed_vlans=[10, 20, 30], target=sw1" in lines
    assert "SVI Operations:" in lines
    assert "  - VLAN 220, interface=Vlan220, ip=10.220.0.1/24, operation=ensure_present, target=sw1" in lines
    assert "  - VLAN 11, operation=remove, target=sw1" in lines


def test_build_render_uses_authoritative_resolved_target_facts():
    render_input = build_render_input(
        _base_change_request(
            plan_decision=PlanDecision(
                decision=PlanDecisionType.APPLY,
                reason="apply",
                diff=[
                    DeviceChange(
                        device="sw1",
                        domain=NetworkDomain.VLAN,
                        changes=VlanChange(
                            vlans_to_create=[VlanSpec(id=220, name="Engineering")],
                        ),
                    )
                ],
            )
        )
    )

    target = render_input.payload.vlan_ops[0].target
    assert target.name == "sw1"
    assert target.site == "HQ"
    assert target.role == "access-switch"
    assert target.platform == "mist"
    assert target.primary_ip == "10.0.0.10/24"


def test_build_render_rejects_missing_resolved_target_platform():
    change_request = _base_change_request(
        plan_decision=PlanDecision(
            decision=PlanDecisionType.APPLY,
            reason="apply",
            diff=[
                DeviceChange(
                    device="sw1",
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[VlanSpec(id=220, name="Engineering")],
                    ),
                )
            ],
        )
    )
    change_request.resolved_targets[0].platform = None

    with pytest.raises(ValueError, match="missing platform"):
        build_render_input(change_request)


def test_build_render_sets_allowed_vlans_mode_for_trunk_and_access_ports():
    render_input = build_render_input(
        _base_change_request(
            plan_decision=PlanDecision(
                decision=PlanDecisionType.APPLY,
                reason="trunk and access ports",
                diff=[
                    DeviceChange(
                        device="sw1",
                        domain=NetworkDomain.VLAN,
                        changes=VlanChange(
                            ports_to_update=[
                                PortSpec(
                                    interface="ge-0/0/1",
                                    vlan_id=10,
                                    mode=SwitchportMode.ACCESS,
                                ),
                                PortSpec(
                                    interface="ge-0/0/23",
                                    mode=SwitchportMode.TRUNK,
                                    native_vlan=1,
                                    allowed_vlans=[10, 20],
                                ),
                                PortSpec(
                                    interface="ge-0/0/24",
                                    mode=SwitchportMode.TRUNK,
                                    native_vlan=1,
                                    allowed_vlans=[],
                                ),
                            ]
                        ),
                    )
                ],
            )
        )
    )

    assert isinstance(render_input.payload, VlanRenderPayload)
    ops_by_iface = {op.interface_name: op for op in render_input.payload.interface_ops}

    access_op = ops_by_iface["ge-0/0/1"]
    assert access_op.switchport_mode == SwitchportMode.ACCESS
    assert access_op.access_vlan == 10
    assert access_op.allowed_vlans_mode is None

    trunk_list_op = ops_by_iface["ge-0/0/23"]
    assert trunk_list_op.switchport_mode == SwitchportMode.TRUNK
    assert trunk_list_op.access_vlan is None
    assert trunk_list_op.allowed_vlans == [10, 20]
    assert trunk_list_op.allowed_vlans_mode == AllowedVlansMode.LIST

    trunk_all_op = ops_by_iface["ge-0/0/24"]
    assert trunk_all_op.switchport_mode == SwitchportMode.TRUNK
    assert trunk_all_op.access_vlan is None
    assert trunk_all_op.allowed_vlans == []
    assert trunk_all_op.allowed_vlans_mode == AllowedVlansMode.ALL

