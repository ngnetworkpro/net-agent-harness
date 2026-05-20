import pytest
import typer
from unittest.mock import patch, AsyncMock

from net_agent_harness.main import ask, show_run


def test_show_run_rejects_invalid_run_id():
    with pytest.raises(typer.BadParameter, match="Invalid run_id"):
        show_run("../../etc")


def test_ask_rejects_change_requests() -> None:
    with pytest.raises(typer.BadParameter, match="Use the plan workflow"):
        ask("Add VLAN 10 to sw1")


@pytest.mark.asyncio
@patch("net_agent_harness.main.run_agent_with_spinner", new_callable=AsyncMock)
@patch("net_agent_harness.main.resolve_from_scope")
@patch("net_agent_harness.main.evaluate_intent_state")
async def test_async_plan_populates_plan_decision_when_llm_returns_none(
    mock_evaluate_intent_state,
    mock_resolve_from_scope,
    mock_run_agent_with_spinner,
    tmp_path,
    monkeypatch
) -> None:
    from net_agent_harness.models.changes import PlannedChange, RequestedChange, RollbackPlan
    from net_agent_harness.models.common import ScopeRef
    from net_agent_harness.models.enums import ChangeRisk, TargetScope
    from net_agent_harness.main import _async_plan

    # Set the runs directory to our temp path so we don't mess with real runs
    from net_agent_harness.config import settings
    monkeypatch.setattr(settings, "runs_dir", tmp_path)

    # 1. Mock run_agent_with_spinner to return a PlannedChange with plan_decision=None
    mock_run_agent_with_spinner.return_value = PlannedChange(
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        target_scope=TargetScope.device,
        requested_change=RequestedChange(
            summary="Create VLAN 23",
            intent="create_vlan",
            desired_state={"operations": []}
        ),
        risk=ChangeRisk.LOW,
        rollback_plan=RollbackPlan(summary="Revert"),
        plan_decision=None, # LLM omitted plan_decision!
    )

    # 2. Mock resolve_from_scope to return a target
    from net_agent_harness.models.changes import ResolvedTarget
    mock_resolve_from_scope.return_value = [
        ResolvedTarget(name="sw1", site="HQ", platform="mist")
    ]

    # 3. Mock evaluate_intent_state to return a PlanDecision
    from net_agent_harness.models.changes import PlanDecision
    from net_agent_harness.models.enums import PlanDecisionType
    mock_evaluate_intent_state.return_value = PlanDecision(
        decision=PlanDecisionType.APPLY,
        reason="VLAN 23 must be created on sw1",
        diff=[]
    )

    # 4. Call _async_plan
    await _async_plan("Create VLAN 23 on sw1 at HQ")

    # 5. Verify evaluate_intent_state was called because planned.plan_decision was None
    mock_evaluate_intent_state.assert_called_once()

