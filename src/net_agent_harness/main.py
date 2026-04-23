import json
from typing import Any
import uuid
from pathlib import Path
import typer
from rich import print
from .agents.change_planner import change_planner
from .config import settings
from .models.artifacts import ConfigRender
from .models.changes import ChangeRequest, PlannedChange
from .models.common import ArtifactMeta
from datetime import UTC, datetime
from .models.enums import RunStage
from .orchestration.coordinator import StageCoordinator
from .orchestration.run_context import RunContextData
from .services.artifact_store import ArtifactStore
from .services.run_store import RunStore
from .tools.config_tools import build_stub_config_render
from .tools.validation_tools import validate_config_render

app = typer.Typer(help='Network agent harness prototype')
run_app = typer.Typer(help='Run end-to-end stage pipelines')
app.add_typer(run_app, name='run')


def get_runs_root() -> Path:
    return settings.runs_dir

def ensure_renderable(change_request: ChangeRequest) -> None:
    if change_request.clarifications_needed:
        msg = "; ".join(change_request.clarifications_needed)
        raise typer.BadParameter(
            f"Cannot render config: clarification required: {msg}"
        )

    if change_request.target_scope == "ambiguous":
        raise typer.BadParameter(
            "Cannot render config: request target is ambiguous"
        )

    if not change_request.resolved_targets:
        raise typer.BadParameter(
            "Cannot render config: no concrete targets were resolved from inventory"
        )

@app.command()
def plan(request: str, operator: str = 'local-user'):
    run_id = f'run-{uuid.uuid4().hex[:8]}'
    runs_root = get_runs_root()
    run_store = RunStore(runs_root)
    artifact_store = ArtifactStore(runs_root)

    deps = RunContextData(
        run_id=run_id,
        stage=RunStage.PLAN,
        operator=operator,
        model_name=settings.ollama_model,
        require_approval_for_execute=settings.require_approval_for_execute,
        inventory_source=settings.inventory_source,
    )

    run_store.create_run(
        run_id=run_id,
        operator=operator,
        stage=RunStage.PLAN,
        model_name=settings.ollama_model,
    )
    run_store.update_stage(run_id, 'plan', 'running')
    result = change_planner.run_sync(request, deps=deps, model_settings={'temperature': 0.0})
    planned = result.output

    artifact = ChangeRequest(
        meta=ArtifactMeta(
            run_id=run_id,
            artifact_id=f"change-request-{run_id}",
            version=1,
            created_at=datetime.now(UTC),
            created_by=operator,
        ),
        scope=planned.scope,
        target_scope=planned.target_scope,
        resolved_targets=planned.resolved_targets,
        clarifications_needed=planned.clarifications_needed,
        requested_change=planned.requested_change,
        risk=planned.risk,
        assumptions=planned.assumptions,
        dependencies=planned.dependencies,
        rollback_plan=planned.rollback_plan,
    )

    artifact_path = artifact_store.save_model(run_id, 'change_request', artifact)
    run_store.update_stage(run_id, 'plan', 'completed', artifact='change_request')
    print({
        'run_id': run_id,
        'artifact_path': str(artifact_path),
        'output': artifact.model_dump(mode='json')
    })

@app.command()
def render(change_request_file_or_obj: Any):
    """Render config from change request (file or object)."""
    if isinstance(change_request_file_or_obj, Path):
        change_request = ChangeRequest.model_validate_json(
            change_request_file_or_obj.read_text(encoding='utf-8')
        )
    else:
        change_request = change_request_file_or_obj

    ensure_renderable(change_request)
    artifact_store = ArtifactStore(get_runs_root())
    run_store = RunStore(get_runs_root())
    run_store.update_stage(change_request.meta.run_id, 'render', 'running')
    render_result = build_stub_config_render(change_request)
    artifact_path = artifact_store.save_model(change_request.meta.run_id, 'config_render', render_result)
    run_store.update_stage(change_request.meta.run_id, 'render', 'completed', artifact='config_render')
    print({'run_id': change_request.meta.run_id, 'artifact_path': str(artifact_path), 'output': render_result.model_dump(mode='json')})

@app.command()
def validate(config_render_file_or_obj: Any):
    """Validate config from change request (file or object)."""
    if isinstance(config_render_file_or_obj, Path):
        payload = json.loads(config_render_file_or_obj.read_text(encoding='utf-8'))
        config_render = ConfigRender.model_validate(payload)
    else:
        config_render = config_render_file_or_obj

    artifact_store = ArtifactStore(get_runs_root())
    run_store = RunStore(get_runs_root())
    run_store.update_stage(config_render.meta.run_id, 'validate', 'running')
    validation_result = validate_config_render(config_render)
    artifact_path = artifact_store.save_model(config_render.meta.run_id, 'validation_report', validation_result)
    final_status = 'completed' if validation_result.overall_status.value == 'pass' else validation_result.overall_status.value
    run_store.update_stage(
        config_render.meta.run_id,
        'validate',
        final_status,
        artifact='validation_report',
        approved_for_execution=validation_result.approved_for_execution,
    )
    print({'run_id': config_render.meta.run_id, 'artifact_path': str(artifact_path), 'output': validation_result.model_dump(mode='json')})


@run_app.command('stages')
@app.command()
def run_stages(artifact_path: Path):
    """Run all post-plan stages for an existing change request."""
    change_request = ChangeRequest.model_validate_json(artifact_path.read_text())
    # Same validation as `render()` uses
    ensure_renderable(change_request)
    run_id = change_request.meta.run_id
    # Render config
    render(change_request)
    # Review
    validate(change_request)
    # # Finalize
    # finalize(change_request)
    print(f"✅ Full pipeline complete: {run_id}")


@app.command()
def show_run(run_id: str):
    run_dir = get_runs_root() / run_id
    if not run_dir.exists():
        raise typer.BadParameter(f'Run directory not found: {run_dir}')
    files = sorted(str(p) for p in run_dir.glob('*.json'))
    print(json.dumps({'run_id': run_id, 'files': files}, indent=2))


if __name__ == '__main__':
    app()
