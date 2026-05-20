"""Tests for generalised RunStore with workflow_family and request_capability (Issue #45)."""
import json

from net_agent_harness.models.enums import Capability, RunStage, WorkflowFamily
from net_agent_harness.services.run_store import WORKFLOW_STAGE_GRAPH, RunStore


class TestWorkflowFamilyEnum:
    def test_values_exist(self):
        assert WorkflowFamily.DISCOVERY.value == "discovery"
        assert WorkflowFamily.CHANGE.value == "change"
        assert WorkflowFamily.INCIDENT.value == "incident"


class TestWorkflowStageGraph:
    def test_change_graph_includes_expected_stages(self):
        stages = WORKFLOW_STAGE_GRAPH[WorkflowFamily.CHANGE]
        assert "plan" in stages
        assert "render" in stages
        assert "validate" in stages
        assert "execute" in stages

    def test_discovery_graph_includes_discover_and_answer(self):
        stages = WORKFLOW_STAGE_GRAPH[WorkflowFamily.DISCOVERY]
        assert "discover" in stages
        assert "answer" in stages

    def test_incident_graph_defined(self):
        stages = WORKFLOW_STAGE_GRAPH[WorkflowFamily.INCIDENT]
        assert len(stages) >= 1


class TestRunStoreWorkflowFamily:
    def test_create_run_without_workflow_family(self, tmp_path):
        store = RunStore(tmp_path)
        path = store.create_run("run-basic", "tester", RunStage.PLAN, "llama3")
        payload = json.loads(path.read_text())
        assert "workflow_family" not in payload
        assert "request_capability" not in payload

    def test_create_run_with_workflow_family(self, tmp_path):
        store = RunStore(tmp_path)
        path = store.create_run(
            "run-change",
            "tester",
            RunStage.PLAN,
            "llama3",
            workflow_family=WorkflowFamily.CHANGE,
            request_capability=Capability.CHANGE,
        )
        payload = json.loads(path.read_text())
        assert payload["workflow_family"] == "change"
        assert payload["request_capability"] == "change"

    def test_create_run_discovery_workflow(self, tmp_path):
        store = RunStore(tmp_path)
        path = store.create_run(
            "run-disco",
            "tester",
            RunStage.DISCOVER,
            "llama3",
            workflow_family=WorkflowFamily.DISCOVERY,
            request_capability=Capability.TOPOLOGY,
        )
        payload = json.loads(path.read_text())
        assert payload["workflow_family"] == "discovery"
        assert payload["request_capability"] == "topology"

    def test_create_run_incident_workflow(self, tmp_path):
        store = RunStore(tmp_path)
        path = store.create_run(
            "run-incident",
            "tester",
            RunStage.PLAN,
            "llama3",
            workflow_family=WorkflowFamily.INCIDENT,
            request_capability=Capability.INCIDENT,
        )
        payload = json.loads(path.read_text())
        assert payload["workflow_family"] == "incident"
        assert payload["request_capability"] == "incident"

    def test_stage_history_preserved_with_workflow_family(self, tmp_path):
        store = RunStore(tmp_path)
        path = store.create_run(
            "run-hist",
            "tester",
            RunStage.PLAN,
            "llama3",
            workflow_family=WorkflowFamily.CHANGE,
        )
        store.update_stage("run-hist", "plan", "completed", artifact="change_request")
        payload = json.loads(path.read_text())
        assert len(payload["stage_history"]) >= 2
        assert payload["workflow_family"] == "change"
