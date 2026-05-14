from pathlib import Path
import asyncio
from ..models.artifacts import ConfigRender, ValidationReport, ExecutionResult
from ..models.changes import ChangeRequest
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

        render_input = build_render_input(change_request)
        render_result_data = await change_render_agent.run(
            "Render the configuration.",
            deps=render_input,
        )
        render_result = render_result_data.output

        from .resolve_backend import resolve_render_backend, aggregate_and_label_snippets
        from ..models.enums import RenderRole, RenderBackendType
        
        platform = None
        if change_request.resolved_targets:
            platform = change_request.resolved_targets[0].platform
        primary_backend = resolve_render_backend(settings, platform)

        final_snippets = aggregate_and_label_snippets(render_result.snippets, primary_backend)
        
        render_result.snippets = final_snippets
        
        render_result.meta.run_id = change_request.meta.run_id
        ConfigRender.model_validate(render_result.model_dump())
        path = self.artifact_store.save_model(change_request.meta.run_id, 'config_render', render_result)

        if self.run_store:
            self.run_store.update_stage(change_request.meta.run_id, 'render', 'completed', artifact='config_render')
        return render_result, path

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
        return validation_result, path

    async def execute(
        self,
        change_request: ChangeRequest,
        validation_report: ValidationReport,
    ) -> tuple[ExecutionResult, Path]:
        run_id = change_request.meta.run_id
        if self.run_store:
            self.run_store.update_stage(run_id, 'approval_pending', 'running')

        if not validation_report.approved_for_execution:
            raise RuntimeError("Execution blocked: validation did not approve this change.")

        adapter = get_backend_adapter(settings)
        backend_render = await adapter.render(change_request)

        approved = request_approval(backend_render)
        if not approved:
            if self.run_store:
                self.run_store.update_stage(run_id, 'approval_pending', 'rejected')
            raise RuntimeError("Execution cancelled: operator did not approve.")

        if self.run_store:
            self.run_store.update_stage(run_id, 'execute', 'running')

        result = await adapter.apply(backend_render)
        path = self.artifact_store.save_model(run_id, 'execution_result', result)

        if self.run_store:
            self.run_store.update_stage(run_id, 'execute', 'completed', artifact='execution_result')

        return result, path

    async def run_pipeline(self, change_request: ChangeRequest) -> dict:
        render_result, render_path = await self.render(change_request)
        validation_result, validation_path = self.validate(render_result, change_request)
        summary = {
            'run_id': change_request.meta.run_id,
            'artifacts': {
                'change_request': str(self.artifact_store.artifact_path(change_request.meta.run_id, 'change_request')),
                'config_render': str(render_path),
                'validation_report': str(validation_path),
            },
            'status': validation_result.overall_status.value,
            'approved_for_execution': validation_result.approved_for_execution,
        }

        if validation_result.approved_for_execution:
            try:
                execution_result, execution_path = await self.execute(change_request, validation_result)
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
