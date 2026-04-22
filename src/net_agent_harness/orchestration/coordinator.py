from pathlib import Path
from ..models.artifacts import ConfigRender, ValidationReport
from ..models.changes import ChangeRequest
from ..services.artifact_store import ArtifactStore
from ..services.run_store import RunStore
from ..tools.config_tools import build_stub_config_render
from ..tools.validation_tools import validate_config_render


class StageCoordinator:
    def __init__(self, artifact_store: ArtifactStore, run_store: RunStore | None = None):
        self.artifact_store = artifact_store
        self.run_store = run_store

    def render(self, change_request: ChangeRequest) -> tuple[ConfigRender, Path]:
        if self.run_store:
            self.run_store.update_stage(change_request.meta.run_id, 'render', 'running')
        render_result = build_stub_config_render(change_request)
        path = self.artifact_store.save_model(change_request.meta.run_id, 'config_render', render_result)
        if self.run_store:
            self.run_store.update_stage(change_request.meta.run_id, 'render', 'completed', artifact='config_render')
        return render_result, path

    def validate(self, config_render: ConfigRender) -> tuple[ValidationReport, Path]:
        if self.run_store:
            self.run_store.update_stage(config_render.meta.run_id, 'validate', 'running')
        validation_result = validate_config_render(config_render)
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

    def run_pipeline(self, change_request: ChangeRequest) -> dict:
        render_result, render_path = self.render(change_request)
        validation_result, validation_path = self.validate(render_result)
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
        summary_path = self.artifact_store.save_json(change_request.meta.run_id, 'run_summary', summary)
        summary['artifacts']['run_summary'] = str(summary_path)
        if self.run_store:
            self.run_store.update_stage(
                change_request.meta.run_id,
                'pipeline',
                summary['status'],
                artifact='run_summary',
                approved_for_execution=summary['approved_for_execution'],
            )
        return summary
