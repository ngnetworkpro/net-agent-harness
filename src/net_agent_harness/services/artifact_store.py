import json
from pathlib import Path
from pydantic import BaseModel


class ArtifactStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        import re
        if not re.match(r'^[\w-]+$', run_id):
            raise ValueError(f"Invalid run_id: {run_id}")
        path = self.base_dir / run_id
        if not path.resolve().is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"Path traversal detected for run_id: {run_id}")
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

    def resolve_lineage(self, run_id: str) -> dict:
        workflow = [
            ("change_request", "plan"),
            ("config_render", "render"),
            ("validation_report", "validate"),
            ("execution_plan", "approval_pending"),
            ("execution_result", "execute"),
        ]
        run_statuses = self._read_stage_statuses(run_id)
        nodes: list[dict] = []
        upstream_ok = True

        for artifact_name, stage_name in workflow:
            path = self.artifact_path(run_id, artifact_name)
            exists = path.exists()
            node: dict = {
                "artifact_name": artifact_name,
                "stage": stage_name,
                "path": str(path),
                "exists": exists,
                "blocked": False,
                "block_reasons": [],
            }
            if exists:
                payload = json.loads(path.read_text(encoding="utf-8"))
                meta = payload.get("meta", {})
                node["artifact_id"] = meta.get("artifact_id")
                node["parent_artifact_id"] = meta.get("parent_artifact_id")
                node["child_artifact_ids"] = meta.get("child_artifact_ids", [])
            else:
                node["artifact_id"] = None
                node["parent_artifact_id"] = None
                node["child_artifact_ids"] = []

            stage_status = run_statuses.get(stage_name)
            node["stage_status"] = stage_status

            if not upstream_ok:
                node["blocked"] = True
                node["block_reasons"].append("upstream_failed")
            if not exists:
                node["blocked"] = True
                node["block_reasons"].append("missing_artifact")

            nodes.append(node)

            if stage_status in {"failed", "fail", "warn", "blocked", "rejected", "cancelled"}:
                upstream_ok = False
            if not exists:
                upstream_ok = False

        return {
            "run_id": run_id,
            "nodes": nodes,
            "reconstructable": all(node["exists"] for node in nodes[:4]),
        }

    def _read_stage_statuses(self, run_id: str) -> dict[str, str]:
        run_file = self.run_dir(run_id) / "run.json"
        if not run_file.exists():
            return {}
        payload = json.loads(run_file.read_text(encoding="utf-8"))
        statuses: dict[str, str] = {}
        for entry in payload.get("stage_history", []):
            stage = entry.get("stage")
            status = entry.get("status")
            if isinstance(stage, str) and isinstance(status, str):
                statuses[stage] = status
        return statuses
