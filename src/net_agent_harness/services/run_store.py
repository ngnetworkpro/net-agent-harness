import json
from datetime import timezone, datetime
from pathlib import Path
from ..models.enums import Capability, RunStage, WorkflowFamily


# Canonical stage sequences for each workflow family.
# These define the expected progression; actual runs may stop early.
WORKFLOW_STAGE_GRAPH: dict[WorkflowFamily, list[str]] = {
    WorkflowFamily.DISCOVERY: ["discover", "answer"],
    WorkflowFamily.CHANGE: ["plan", "render", "validate", "approval_pending", "execute"],
    WorkflowFamily.INCIDENT: ["incident", "review"],
    WorkflowFamily.SITE: [
        "discover",
        "allocate_ipam",
        "plan_topology",
        "plan_changes",
        "validate",
    ],
}


class RunStore:
    def __init__(self, runs_root: Path):
        self.runs_root = runs_root
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        import re
        if not re.match(r'^[\w-]+$', run_id):
            raise ValueError(f"Invalid run_id: {run_id}")
        path = self.runs_root / run_id
        if not path.resolve().is_relative_to(self.runs_root.resolve()):
            raise ValueError(f"Path traversal detected for run_id: {run_id}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run_file(self, run_id: str) -> Path:
        return self.run_dir(run_id) / 'run.json'

    def create_run(
        self,
        run_id: str,
        operator: str,
        stage: RunStage,
        model_name: str,
        workflow_family: WorkflowFamily | None = None,
        request_capability: Capability | None = None,
    ) -> Path:
        payload: dict = {
            'run_id': run_id,
            'operator': operator,
            'model_name': model_name,
            'current_stage': stage.value,
            'status': 'created',
            'stage_history': [
                {
                    'stage': stage.value,
                    'status': 'created',
                    'timestamp': self._now(),
                }
            ],
            'created_at': self._now(),
            'updated_at': self._now(),
        }
        if workflow_family is not None:
            payload['workflow_family'] = workflow_family.value
        if request_capability is not None:
            payload['request_capability'] = request_capability.value
        path = self.run_file(run_id)
        path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        return path

    def update_stage(self, run_id: str, stage: str, status: str, **extra) -> Path:
        path = self.run_file(run_id)
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['current_stage'] = stage
        payload['status'] = status
        payload['updated_at'] = self._now()
        entry = {'stage': stage, 'status': status, 'timestamp': self._now()}
        if extra:
            entry.update(extra)
        payload.setdefault('stage_history', []).append(entry)
        path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        return path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
