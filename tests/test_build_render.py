import pytest

from net_agent_harness.models.changes import (
    ChangeRequest,
    DeviceChange,
    PlanDecision,
    RequestedChange,
    ResolvedTarget,
    RollbackPlan,
    VlanChange,
    VlanSpec,
)
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk, NetworkDomain, PlanDecisionType
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


def test_build_render_rejects_vlan_removal_until_supported():
    with pytest.raises(ValueError, match="VLAN removal is not supported"):
        build_render_input(
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
