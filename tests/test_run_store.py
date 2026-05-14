import json
from net_agent_harness.models.enums import RunStage
from net_agent_harness.services.run_store import RunStore


def test_run_store_path_traversal(tmp_path):
    import pytest
    store = RunStore(tmp_path)

    with pytest.raises(ValueError, match="Invalid run_id"):
        store.run_dir("../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid run_id"):
        store.run_dir("run-1/nested")

def test_run_store_stage_updates(tmp_path):
    store = RunStore(tmp_path)
    path = store.create_run('run-1', 'tester', RunStage.PLAN, 'llama3.2')
    store.update_stage('run-1', 'plan', 'running')
    store.update_stage('run-1', 'plan', 'completed', artifact='change_request')

    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['current_stage'] == 'plan'
    assert payload['status'] == 'completed'
    assert len(payload['stage_history']) >= 3
