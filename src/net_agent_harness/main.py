import json
import uuid
from pathlib import Path
import typer
import asyncio
from rich import print
from .agents.change_planner import change_planner
from .orchestration.stream_utils import run_agent_with_spinner
from .config import settings
from .models.artifacts import ConfigRender
from .models.changes import ChangeRequest, PlannedChange
from .models.common import ArtifactMeta
from datetime import timezone, datetime
from .models.enums import RunStage
from .orchestration.coordinator import StageCoordinator
from .orchestration.run_context import RunContextData
from .services.artifact_store import ArtifactStore
from .services.run_store import RunStore
from .tools.config_tools import build_stub_config_render
from .tools.validation_tools import validate_config_render
from .tools.inventory_tools import resolve_from_scope

from .orchestration.intent_router import route_intent
from .orchestration.domain_loader import load_domain_context, DomainLoadError

app = typer.Typer(help='Network agent harness prototype')
run_app = typer.Typer(help='Run end-to-end stage pipelines')
app.add_typer(run_app, name='run')


def get_runs_root() -> Path:
    return settings.runs_dir

def ensure_renderable(change_request: ChangeRequest) -> None:
    # Short-circuit: if the planner already evaluated this as a no_op,
    # there is nothing to render. Exit cleanly rather than failing on
    # missing targets, which would be misleading.
    if (
        change_request.plan_decision is not None
        and change_request.plan_decision.decision.value == "no_op"
    ):
        reason = change_request.plan_decision.reason
        raise typer.Exit(
            message=f"[no_op] Nothing to render: {reason}"
        )

    if (
        change_request.plan_decision is not None
        and change_request.plan_decision.decision.value == "blocked"
    ):
        reason = change_request.plan_decision.reason
        raise typer.BadParameter(f"Cannot render config: blocked: {reason}")

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
    try:
        asyncio.run(_async_plan(request, operator))
    except Exception as e:
        typer.secho(f"Error executing plan: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

async def _async_plan(request: str, operator: str = 'local-user'):
    route = route_intent(request)
    
    if route.domain in {"generic", "unknown"} or route.confidence < 0.65:
        raise typer.BadParameter(
            "Could not confidently determine the network domain from your request. "
            "Please explicitly mention 'vlan', 'acl', 'routing', etc., or provide more context."
        )
        
    try:
        domain_context = load_domain_context(route.domain)
    except DomainLoadError as exc:
        raise typer.Exit(code=2) from exc
    
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
        route_result=route,
        domain_context=domain_context,
    )

    run_store.create_run(
        run_id=run_id,
        operator=operator,
        stage=RunStage.PLAN,
        model_name=settings.ollama_model,
    )
    run_store.update_stage(run_id, 'plan', 'running')
    
    planned = await run_agent_with_spinner(
        agent=change_planner,
        prompt=request,
        deps=deps,
        model_settings={'temperature': 0.0},
        message="Evaluating configuration intent..."
    )

    # --- Authoritative target resolution ---
    resolved_targets = resolve_from_scope(
        scope=planned.scope,
        inventory_source=settings.inventory_source,
    )

    if not resolved_targets:
        scope_summary = (
            f"devices={planned.scope.device_names or 'none'}, "
            f"site={planned.scope.site or 'none'}, "
            f"roles={planned.scope.device_roles or planned.scope.requested_role or 'none'}"
        )
        run_store.update_stage(run_id, 'plan', 'blocked',
                            reason=f"No inventory match for scope: {scope_summary}")
        raise typer.BadParameter(
            f"Could not resolve target devices. "
            f"Scope was: {scope_summary}. "
            f"Verify devices and site exist in inventory source '{settings.inventory_source}'."
        )
    # --- End resolution ---

    artifact = ChangeRequest(
        meta=ArtifactMeta(
            run_id=run_id,
            artifact_id=f"change-request-{run_id}",
            version=1,
            created_at=datetime.now(timezone.utc),
            created_by=operator,
        ),
        scope=planned.scope,
        target_scope=planned.target_scope,
        resolved_targets=resolved_targets,
        clarifications_needed=planned.clarifications_needed,
        requested_change=planned.requested_change,
        risk=planned.risk,
        assumptions=planned.assumptions,
        dependencies=planned.dependencies,
        rollback_plan=planned.rollback_plan,
        plan_decision=planned.plan_decision,  # carry the no_op/apply/blocked decision forward
    )

    artifact_path = artifact_store.save_model(run_id, 'change_request', artifact)
    run_store.update_stage(run_id, 'plan', 'completed', artifact='change_request')
    print({
        'run_id': run_id,
        'artifact_path': str(artifact_path),
        'output': artifact.model_dump(mode='json')
    })

# ── Internal helpers (no Typer annotation constraints) ───────────────────────

def _run_render(change_request: ChangeRequest) -> None:
    """Core render logic, callable from CLI or programmatically."""
    ensure_renderable(change_request)
    artifact_store = ArtifactStore(get_runs_root())
    run_store = RunStore(get_runs_root())
    run_store.update_stage(change_request.meta.run_id, 'render', 'running')
    render_result = build_stub_config_render(change_request)
    artifact_path = artifact_store.save_model(change_request.meta.run_id, 'config_render', render_result)
    run_store.update_stage(change_request.meta.run_id, 'render', 'completed', artifact='config_render')
    print({'run_id': change_request.meta.run_id, 'artifact_path': str(artifact_path), 'output': render_result.model_dump(mode='json')})


def _run_validate(config_render: ConfigRender) -> None:
    """Core validate logic, callable from CLI or programmatically."""
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


# ── CLI commands (Typer-safe: only concrete scalar/Path types) ────────────────

@app.command()
def render(change_request_file: Path):
    """Render config from a change-request JSON file."""
    change_request = ChangeRequest.model_validate_json(
        change_request_file.read_text(encoding='utf-8')
    )
    _run_render(change_request)


@app.command()
def validate(config_render_file: Path):
    """Validate config from a config-render JSON file."""
    payload = json.loads(config_render_file.read_text(encoding='utf-8'))
    config_render = ConfigRender.model_validate(payload)
    _run_validate(config_render)


@run_app.command('stages')
@app.command()
def run_stages(artifact_path: Path):
    """Run all post-plan stages for an existing change request."""
    change_request = ChangeRequest.model_validate_json(artifact_path.read_text())
    ensure_renderable(change_request)
    run_id = change_request.meta.run_id
    # Render config
    _run_render(change_request)
    # Validate
    # Note: run_stages passes a ChangeRequest here, so we need to build the render first
    # validate operates on a ConfigRender; for the pipeline, reload from disk
    render_artifact = get_runs_root() / run_id / 'config_render.json'
    _run_validate(ConfigRender.model_validate_json(render_artifact.read_text()))
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
