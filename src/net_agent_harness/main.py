import json
import re
import traceback
import uuid
from pathlib import Path
import typer
import asyncio
from rich import print
from pydantic_ai.exceptions import ModelHTTPError
from .agents.change_planner import change_planner
from .orchestration.stream_utils import run_agent_with_spinner
from .config import settings
from .models.artifacts import ConfigRender
from .models.changes import ChangeRequest, PlannedChange, ResolvedTarget
from .models.common import ArtifactMeta
from .models.resources import (
    DeviceResourceRef,
    ResourceRelationship,
    ResourceRef,
    SiteResourceRef,
    SiteToDeviceRelationship,
)
from datetime import timezone, datetime
from .models.enums import RunStage
from .orchestration.coordinator import StageCoordinator
from .orchestration.run_context import RunContextData
from .services.artifact_store import ArtifactStore
from .services.run_store import RunStore
from .services.run_progress_reporter import RunProgressReporter
from .tools.inventory_tools import resolve_from_scope
from .tools.evaluation import evaluate_intent_state
from .tools.validation_tools import validate_config_render 

from .orchestration.desired_state_normalizer import normalize_desired_state
from .orchestration.dispatcher import DispatchMode, dispatch_request
from .orchestration.intent_router import route_intent
from .orchestration.read_only_answer import build_read_only_answer
from .orchestration.domain_loader import load_domain_context, DomainLoadError
from .orchestration.rollback_builder import build_rollback_plan
from .orchestration.scope_validator import ScopeValidationError, validate_target_scope
from .models.enums import Capability, PlanDecisionType

app = typer.Typer(help='Network agent harness prototype')
run_app = typer.Typer(help='Run end-to-end stage pipelines')
app.add_typer(run_app, name='run')


def _validate_run_id(run_id: str) -> str:
    if not re.match(r'^[\w-]+$', run_id):
        raise typer.BadParameter(f"Invalid run_id: {run_id!r}")
    return run_id


def get_runs_root() -> Path:
    return settings.runs_dir


def _build_authoritative_resource_refs(
    planned: PlannedChange,
    resolved_targets: list[ResolvedTarget],
) -> tuple[list[ResourceRef], list[ResourceRelationship]]:
    resources: list[ResourceRef] = []
    relationships: list[ResourceRelationship] = []

    if planned.scope.site:
        site_ref = SiteResourceRef(site_name=planned.scope.site)
        resources.append(site_ref)
    else:
        site_ref = None

    for target in resolved_targets:
        device_ref = DeviceResourceRef(device_name=target.name, site_name=target.site or planned.scope.site)
        resources.append(device_ref)
        if site_ref is not None:
            relationships.append(
                SiteToDeviceRelationship(
                    site=site_ref,
                    device=device_ref,
                )
            )

    return resources, relationships


def _merge_unique_resources(
    planned_resources: list[ResourceRef],
    authoritative_resources: list[ResourceRef],
) -> list[ResourceRef]:
    """Merge resource refs, deduplicating by canonical identity.

    Authoritative entries are processed first so they win on key collision
    (e.g. a DeviceResourceRef with site_name populated beats one without).
    """
    merged: list[ResourceRef] = []
    seen: set[str] = set()
    for resource in [*authoritative_resources, *planned_resources]:
        key = resource.canonical_key()
        if key in seen:
            continue
        seen.add(key)
        merged.append(resource)
    return merged


def _merge_unique_relationships(
    planned_relationships: list[ResourceRelationship],
    authoritative_relationships: list[ResourceRelationship],
) -> list[ResourceRelationship]:
    """Merge relationships, deduplicating by canonical identity.

    Authoritative entries are processed first so they win on key collision
    (e.g. a site_to_device with site_name populated on the device ref
    beats one where site_name is null).
    """
    merged: list[ResourceRelationship] = []
    seen: set[str] = set()
    for relationship in [*authoritative_relationships, *planned_relationships]:
        key = relationship.canonical_key()
        if key in seen:
            continue
        seen.add(key)
        merged.append(relationship)
    return merged


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


def _run_direct_answer(request: str, capability: Capability, operator: str) -> None:
    answer = build_read_only_answer(
        question=request,
        capability=capability,
        inventory_source=settings.inventory_source,
        operator=operator,
    )
    runs_root = get_runs_root()
    run_store = RunStore(runs_root)
    reporter = RunProgressReporter(run_store, answer.meta.run_id)
    artifact_store = ArtifactStore(runs_root)
    run_store.create_run(
        run_id=answer.meta.run_id,
        operator=operator,
        stage=RunStage.DISCOVER,
        model_name=settings.ollama_model,
    )
    reporter.update(RunStage.DISCOVER.value, "running", "🔎 Building read-only answer...")
    artifact_path = artifact_store.save_model(answer.meta.run_id, "answer", answer)
    reporter.update(
        RunStage.DISCOVER.value,
        "completed",
        f"✅ answer complete: {artifact_path}",
        artifact="answer",
        route_capability=capability.value,
    )
    print(
        {
            "run_id": answer.meta.run_id,
            "artifact_path": str(artifact_path),
            "output": answer.model_dump(mode="json"),
        }
    )

@app.command()
def plan(request: str, operator: str = 'local-user'):
    try:
        asyncio.run(_async_plan(request, operator))
    except typer.BadParameter as e:
        typer.secho(f"Error executing plan: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except ModelHTTPError as e:
        typer.secho(f"API Connection Error: Failed to communicate with the model provider ({e.status_code}).\nDetails: {e.body}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except Exception as e:
        traceback.print_exc()
        typer.secho(f"Error executing plan: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@app.command()
def ask(request: str, operator: str = "local-user"):
    route = route_intent(request)
    dispatch = dispatch_request(route)
    if dispatch.mode is not DispatchMode.DIRECT_ANSWER:
        route_label = (
            f"{route.kind.value}.{route.capability.value}"
            if route.kind is not None and route.capability is not None
            else route.status.value
        )
        raise typer.BadParameter(
            f"Request routed to {route_label}. Use the plan workflow for change requests."
        )
    if route.capability is None:
        raise typer.BadParameter("Request capability is missing.")
    _run_direct_answer(request, route.capability, operator)


@app.command()
def topology(request: str, operator: str = "local-user"):
    _run_direct_answer(request, Capability.TOPOLOGY, operator)


@app.command()
def ipam(request: str, operator: str = "local-user"):
    _run_direct_answer(request, Capability.IPAM, operator)

async def _async_plan(request: str, operator: str = "local-user"):
    route = route_intent(request)
    dispatch = dispatch_request(route)

    if dispatch.mode is not DispatchMode.WORKFLOW_RUN:
        route_label = (
            f"{route.kind.value}.{route.capability.value}"
            if route.kind is not None and route.capability is not None
            else route.status.value
        )
        reason = route.rationale[0] if route.rationale else dispatch.reason
        raise typer.BadParameter(
            f"Request routed to {route_label} and cannot enter the change planning workflow. {reason}"
        )

    run_stage = dispatch.initial_stage or RunStage.PLAN

    try:
        domain_context = load_domain_context(route.domain)
    except DomainLoadError as exc:
        raise typer.Exit(code=2) from exc

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    runs_root = get_runs_root()
    run_store = RunStore(runs_root)
    reporter = RunProgressReporter(run_store, run_id)
    artifact_store = ArtifactStore(runs_root)

    deps = RunContextData(
        run_id=run_id,
        stage=run_stage,
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
        stage=run_stage,
        model_name=settings.ollama_model,
    )

    reporter.update(run_stage.value, "running", "🧠 Evaluating configuration intent...")
    reporter.update(
        run_stage.value,
        "running",
        "🧭 Routed request into staged workflow.",
        route_kind=route.kind.value if route.kind is not None else None,
        route_capability=route.capability.value if route.capability is not None else None,
        route_confidence=route.confidence,
        dispatch_mode=dispatch.mode.value,
    )
    planned = await run_agent_with_spinner(
        agent=change_planner,
        prompt=request,
        deps=deps,
        model_settings={"temperature": 0.0},
        message="Running Change Planner Agent..."
    )

    reporter.update(run_stage.value, "running", " 🔍 Resolving inventory scope...")

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

        run_store.update_stage(
            run_id,
            run_stage.value,
            "blocked",
            reason=f"No inventory match for scope: {scope_summary}",
        )
        raise typer.BadParameter(
            f"Could not resolve target devices. "
            f"Scope was: {scope_summary}. "
            f"Verify devices and site exist in inventory source '{settings.inventory_source}'."
        )
    
    reporter.update(run_stage.value, "running", " 🔍 Evaluating intent state...")
    if resolved_targets and (planned.plan_decision is None or planned.plan_decision.decision.value != "blocked"):
        normalized_desired_state = normalize_desired_state(
            route.domain,
            planned.requested_change.desired_state,
        )
        plan_decision = evaluate_intent_state(
            run_id=run_id,
            domain=route.domain.value, 
            site=planned.scope.site,
            device_names=[t.name for t in resolved_targets],
            desired_state=normalized_desired_state,
            inventory_source=settings.inventory_source,
        )
        planned.plan_decision = plan_decision
    reporter.update(run_stage.value, "running", "💾 Persisting change request artifact...")
    target_resources, resource_relationships = _build_authoritative_resource_refs(planned, resolved_targets)
    merged_resources = _merge_unique_resources(planned.target_resources, target_resources)
    merged_relationships = _merge_unique_relationships(
        planned.resource_relationships,
        resource_relationships,
    )

    # Build structured rollback from the forward diff when applicable
    if (
        planned.plan_decision is not None
        and planned.plan_decision.decision == PlanDecisionType.APPLY
    ):
        rollback = build_rollback_plan(planned.plan_decision)
    else:
        rollback = planned.rollback_plan

    # Validate and correct target_scope
    try:
        validated_scope = validate_target_scope(
            target_scope=planned.target_scope,
            scope_ref=planned.scope,
            resolved_targets=resolved_targets,
            target_resources=merged_resources,
        )
    except ScopeValidationError as exc:
        run_store.update_stage(
            run_id, run_stage.value, "blocked",
            reason=str(exc),
        )
        raise typer.BadParameter(str(exc)) from exc

    artifact = ChangeRequest(
        meta=ArtifactMeta(
            run_id=run_id,
            artifact_id=f"change-request-{run_id}",
            version=1,
            created_at=datetime.now(timezone.utc),
            created_by=operator,
        ),
        domain=route.domain,
        scope=planned.scope,
        target_scope=validated_scope,
        resolved_targets=resolved_targets,
        target_resources=merged_resources,
        resource_relationships=merged_relationships,
        clarifications_needed=planned.clarifications_needed,
        requested_change=planned.requested_change,
        risk=planned.risk,
        assumptions=planned.assumptions,
        dependencies=planned.dependencies,
        rollback_plan=rollback,
        plan_decision=planned.plan_decision,
    )

    artifact_path = artifact_store.save_model(run_id, "change_request", artifact)
    if planned.plan_decision and planned.plan_decision.decision.value == "no_op":
        reporter.update(run_stage.value, "completed", "✅ plan complete: no changes needed", artifact="change_request")
    elif planned.plan_decision and planned.plan_decision.decision.value == "apply":
        reporter.update(run_stage.value, "completed", f"✅ plan complete: ready for next steps. change request artifact at: {artifact_path}", artifact="change_request")
    else:
        reporter.update(run_stage.value, "blocked", f"❌ plan blocked. See artifact at: {artifact_path}", artifact="change_request")
    

# ── Internal helpers (no Typer annotation constraints) ───────────────────────

async def _async_render(change_request: ChangeRequest) -> None:
    """Core async render logic, callable from CLI or programmatically."""
    ensure_renderable(change_request)
    artifact_store = ArtifactStore(get_runs_root())
    run_store = RunStore(get_runs_root())
    run_stage = RunStage.RENDER
    reporter = RunProgressReporter(run_store, change_request.meta.run_id)
    reporter.update(run_stage.value, "running", "🔧 Rendering configuration...")

    plan_decision = change_request.plan_decision
    if plan_decision is None:
        raise ValueError("plan_decision is required for rendering")

    coordinator = StageCoordinator(artifact_store, run_store)
    render_result, artifact_path = await coordinator.render(change_request)

    reporter.update("render", "completed", f"✅ render complete: {artifact_path}", artifact='config_render')
    print({'run_id': change_request.meta.run_id, 'artifact_path': str(artifact_path), 'output': render_result.model_dump(mode='json')})


def _run_validate(
        config_render: ConfigRender,
        change_request: ChangeRequest | None = None,
    ) -> None:
    """Core validate logic, callable from CLI or programmatically."""
    artifact_store = ArtifactStore(get_runs_root())
    run_store = RunStore(get_runs_root())
    run_store.update_stage(config_render.meta.run_id, 'validate', 'running')
    validation_result = validate_config_render(config_render, change_request)
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
    try:
        asyncio.run(_async_render(change_request))
    except typer.BadParameter as e:
        typer.secho(f"Error executing render: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except ModelHTTPError as e:
        typer.secho(f"API Connection Error: Failed to communicate with the model provider ({e.status_code}).\nDetails: {e.body}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except Exception as e:
        traceback.print_exc()
        typer.secho(f"Error executing render: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


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
    try:
        asyncio.run(_async_render(change_request))
    except ModelHTTPError as e:
        typer.secho(f"API Connection Error: Failed to communicate with the model provider ({e.status_code}).\nDetails: {e.body}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except Exception as e:
        traceback.print_exc()
        typer.secho(f"Error executing stage pipeline: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    render_artifact = get_runs_root() / run_id / 'config_render.json'
    _run_validate(
        ConfigRender.model_validate_json(render_artifact.read_text()),
        change_request,
    )
    print(f"✅ Full pipeline complete: {run_id}")


@app.command()
def show_run(run_id: str):
    run_id = _validate_run_id(run_id)
    run_dir = get_runs_root() / run_id
    if not run_dir.exists():
        raise typer.BadParameter(f'Run directory not found: {run_dir}')
    files = sorted(str(p) for p in run_dir.glob('*.json'))
    print(json.dumps({'run_id': run_id, 'files': files}, indent=2))


if __name__ == '__main__':
    app()
