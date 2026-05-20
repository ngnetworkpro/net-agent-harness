from pathlib import Path
from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk, NetworkDomain, RunStage, WorkflowFamily
from net_agent_harness.services.artifact_store import ArtifactStore
from net_agent_harness.services.run_store import RunStore


def test_artifact_store_path_traversal(tmp_path: Path):
    import pytest
    store = ArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="Invalid run_id"):
        store.run_dir("../../../etc/passwd")

def test_save_model(tmp_path: Path):
    store = ArtifactStore(tmp_path)
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
    path = store.save_model("run-1", "change_request", model)
    assert path.exists()
    assert path.name == "change_request.json"


def test_resolve_lineage_reconstructs_change_workflow(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    run_store = RunStore(tmp_path)
    run_id = "run-lineage"
    run_store.create_run(
        run_id=run_id,
        operator="test",
        stage=RunStage.PLAN,
        model_name="test-model",
        workflow_family=WorkflowFamily.CHANGE,
    )
    run_store.update_stage(run_id, "plan", "completed")
    run_store.update_stage(run_id, "render", "completed")
    run_store.update_stage(run_id, "validate", "pass")
    run_store.update_stage(run_id, "approval_pending", "blocked")

    store.save_json(
        run_id,
        "change_request",
        {"meta": {"artifact_id": "cr-1", "parent_artifact_id": None, "child_artifact_ids": ["render-1"]}},
    )
    store.save_json(
        run_id,
        "config_render",
        {"meta": {"artifact_id": "render-1", "parent_artifact_id": "cr-1", "child_artifact_ids": ["vr-1"]}},
    )
    store.save_json(
        run_id,
        "validation_report",
        {"meta": {"artifact_id": "vr-1", "parent_artifact_id": "render-1", "child_artifact_ids": ["ep-1"]}},
    )
    store.save_json(
        run_id,
        "execution_plan",
        {"meta": {"artifact_id": "ep-1", "parent_artifact_id": "vr-1", "child_artifact_ids": []}},
    )

    lineage = store.resolve_lineage(run_id)

    assert lineage["reconstructable"] is True
    nodes = {node["artifact_name"]: node for node in lineage["nodes"]}
    assert nodes["config_render"]["parent_artifact_id"] == "cr-1"
    assert nodes["validation_report"]["parent_artifact_id"] == "render-1"
    assert nodes["execution_plan"]["parent_artifact_id"] == "vr-1"
    assert nodes["execution_plan"]["blocked"] is False


def test_resolve_lineage_blocks_downstream_when_upstream_failed(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    run_store = RunStore(tmp_path)
    run_id = "run-lineage-failed"
    run_store.create_run(
        run_id=run_id,
        operator="test",
        stage=RunStage.PLAN,
        model_name="test-model",
        workflow_family=WorkflowFamily.CHANGE,
    )
    run_store.update_stage(run_id, "plan", "completed")
    run_store.update_stage(run_id, "render", "failed")

    store.save_json(
        run_id,
        "change_request",
        {"meta": {"artifact_id": "cr-1", "parent_artifact_id": None, "child_artifact_ids": ["render-1"]}},
    )
    store.save_json(
        run_id,
        "config_render",
        {"meta": {"artifact_id": "render-1", "parent_artifact_id": "cr-1", "child_artifact_ids": []}},
    )

    lineage = store.resolve_lineage(run_id)
    nodes = {node["artifact_name"]: node for node in lineage["nodes"]}

    assert nodes["validation_report"]["blocked"] is True
    assert "upstream_failed" in nodes["validation_report"]["block_reasons"]
    assert "missing_artifact" in nodes["validation_report"]["block_reasons"]
