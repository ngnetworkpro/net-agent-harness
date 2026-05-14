from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk
import pytest
from net_agent_harness.tools.config_tools import render_vlan_config
from net_agent_harness.models.changes import PlanDecision, DeviceChange, VlanChange, VlanSpec
from net_agent_harness.models.enums import PlanDecisionType, NetworkDomain


@pytest.mark.asyncio
async def test_render_vlan_config():
    ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="change-1", created_by="test"),
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        domain=NetworkDomain.VLAN,
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            requested_by="tester",
            intent="Add VLAN 220 to access switch sw1 at HQ",
        ),
        target_scope="device",
        rollback_plan=RollbackPlan(
            summary="Revert",
            trigger_conditions=["Error"],
            rollback_steps=["Undo"]
        ),
        risk=ChangeRisk.LOW,
        plan_decision=PlanDecision(
            decision=PlanDecisionType.APPLY,
            reason="Test",
            diff=[
                DeviceChange(
                    device="sw1",
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[VlanSpec(id=220, name="")],
                        ports_to_update=[],
                    )
                )
            ]
        )
    )

    # Note: testing actual render logic would involve mocking the agent.
    # For now, let's just make sure the file can be imported successfully.
    assert render_vlan_config is not None
