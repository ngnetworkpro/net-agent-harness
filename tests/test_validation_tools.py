from net_agent_harness.models.artifacts import ConfigRender, ConfigSnippet
from net_agent_harness.models.common import ArtifactMeta
from net_agent_harness.models.enums import RenderBackendType, RenderRole, ValidationStatus
from net_agent_harness.tools.validation_tools import validate_config_render


def test_validate_config_render_passes_candidate_output():
    render = ConfigRender(
        meta=ArtifactMeta(run_id="run-1", artifact_id="render-1", created_by="test"),
        summary="Candidate config",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                commands=["! Candidate config for sw1", "vlan 220"],
                rendered_text="! Candidate config for sw1\nvlan 220",
            )
        ],
        warnings=[],
    )

    report = validate_config_render(render)
    assert report.overall_status == ValidationStatus.PASS
    assert report.approved_for_execution is True


def test_validate_config_render_warns_on_warnings():
    render = ConfigRender(
        meta=ArtifactMeta(run_id="run-1", artifact_id="render-1", created_by="test"),
        summary="Candidate config",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                commands=["! Candidate config for sw1", "vlan 220"],
                rendered_text="! Candidate config for sw1\nvlan 220",
            )
        ],
        warnings=["Assumed VLAN name"],
    )

    report = validate_config_render(render)
    assert report.overall_status == ValidationStatus.WARN
    assert report.approved_for_execution is False


def test_validate_config_render_does_not_require_cli_marker_for_terraform_primary():
    render = ConfigRender(
        meta=ArtifactMeta(run_id="run-1", artifact_id="render-1", created_by="test"),
        summary="Terraform render",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.TERRAFORM,
                render_role=RenderRole.PRIMARY,
                rendered_text='resource "mist_org_networktemplate" "offices" {}',
            )
        ],
        warnings=[],
    )

    report = validate_config_render(render)
    assert not any(f.code == "MISSING_CANDIDATE_HEADER" for f in report.findings)
