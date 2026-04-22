from ..models.artifacts import ConfigRender, Finding, ValidationReport
from ..models.common import ArtifactMeta
from ..models.enums import ValidationStatus


REQUIRED_SAFETY_MARKERS = ["! Candidate config"]


def validate_config_render(config_render: ConfigRender) -> ValidationReport:
    findings: list[Finding] = []
    checks_run = [
        "candidate header present",
        "non-empty snippet list",
        "warnings reviewed",
    ]

    if not config_render.snippets:
        findings.append(Finding(
            code="EMPTY_RENDER",
            severity="high",
            message="No config snippets were produced.",
            recommendation="Review the source change request and rendering logic.",
        ))

    for snippet in config_render.snippets:
        text = snippet.rendered_text or "\n".join(snippet.commands)
        if not text.strip():
            findings.append(Finding(
                code="EMPTY_SNIPPET",
                severity="high",
                message=f"Snippet for {snippet.device_name} has no rendered content.",
                device_name=snippet.device_name,
                recommendation="Ensure the render step creates candidate commands.",
            ))

        if not any(marker in text for marker in REQUIRED_SAFETY_MARKERS):
            findings.append(Finding(
                code="MISSING_CANDIDATE_HEADER",
                severity="medium",
                message=f"Snippet for {snippet.device_name} is missing the expected candidate header.",
                device_name=snippet.device_name,
                recommendation="Add a clear non-executed candidate marker to the rendered output.",
            ))

    if config_render.warnings:
        findings.append(Finding(
            code="RENDER_WARNINGS_PRESENT",
            severity="low",
            message="Render completed with warnings that should be reviewed before approval.",
            recommendation="Review warnings and confirm assumptions are acceptable.",
        ))

    status = ValidationStatus.PASS
    approved_for_execution = True

    if any(f.severity == "high" for f in findings):
        status = ValidationStatus.FAIL
        approved_for_execution = False
    elif findings:
        status = ValidationStatus.WARN
        approved_for_execution = False

    return ValidationReport(
        meta=ArtifactMeta(
            run_id=config_render.meta.run_id,
            artifact_id="validation-report-001",
            created_by="validate_config_render",
        ),
        overall_status=status,
        checks_run=checks_run,
        findings=findings,
        approved_for_execution=approved_for_execution,
    )
