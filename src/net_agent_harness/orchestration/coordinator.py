from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Literal
from ..models.artifacts import ConfigRender, ExecutionPlan, ValidationReport, ExecutionResult, ConfigRenderOutput
from ..models.changes import ChangeRequest
from ..models.enums import PlanDecisionType, RenderBackendType
from ..models.common import ArtifactMeta
from ..services.artifact_store import ArtifactStore
from ..services.run_store import RunStore
from ..tools.validation_tools import validate_config_render
from ..policies.approvals import get_backend_adapter, request_approval
from ..config import settings
from ..agents.config_render_agent import change_render_agent
from ..orchestration.build_render import build_render_input


class StageCoordinator:
    def __init__(self, artifact_store: ArtifactStore, run_store: RunStore | None = None):
        self.artifact_store = artifact_store
        self.run_store = run_store

    async def render(self, change_request: ChangeRequest) -> tuple[ConfigRender, Path]:
        if self.run_store:
            self.run_store.update_stage(change_request.meta.run_id, 'render', 'running')
        if (
            change_request.plan_decision is None
            or change_request.plan_decision.decision != PlanDecisionType.APPLY
        ):
            decision = change_request.plan_decision.decision.value if change_request.plan_decision else "none"
            raise ValueError(f"Render rejected: plan decision is '{decision}', expected 'apply'.")

        from .resolve_backend import resolve_render_backend

        if change_request.plan_decision and change_request.plan_decision.diff:
            from .platform_constraints import validate_platform_constraints
            platform_by_device = {t.name: t.platform for t in change_request.resolved_targets}
            errors: list[str] = []
            for device_change in change_request.plan_decision.diff:
                device_platform = platform_by_device.get(device_change.device)
                errors.extend(validate_platform_constraints(device_platform, [device_change]))
            if errors:
                raise ValueError(f"Cannot render config: platform constraints failed: {'; '.join(errors)}")

        platform = change_request.resolved_targets[0].platform if change_request.resolved_targets else None
        primary_backend = resolve_render_backend(settings, platform)

        # Source-backed backends have their own deterministic render — skip the LLM
        if primary_backend == RenderBackendType.TERRAFORM:
            from ..adapters.backends.terraform import TerraformBackendAdapter
            adapter = TerraformBackendAdapter()
            config_render = await adapter.render(change_request)
        else:
            # API / CLI — use the LLM render agent + post-processing
            render_input = build_render_input(change_request)
            render_result_data = await change_render_agent.run(
                "Render the configuration.",
                deps=render_input,
            )
            render_result: ConfigRenderOutput = render_result_data.output

            from .resolve_backend import aggregate_and_label_snippets
            final_snippets = aggregate_and_label_snippets(render_result.snippets, primary_backend)
            render_result.snippets = final_snippets

            config_render = ConfigRender(
                meta=change_request.meta,
                **render_result.model_dump()
            )

        config_render.meta = ArtifactMeta(
            run_id=change_request.meta.run_id,
            artifact_id=f"config-render-{change_request.meta.run_id}",
            parent_artifact_id=change_request.meta.artifact_id,
            created_at=datetime.now(timezone.utc),
            created_by="stage_coordinator",
        )
        if config_render.meta.artifact_id not in change_request.meta.child_artifact_ids:
            change_request.meta.child_artifact_ids.append(config_render.meta.artifact_id)
            self.artifact_store.save_model(change_request.meta.run_id, "change_request", change_request)

        path = self.artifact_store.save_model(change_request.meta.run_id, 'config_render', config_render)

        if self.run_store:
            self.run_store.update_stage(change_request.meta.run_id, 'render', 'completed', artifact='config_render')
        return config_render, path

    def validate(
        self,
        config_render: ConfigRender,
        change_request: ChangeRequest | None = None,
    ) -> tuple[ValidationReport, Path]:
        if self.run_store:
            self.run_store.update_stage(config_render.meta.run_id, 'validate', 'running')
        validation_result = validate_config_render(config_render, change_request)
        path = self.artifact_store.save_model(config_render.meta.run_id, 'validation_report', validation_result)
        final_status = 'completed' if validation_result.overall_status.value == 'pass' else validation_result.overall_status.value
        if self.run_store:
            self.run_store.update_stage(
                config_render.meta.run_id,
                'validate',
                final_status,
                artifact='validation_report',
                approved_for_execution=validation_result.approved_for_execution,
            )
        if validation_result.meta.artifact_id not in config_render.meta.child_artifact_ids:
            config_render.meta.child_artifact_ids.append(validation_result.meta.artifact_id)
            self.artifact_store.save_model(config_render.meta.run_id, "config_render", config_render)
        return validation_result, path

    async def execute(
        self,
        config_render: ConfigRender,
        change_request: ChangeRequest,
        validation_report: ValidationReport,
    ) -> tuple[ExecutionResult, Path]:
        run_id = change_request.meta.run_id
        if self.run_store:
            self.run_store.update_stage(run_id, 'approval_pending', 'running')

        if not validation_report.approved_for_execution:
            raise RuntimeError("Execution blocked: validation did not approve this change.")

        approved = request_approval(config_render)
        if not approved:
            if self.run_store:
                self.run_store.update_stage(run_id, 'approval_pending', 'rejected')
            raise RuntimeError("Execution cancelled: operator did not approve.")

        if self.run_store:
            self.run_store.update_stage(run_id, 'execute', 'running')

        adapter = get_backend_adapter(settings)
        result = await adapter.apply(config_render)
        path = self.artifact_store.save_model(run_id, 'execution_result', result)

        if self.run_store:
            self.run_store.update_stage(run_id, 'execute', 'completed', artifact='execution_result')

        return result, path

    def create_execution_plan(
        self,
        change_request: ChangeRequest,
        validation_report: ValidationReport,
    ) -> tuple[ExecutionPlan, Path]:
        status: Literal["ready", "blocked"] = "ready" if validation_report.approved_for_execution else "blocked"
        detail = (
            "Validation approved execution."
            if validation_report.approved_for_execution
            else "Execution blocked: validation did not approve this change."
        )
        execution_plan = ExecutionPlan(
            meta=ArtifactMeta(
                run_id=change_request.meta.run_id,
                artifact_id=f"execution-plan-{change_request.meta.run_id}",
                parent_artifact_id=validation_report.meta.artifact_id,
                created_by="stage_coordinator",
            ),
            backend=str(settings.execution_backend),
            status=status,
            detail=detail,
            approved_for_execution=validation_report.approved_for_execution,
        )
        path = self.artifact_store.save_model(change_request.meta.run_id, "execution_plan", execution_plan)
        if self.run_store:
            approval_status = "ready" if execution_plan.approved_for_execution else "blocked"
            self.run_store.update_stage(
                change_request.meta.run_id,
                "approval_pending",
                approval_status,
                artifact="execution_plan",
                artifact_id=execution_plan.meta.artifact_id,
                approved_for_execution=execution_plan.approved_for_execution,
            )
        if execution_plan.meta.artifact_id not in validation_report.meta.child_artifact_ids:
            validation_report.meta.child_artifact_ids.append(execution_plan.meta.artifact_id)
            self.artifact_store.save_model(change_request.meta.run_id, "validation_report", validation_report)
        return execution_plan, path

    async def run_pipeline(self, change_request: ChangeRequest) -> dict:
        render_result, render_path = await self.render(change_request)
        validation_result, validation_path = self.validate(render_result, change_request)
        execution_plan, execution_plan_path = self.create_execution_plan(change_request, validation_result)
        summary: dict[str, Any] = {
            'run_id': change_request.meta.run_id,
            'artifacts': {
                'change_request': str(self.artifact_store.artifact_path(change_request.meta.run_id, 'change_request')),
                'config_render': str(render_path),
                'validation_report': str(validation_path),
                'execution_plan': str(execution_plan_path),
            },
            'status': validation_result.overall_status.value,
            'approved_for_execution': validation_result.approved_for_execution,
        }

        if execution_plan.approved_for_execution:
            try:
                execution_result, execution_path = await self.execute(
                    render_result, change_request, validation_result
                )
                execution_result.meta.parent_artifact_id = execution_plan.meta.artifact_id
                self.artifact_store.save_model(change_request.meta.run_id, "execution_result", execution_result)
                if execution_result.meta.artifact_id not in execution_plan.meta.child_artifact_ids:
                    execution_plan.meta.child_artifact_ids.append(execution_result.meta.artifact_id)
                    self.artifact_store.save_model(change_request.meta.run_id, "execution_plan", execution_plan)
                summary['artifacts']['execution_result'] = str(execution_path)
                summary['execution_status'] = execution_result.status
                summary['execution_reference'] = execution_result.reference
            except RuntimeError as e:
                summary['execution_status'] = 'cancelled'
                summary['execution_detail'] = str(e)

        summary_path = self.artifact_store.save_json(change_request.meta.run_id, 'run_summary', summary)
        summary['artifacts']['run_summary'] = str(summary_path)
        if self.run_store:
            self.run_store.update_stage(
                change_request.meta.run_id,
                'pipeline',
                summary.get('execution_status', summary['status']),
                artifact='run_summary',
                approved_for_execution=summary['approved_for_execution'],
            )
        return summary
