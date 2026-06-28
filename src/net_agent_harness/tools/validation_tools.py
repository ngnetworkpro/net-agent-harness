import os
import re
import json
import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path

import yaml

from ..models.artifacts import (
    ConfigRender,
    ConfigSnippet,
    Finding,
    RenderAcceptanceResult,
    ValidationCheckResult,
    ValidationReport,
)
from ..models.changes import ChangeRequest
from ..models.common import ArtifactMeta
from ..models.enums import ValidationStatus, PlanDecisionType, RenderBackendType, RenderRole


REQUIRED_SAFETY_MARKERS = ["! Candidate config"]
TERRAFORM_MARKERS = (
    "terraform {",
    "resource ",
    "locals {",
    "module ",
    "data ",
    "variable ",
    "output ",
    "jsondecode(",
    "jsonencode(",
)
CLI_PRIMARY_PATTERNS = (
    r"^\s*interface\s+\S+",
    r"^\s*switchport\b",
    r"^\s*hostname\s+\S+",
    r"^\s*router\s+\S+",
    r"^\s*ip address\s+\S+",
    r"^\s*vlan\s+\d+\b",
)


def validate_config_render(
    config_render: ConfigRender,
    change_request: ChangeRequest | None = None,
) -> ValidationReport:
    findings: list[Finding] = []
    check_results: list[ValidationCheckResult] = []
    evidence = [f"config_render:{config_render.meta.artifact_id}"]
    if change_request is not None:
        evidence.append(f"change_request:{change_request.meta.artifact_id}")
    evidence.extend(
        f"rendered_device:{snippet.device_name}"
        for snippet in config_render.snippets
        if snippet.device_name
    )
    evidence = list(dict.fromkeys(evidence))

    check_results.append(
        ValidationCheckResult(
            check_name="evidence_presence_check",
            status=ValidationStatus.PASS if evidence else ValidationStatus.FAIL,
            details="Validation captured explicit evidence references."
            if evidence
            else "Validation requires at least one evidence reference.",
            blocking=not evidence,
        )
    )

    check_results.extend(_validate_snippets(config_render, findings))

    if change_request is not None:
        check_results.extend(_validate_against_change_request(config_render, change_request, findings))

    check_results.extend(_validate_backend_dry_run(config_render, findings))

    if config_render.warnings:
        findings.append(Finding(
            code="RENDER_WARNINGS_PRESENT",
            severity="low",
            message="Render completed with warnings.",
            recommendation="Review warnings and confirm assumptions are acceptable.",
        ))
        check_results.append(
            ValidationCheckResult(
                check_name="warnings_review_check",
                status=ValidationStatus.WARN,
                details="Render warnings are present and must be reviewed.",
                blocking=False,
            )
        )
    else:
        check_results.append(
            ValidationCheckResult(
                check_name="warnings_review_check",
                status=ValidationStatus.PASS,
                details="No render warnings were produced.",
                blocking=False,
            )
        )

    status = ValidationStatus.PASS
    approved_for_execution = True

    if not evidence or any(f.severity == "high" for f in findings):
        status = ValidationStatus.FAIL
        approved_for_execution = False
    elif findings:
        status = ValidationStatus.WARN
        approved_for_execution = False

    return ValidationReport(
        meta=ArtifactMeta(
            run_id=config_render.meta.run_id,
            artifact_id=f"validation-report-{config_render.meta.run_id}",
            parent_artifact_id=config_render.meta.artifact_id,
            created_by="validate_config_render",
        ),
        overall_status=status,
        checks_run=[check.check_name for check in check_results],
        check_results=check_results,
        findings=findings,
        evidence=evidence,
        approved_for_execution=approved_for_execution,
    )


def _validate_snippets(
    config_render: ConfigRender,
    findings: list[Finding],
) -> list[ValidationCheckResult]:
    checks: list[ValidationCheckResult] = []

    if not config_render.snippets:
        findings.append(Finding(
            code="EMPTY_RENDER",
            severity="high",
            message="No config snippets were produced.",
            recommendation="Review the source change request and rendering logic.",
        ))
        checks.append(
            ValidationCheckResult(
                check_name="artifact_consistency_check",
                status=ValidationStatus.FAIL,
                details="No snippets were produced.",
                blocking=True,
            )
        )
        return checks

    has_header_issue = False
    has_label_issue = False
    has_platform_issue = False
    any_labeled_snippet = any(
        snippet.backend_type is not None or snippet.render_role is not None
        for snippet in config_render.snippets
    )

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
            has_platform_issue = True
        elif (
            snippet.render_role == RenderRole.PRIMARY
            and (snippet.backend_type in {None, RenderBackendType.CLI})
            and not any(marker in text for marker in REQUIRED_SAFETY_MARKERS)
        ):
            findings.append(Finding(
                code="MISSING_CANDIDATE_HEADER",
                severity="medium",
                message=f"Snippet for {snippet.device_name} is missing the expected candidate header.",
                device_name=snippet.device_name,
                recommendation="Add a clear non-executed candidate marker to the rendered output.",
            ))
            has_header_issue = True

        if any_labeled_snippet and snippet.backend_type is None:
            findings.append(Finding(
                code="MISSING_BACKEND_TYPE",
                severity="high",
                message=f"Snippet for {snippet.device_name} is missing backend_type.",
                device_name=snippet.device_name,
                recommendation="Ensure each render snippet is labeled with backend_type.",
            ))
            has_label_issue = True

        if any_labeled_snippet and snippet.render_role is None:
            findings.append(Finding(
                code="MISSING_RENDER_ROLE",
                severity="high",
                message=f"Snippet for {snippet.device_name} is missing render_role.",
                device_name=snippet.device_name,
                recommendation="Ensure each render snippet is labeled as primary or fallback.",
            ))
            has_label_issue = True

    checks.append(
        ValidationCheckResult(
            check_name="artifact_consistency_check",
            status=ValidationStatus.PASS if not has_platform_issue else ValidationStatus.FAIL,
            details="Rendered snippets contain non-empty candidate content."
            if not has_platform_issue
            else "One or more snippets are empty.",
            blocking=has_platform_issue,
        )
    )
    checks.append(
        ValidationCheckResult(
            check_name="candidate_header_check",
            status=ValidationStatus.PASS if not has_header_issue else ValidationStatus.WARN,
            details="Primary CLI snippets include candidate header markers."
            if not has_header_issue
            else "One or more primary CLI snippets are missing candidate header markers.",
            blocking=False,
        )
    )
    checks.append(
        ValidationCheckResult(
            check_name="backend_role_label_check",
            status=ValidationStatus.PASS if not has_label_issue else ValidationStatus.FAIL,
            details=(
                "All snippets include backend_type and render_role labels."
                if not has_label_issue and any_labeled_snippet
                else "Snippets are unlabeled; backend-specific checks run only when labels are present."
                if not has_label_issue
                else "One or more snippets are missing backend_type or render_role labels."
            ),
            blocking=has_label_issue,
        )
    )

    return checks


def _validate_against_change_request(
    config_render: ConfigRender,
    change_request: ChangeRequest,
    findings: list[Finding],
) -> list[ValidationCheckResult]:
    checks: list[ValidationCheckResult] = []
    run_id = change_request.meta.run_id
    plan_decision = change_request.plan_decision

    has_consistency_issue = False
    has_platform_constraint_issue = False

    if config_render.meta.run_id != run_id:
        findings.append(Finding(
            code="RENDER_RUN_ID_MISMATCH",
            severity="high",
            message=f"ConfigRender run_id '{config_render.meta.run_id}' does not match ChangeRequest run_id '{run_id}'.",
            recommendation="Ensure the render artifact run_id matches the source ChangeRequest.",
        ))
        has_consistency_issue = True

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
                has_consistency_issue = True

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
            has_consistency_issue = True

        rendered_vlan_ids = _extract_rendered_vlan_ids(config_render.snippets)
        missing_vlan_ids = expected_vlan_ids - rendered_vlan_ids
        if missing_vlan_ids and expected_vlan_ids:
            findings.append(Finding(
                code="MISSING_VLAN_IN_RENDER",
                severity="high",
                message=f"VLAN IDs {missing_vlan_ids} from the plan are missing in rendered output.",
                recommendation="Ensure all planned VLANs are included in the rendered configuration.",
            ))
            has_platform_constraint_issue = True

        if not config_render.snippets:
            findings.append(Finding(
                code="EMPTY_RENDER_FOR_APPLY",
                severity="high",
                message="Plan decision is 'apply' but no snippets were produced.",
                recommendation="Ensure the render step produces configuration snippets for apply plans.",
            ))
            has_consistency_issue = True

    checks.append(
        ValidationCheckResult(
            check_name="artifact_consistency_check",
            status=ValidationStatus.PASS if not has_consistency_issue else ValidationStatus.FAIL,
            details="Render artifact is consistent with change request metadata and targets."
            if not has_consistency_issue
            else "Render artifact does not match run metadata or resolved targets.",
            blocking=has_consistency_issue,
        )
    )
    checks.append(
        ValidationCheckResult(
            check_name="platform_constraint_check",
            status=ValidationStatus.PASS if not has_platform_constraint_issue else ValidationStatus.FAIL,
            details="Rendered output satisfies expected platform and plan constraints."
            if not has_platform_constraint_issue
            else "Rendered output is missing plan-required platform data.",
            blocking=has_platform_constraint_issue,
        )
    )

    return checks


def _validate_backend_dry_run(
    config_render: ConfigRender,
    findings: list[Finding],
) -> list[ValidationCheckResult]:
    check_results: list[ValidationCheckResult] = []
    terraform_primaries = [
        snippet
        for snippet in config_render.snippets
        if snippet.backend_type == RenderBackendType.TERRAFORM
        and snippet.render_role == RenderRole.PRIMARY
    ]

    if not terraform_primaries:
        return check_results

    malformed_messages: list[str] = []
    for snippet in terraform_primaries:
        rendered = (snippet.rendered_text or "").strip()
        if not rendered:
            malformed_messages.append(
                f"Terraform primary snippet for {snippet.device_name} is missing rendered_text."
            )
            continue
        text_lower = rendered.lower()
        if not any(marker in text_lower for marker in TERRAFORM_MARKERS):
            malformed_messages.append(
                f"Terraform primary snippet for {snippet.device_name} is not Terraform-shaped."
            )
        if any(
            re.search(pattern, rendered, re.IGNORECASE | re.MULTILINE)
            for pattern in CLI_PRIMARY_PATTERNS
        ):
            malformed_messages.append(
                f"Terraform primary snippet for {snippet.device_name} appears CLI-shaped."
            )

    if malformed_messages:
        for message in malformed_messages:
            findings.append(Finding(
                code="MALFORMED_TERRAFORM_RENDER",
                severity="high",
                message=message,
                recommendation="Ensure Terraform snippets contain valid Terraform configuration.",
            ))
        return [
            ValidationCheckResult(
                check_name="terraform_validate_check",
                backend_type=RenderBackendType.TERRAFORM,
                status=ValidationStatus.FAIL,
                details="Terraform render artifact is malformed.",
                blocking=True,
            ),
            ValidationCheckResult(
                check_name="terraform_plan_check",
                backend_type=RenderBackendType.TERRAFORM,
                status=ValidationStatus.FAIL,
                details="Terraform render artifact is malformed.",
                blocking=True,
            ),
        ]

    terraform_bin = shutil.which("terraform")
    if terraform_bin is None:
        findings.append(Finding(
            code="TERRAFORM_BINARY_MISSING",
            severity="high",
            message="Terraform preflight checks require `terraform` to be installed.",
            recommendation="Install Terraform in the validation environment.",
        ))
        return [
            ValidationCheckResult(
                check_name="terraform_validate_check",
                backend_type=RenderBackendType.TERRAFORM,
                status=ValidationStatus.FAIL,
                details="Terraform executable was not found in PATH.",
                blocking=True,
            ),
            ValidationCheckResult(
                check_name="terraform_plan_check",
                backend_type=RenderBackendType.TERRAFORM,
                status=ValidationStatus.FAIL,
                details="Terraform executable was not found in PATH.",
                blocking=True,
            ),
        ]

    env = os.environ.copy()
    env["TF_IN_AUTOMATION"] = "1"
    with tempfile.TemporaryDirectory(prefix="tf-validate-") as temp_dir:
        workdir = Path(temp_dir)
        for index, snippet in enumerate(terraform_primaries):
            safe_device = re.sub(r"[^a-zA-Z0-9_-]+", "_", snippet.device_name)
            target_path = workdir / f"{index:03d}_{safe_device}.tf"
            target_path.write_text((snippet.rendered_text or "").strip() + "\n")

        init_result = subprocess.run(  # nosec B603
            [terraform_bin, "init", "-backend=false", "-input=false", "-no-color"],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if init_result.returncode != 0:
            details = _truncate_command_output(init_result)
            findings.append(Finding(
                code="TERRAFORM_INIT_FAILED",
                severity="high",
                message="Terraform init failed during preflight validation.",
                recommendation="Review Terraform source and provider configuration.",
            ))
            return [
                ValidationCheckResult(
                    check_name="terraform_validate_check",
                    backend_type=RenderBackendType.TERRAFORM,
                    status=ValidationStatus.FAIL,
                    details=details,
                    blocking=True,
                ),
                ValidationCheckResult(
                    check_name="terraform_plan_check",
                    backend_type=RenderBackendType.TERRAFORM,
                    status=ValidationStatus.FAIL,
                    details="Terraform init failed; plan preflight was not run.",
                    blocking=True,
                ),
            ]

        validate_result = subprocess.run(  # nosec B603
            [terraform_bin, "validate", "-no-color"],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        validate_ok = validate_result.returncode == 0
        if not validate_ok:
            findings.append(Finding(
                code="TERRAFORM_VALIDATE_FAILED",
                severity="high",
                message="Terraform validate failed for rendered artifact.",
                recommendation="Fix Terraform syntax/configuration errors before execution.",
            ))

        plan_status = ValidationStatus.FAIL
        plan_details = "Terraform plan was skipped because validate failed."
        if validate_ok:
            plan_result = subprocess.run(  # nosec B603
                [
                    terraform_bin,
                    "plan",
                    "-refresh=false",
                    "-lock=false",
                    "-input=false",
                    "-detailed-exitcode",
                    "-no-color",
                ],
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            plan_ok = plan_result.returncode in {0, 2}
            plan_status = ValidationStatus.PASS if plan_ok else ValidationStatus.FAIL
            plan_details = _truncate_command_output(plan_result)
            if not plan_ok:
                findings.append(Finding(
                    code="TERRAFORM_PLAN_FAILED",
                    severity="high",
                    message="Terraform plan failed for rendered artifact.",
                    recommendation="Review provider constraints and required inputs.",
                ))

        return [
            ValidationCheckResult(
                check_name="terraform_validate_check",
                backend_type=RenderBackendType.TERRAFORM,
                status=ValidationStatus.PASS if validate_ok else ValidationStatus.FAIL,
                details=_truncate_command_output(validate_result),
                blocking=not validate_ok,
            ),
            ValidationCheckResult(
                check_name="terraform_plan_check",
                backend_type=RenderBackendType.TERRAFORM,
                status=plan_status,
                details=plan_details,
                blocking=plan_status != ValidationStatus.PASS,
            ),
        ]


def _truncate_command_output(result: subprocess.CompletedProcess[str], max_chars: int = 1000) -> str:
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    if not output:
        return f"Command exited with status {result.returncode}."
    if len(output) <= max_chars:
        return output
    return output[: max_chars - 3] + "..."


def _extract_rendered_vlan_ids(snippets: list[ConfigSnippet]) -> set[int]:
    vlan_ids: set[int] = set()
    for snippet in snippets:
        if snippet.render_role != RenderRole.PRIMARY:
            continue
        text = snippet.rendered_text or "\n".join(snippet.commands)
        non_comment_lines = _strip_comment_lines(text)
        vlan_matches = re.findall(r'vlan\s+(\d+)', "\n".join(non_comment_lines), re.IGNORECASE)
        for match in vlan_matches:
            try:
                vlan_ids.add(int(match))
            except ValueError:
                pass
    return vlan_ids


def _strip_comment_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("!", "#"))
    ]

def validate_config_render_acceptance(
    change_request: ChangeRequest,
    config_render: ConfigRender,
) -> RenderAcceptanceResult:
    """Deterministic acceptance validation for render pipeline."""
    errors = []
    warnings = []
    
    # Rule 1: Render only allowed for apply
    plan_decision = change_request.plan_decision
    if plan_decision and plan_decision.decision != PlanDecisionType.APPLY:
        errors.append(f"Render rejected: plan decision is '{plan_decision.decision.value}', expected 'apply'.")

    # Rule 2: meta.run_id must match
    if config_render.meta.run_id != change_request.meta.run_id:
        errors.append(f"run_id mismatch: '{config_render.meta.run_id}' vs '{change_request.meta.run_id}'.")

    device_primaries: dict[str, int] = {}
    device_fallbacks: dict[str, int] = {}
    from ..config import settings
    selected_backend = settings.execution_backend
    
    for snippet in config_render.snippets:
        device = snippet.device_name
        
        # Rule 9: Valid JSON/YAML
        if snippet.rendered_text:
            text = snippet.rendered_text.strip()
            if text.startswith("{") or text.startswith("["):
                try:
                    json.loads(text)
                except json.JSONDecodeError:
                    errors.append(f"Snippet for {device} contains malformed JSON.")
            elif ":" in text and not any(marker in text for marker in REQUIRED_SAFETY_MARKERS):
                try:
                    yaml.safe_load(text)
                except yaml.YAMLError:
                    pass # Not failing strictly on YAML since CLI output might look like yaml
                    
        # Rule 4: Fallback snippets explicitly labeled
        if snippet.render_role == RenderRole.FALLBACK:
            device_fallbacks[device] = device_fallbacks.get(device, 0) + 1
            
        if snippet.render_role == RenderRole.PRIMARY:
            device_primaries[device] = device_primaries.get(device, 0) + 1
            
            # Rule 5: User-selected Terraform/Ansible must be primary
            if selected_backend in ("terraform", "ansible"):
                if snippet.backend_type and snippet.backend_type.value != selected_backend:
                    if snippet.backend_type == RenderBackendType.CLI:
                        pass # Allowed as last resort
                    else:
                        errors.append(f"User selected {selected_backend}, but primary snippet for {device} is {snippet.backend_type.value}.")
            
            # Rule 8: CLI must not be primary when API or selected backend available
            if snippet.backend_type == RenderBackendType.CLI:
                platform = None
                for rt in change_request.resolved_targets:
                    if rt.name == device:
                        platform = rt.platform
                        break
                from ..orchestration.resolve_backend import resolve_render_backend
                expected = resolve_render_backend(settings, platform)
                if expected != RenderBackendType.CLI:
                    errors.append(f"CLI is primary for {device}, but expected {expected.value}.")

            if snippet.backend_type == RenderBackendType.TERRAFORM:
                if not snippet.rendered_text:
                    errors.append(
                        f"Terraform primary snippet for {device} is missing rendered_text."
                    )
                    continue
                primary_text = snippet.rendered_text
                text_lower = primary_text.lower()
                if not any(marker in text_lower for marker in TERRAFORM_MARKERS):
                    errors.append(
                        f"Terraform primary snippet for {device} is not Terraform-shaped."
                    )
                if any(
                    re.search(pattern, primary_text, re.IGNORECASE | re.MULTILINE)
                    for pattern in CLI_PRIMARY_PATTERNS
                ):
                    errors.append(
                        f"Terraform primary snippet for {device} appears CLI-shaped."
                    )

        # Rule 7: API may be fallback when Terraform/Ansible is primary
        if snippet.backend_type == RenderBackendType.API and snippet.render_role == RenderRole.FALLBACK:
            warnings.append(f"API is provided as fallback for {device}.")
            
    # Rule 3: Exactly one primary snippet per device, at most one fallback
    for rt in change_request.resolved_targets:
        primary_count = device_primaries.get(rt.name, 0)
        fallback_count = device_fallbacks.get(rt.name, 0)
        
        if primary_count == 0 and plan_decision and plan_decision.decision == PlanDecisionType.APPLY:
             errors.append(f"No primary snippet found for device {rt.name}.")
        elif primary_count > 1:
             errors.append(f"Duplicate primary snippets found for device {rt.name}.")
             
        if fallback_count > 1:
             errors.append(f"Duplicate fallback snippets found for device {rt.name}.")

    # Rule 10: Warnings must not hide a condition that should have blocked render
    if config_render.warnings and not errors:
        for w in config_render.warnings:
            if "blocked" in w.lower():
                errors.append(f"Warning indicates a blocking condition: {w}")

    return RenderAcceptanceResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
