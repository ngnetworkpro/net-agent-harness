import json
from datetime import timezone, datetime
from pathlib import Path
from ..models.enums import RunStage


class RunStore:
    def __init__(self, runs_root: Path):
        self.runs_root = runs_root
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        path = self.runs_root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run_file(self, run_id: str) -> Path:
        return self.run_dir(run_id) / 'run.json'

    def create_run(self, run_id: str, operator: str, stage: RunStage, model_name: str) -> Path:
        payload = {
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
