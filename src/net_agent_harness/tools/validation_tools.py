from typing import Any
from ..models.artifacts import ConfigRender, ConfigSnippet, Finding, ValidationReport
from ..models.changes import ChangeRequest
from ..models.common import ArtifactMeta
from ..models.enums import ValidationStatus, PlanDecisionType


REQUIRED_SAFETY_MARKERS = ["! Candidate config"]


def validate_config_render(
    config_render: ConfigRender,
    change_request: ChangeRequest | None = None,
) -> ValidationReport:
    findings: list[Finding] = []
    checks_run = [
        "candidate header present",
        "non-empty snippet list",
        "warnings reviewed",
        "schema validity",
    ]

    checks_run.extend(_validate_schema(config_render, findings))
    checks_run.extend(_validate_snippets(config_render, findings))

    if change_request is not None:
        checks_run.extend(_validate_against_change_request(config_render, change_request, findings))

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


def _validate_schema(config_render: ConfigRender, findings: list[Finding]) -> list[str]:
    checks = ["schema validity"]
    try:
        ConfigRender.model_validate(config_render.model_dump())
    except Exception as e:
        findings.append(Finding(
            code="SCHEMA_INVALID",
            severity="high",
            message=f"ConfigRender failed schema validation: {e}",
            recommendation="Ensure the render output conforms to ConfigRender schema.",
        ))
        checks.append("schema validity")
    return checks


def _validate_snippets(config_render: ConfigRender, findings: list[Finding]) -> list[str]:
    checks = ["non-empty snippet list", "candidate header present"]

    if not config_render.snippets:
        findings.append(Finding(
            code="EMPTY_RENDER",
            severity="high",
            message="No config snippets were produced.",
            recommendation="Review the source change request and rendering logic.",
        ))
        return checks

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
        elif not any(marker in text for marker in REQUIRED_SAFETY_MARKERS):
            findings.append(Finding(
                code="MISSING_CANDIDATE_HEADER",
                severity="medium",
                message=f"Snippet for {snippet.device_name} is missing the expected candidate header.",
                device_name=snippet.device_name,
                recommendation="Add a clear non-executed candidate marker to the rendered output.",
            ))

    return checks


def _validate_against_change_request(
    config_render: ConfigRender,
    change_request: ChangeRequest,
    findings: list[Finding],
) -> list[str]:
    checks: list[str] = []
    run_id = change_request.meta.run_id
    plan_decision = change_request.plan_decision

    if config_render.meta.run_id != run_id:
        findings.append(Finding(
            code="RENDER_RUN_ID_MISMATCH",
            severity="high",
            message=f"ConfigRender run_id '{config_render.meta.run_id}' does not match ChangeRequest run_id '{run_id}'.",
            recommendation="Ensure the render artifact run_id matches the source ChangeRequest.",
        ))

    if change_request.resolved_targets:
        resolved_device_names = {t.name for t in change_request.resolved_targets}
        for snippet in config_render.snippets:
            if snippet.device_name not in resolved_device_names:
                findings.append(Finding(
                    code="SNIPPET_TARGET_NOT_RESOLVED",
                    severity="high",
                    message=f"Snippet device '{snippet.device_name}' is not in resolved_targets.",
                    device_name=snippet.device_name,
                    recommendation="Only render configuration for devices in the resolved target set.",
                ))

    if plan_decision and plan_decision.decision == PlanDecisionType.APPLY:
        expected_vlan_ids = set()
        expected_vlan_names = set()
        expected_devices = set()

        if plan_decision.diff:
            for device_change in plan_decision.diff:
                expected_devices.add(device_change.device)
                if hasattr(device_change.changes, 'vlans_to_create'):
                    for vlan in device_change.changes.vlans_to_create:
                        expected_vlan_ids.add(vlan.id)
                        if vlan.name:
                            expected_vlan_names.add(vlan.name)

        rendered_devices = {s.device_name for s in config_render.snippets}
        extra_devices = rendered_devices - expected_devices
        if extra_devices:
            findings.append(Finding(
                code="INVENTED_DEVICE_SCOPE",
                severity="high",
                message=f"Rendered devices {extra_devices} are not in the approved plan diff.",
                recommendation="Do not render configuration for devices outside the approved plan.",
            ))

        rendered_vlan_ids = _extract_rendered_vlan_ids(config_render.snippets)
        missing_vlan_ids = expected_vlan_ids - rendered_vlan_ids
        if missing_vlan_ids and expected_vlan_ids:
            findings.append(Finding(
                code="MISSING_VLAN_IN_RENDER",
                severity="high",
                message=f"VLAN IDs {missing_vlan_ids} from the plan are missing in rendered output.",
                recommendation="Ensure all planned VLANs are included in the rendered configuration.",
            ))

        if not config_render.snippets:
            findings.append(Finding(
                code="EMPTY_RENDER_FOR_APPLY",
                severity="high",
                message="Plan decision is 'apply' but no snippets were produced.",
                recommendation="Ensure the render step produces configuration snippets for apply plans.",
            ))

    if config_render.warnings:
        findings.append(Finding(
            code="RENDER_WARNINGS_PRESENT",
            severity="low",
            message="Render completed with warnings.",
            recommendation="Review warnings and confirm assumptions are acceptable.",
        ))

    return checks


def _extract_rendered_vlan_ids(snippets: list[ConfigSnippet]) -> set[int]:
    vlan_ids: set[int] = set()
    for snippet in snippets:
        text = snippet.rendered_text or "\n".join(snippet.commands)
        import re
        vlan_matches = re.findall(r'vlan\s+(\d+)', text, re.IGNORECASE)
        for match in vlan_matches:
            try:
                vlan_ids.add(int(match))
            except ValueError:
                pass
    return vlan_ids