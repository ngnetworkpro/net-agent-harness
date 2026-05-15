import subprocess

import pytest

from net_agent_harness.models.artifacts import ConfigRender, ConfigSnippet
from net_agent_harness.models.common import ArtifactMeta
from net_agent_harness.models.enums import RenderBackendType, RenderRole, ValidationStatus
from net_agent_harness.tools import validation_tools
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


def test_validate_config_render_runs_terraform_preflight_checks(monkeypatch: pytest.MonkeyPatch):
    render = ConfigRender(
        meta=ArtifactMeta(run_id="run-terraform-ok", artifact_id="render-1", created_by="test"),
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
    commands: list[list[str]] = []
    monkeypatch.setattr(validation_tools.shutil, "which", lambda _: "/usr/bin/terraform")

    def _fake_run(
        command: list[str],
        *,
        cwd,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
    ):
        del cwd, capture_output, text, check, env
        commands.append(command)
        returncode = 2 if command[1] == "plan" else 0
        return subprocess.CompletedProcess(command, returncode, stdout="ok", stderr="")

    monkeypatch.setattr(validation_tools.subprocess, "run", _fake_run)

    report = validate_config_render(render)

    check_status = {check.check_name: check.status for check in report.check_results}
    assert check_status["terraform_validate_check"] == ValidationStatus.PASS
    assert check_status["terraform_plan_check"] == ValidationStatus.PASS
    assert report.overall_status == ValidationStatus.PASS
    assert report.approved_for_execution is True
    assert any(
        command[1:] == ["init", "-backend=false", "-input=false", "-no-color"]
        for command in commands
    )
    assert any(
        len(command) > 1
        and command[1] == "plan"
        and "-refresh=false" in command
        and "-lock=false" in command
        for command in commands
    )


def test_validate_config_render_fails_when_terraform_binary_missing(monkeypatch: pytest.MonkeyPatch):
    render = ConfigRender(
        meta=ArtifactMeta(run_id="run-terraform-no-bin", artifact_id="render-1", created_by="test"),
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
    monkeypatch.setattr(validation_tools.shutil, "which", lambda _: None)

    report = validate_config_render(render)

    assert report.overall_status == ValidationStatus.FAIL
    assert report.approved_for_execution is False
    assert any(f.code == "TERRAFORM_BINARY_MISSING" for f in report.findings)
    check_status = {check.check_name: check.status for check in report.check_results}
    assert check_status["terraform_validate_check"] == ValidationStatus.FAIL
    assert check_status["terraform_plan_check"] == ValidationStatus.FAIL


def test_validate_config_render_fails_on_malformed_terraform_render(monkeypatch: pytest.MonkeyPatch):
    render = ConfigRender(
        meta=ArtifactMeta(run_id="run-terraform-bad-shape", artifact_id="render-1", created_by="test"),
        summary="Terraform render",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.TERRAFORM,
                render_role=RenderRole.PRIMARY,
                rendered_text="! Candidate config for sw1\nvlan 220",
            )
        ],
        warnings=[],
    )
    monkeypatch.setattr(validation_tools.shutil, "which", lambda _: "/usr/bin/terraform")
    called = {"run": False}

    def _unexpected_run(*args, **kwargs):
        del args, kwargs
        called["run"] = True
        raise AssertionError("subprocess.run should not be called for malformed terraform snippets")

    monkeypatch.setattr(validation_tools.subprocess, "run", _unexpected_run)

    report = validate_config_render(render)

    assert report.overall_status == ValidationStatus.FAIL
    assert report.approved_for_execution is False
    assert any(f.code == "MALFORMED_TERRAFORM_RENDER" for f in report.findings)
    assert called["run"] is False


def test_validate_config_render_fails_when_terraform_validate_fails(monkeypatch: pytest.MonkeyPatch):
    render = ConfigRender(
        meta=ArtifactMeta(run_id="run-terraform-validate-fail", artifact_id="render-1", created_by="test"),
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
    monkeypatch.setattr(validation_tools.shutil, "which", lambda _: "/usr/bin/terraform")

    def _fake_run(command: list[str], **kwargs):
        del kwargs
        if command[1] == "validate":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="invalid reference")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(validation_tools.subprocess, "run", _fake_run)

    report = validate_config_render(render)

    assert report.overall_status == ValidationStatus.FAIL
    assert report.approved_for_execution is False
    assert any(f.code == "TERRAFORM_VALIDATE_FAILED" for f in report.findings)
    check_status = {check.check_name: check.status for check in report.check_results}
    assert check_status["terraform_validate_check"] == ValidationStatus.FAIL
    assert check_status["terraform_plan_check"] == ValidationStatus.FAIL
