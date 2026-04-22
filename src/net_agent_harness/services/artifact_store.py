import json
from pathlib import Path
from pydantic import BaseModel


class ArtifactStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        path = self.base_dir / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, run_id: str, name: str) -> Path:
        return self.run_dir(run_id) / f"{name}.json"

    def save_model(self, run_id: str, name: str, model: BaseModel) -> Path:
        path = self.artifact_path(run_id, name)
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_json(self, run_id: str, name: str, payload: dict) -> Path:
        path = self.artifact_path(run_id, name)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
