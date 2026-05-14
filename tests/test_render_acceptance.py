import pytest
from net_agent_harness.models.artifacts import ConfigRender, ConfigSnippet
from net_agent_harness.models.changes import ChangeRequest, PlanDecision, ResolvedTarget, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import PlanDecisionType, TargetScope, NetworkDomain, ChangeRisk, RenderBackendType, RenderRole
from net_agent_harness.tools.validation_tools import validate_config_render_acceptance
from net_agent_harness.config import settings

@pytest.fixture
def base_change_request():
    return ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="cr-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(device_names=["sw1"]),
        target_scope=TargetScope.device,
        resolved_targets=[ResolvedTarget(name="sw1", platform="mist")],
        requested_change=RequestedChange(summary="test", intent="test"),
        risk=ChangeRisk.LOW,
        rollback_plan=RollbackPlan(summary="none"),
        plan_decision=PlanDecision(decision=PlanDecisionType.APPLY, reason="test", diff=[])
    )

@pytest.fixture
def base_config_render():
    return ConfigRender(
        meta=ArtifactMeta(run_id="run-1", artifact_id="render-1", created_by="test"),
        summary="Test render",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                rendered_text="{ \"key\": \"value\" }"
            )
        ]
    )

def test_reject_blocked_plan(base_change_request, base_config_render):
    base_change_request.plan_decision.decision = PlanDecisionType.BLOCKED
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert not result.passed
    assert any("expected 'apply'" in e for e in result.errors)

def test_reject_no_op_plan(base_change_request, base_config_render):
    base_change_request.plan_decision.decision = PlanDecisionType.NO_OP
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert not result.passed
    assert any("expected 'apply'" in e for e in result.errors)

def test_one_primary_per_device(base_change_request, base_config_render):
    # Adjust setting so API matches Mist platform explicitly
    settings.execution_backend = "direct_api"
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert result.passed

def test_reject_duplicate_primary(base_change_request, base_config_render):
    settings.execution_backend = "direct_api"
    # Add a second primary snippet for the same device
    base_config_render.snippets.append(
        ConfigSnippet(
            device_name="sw1",
            backend_type=RenderBackendType.TERRAFORM,
            render_role=RenderRole.PRIMARY,
            rendered_text="{}"
        )
    )
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert not result.passed
    assert any("Duplicate primary snippets" in e for e in result.errors)

def test_reject_duplicate_fallback(base_change_request, base_config_render):
    settings.execution_backend = "direct_api"
    # Make the first snippet primary, then add two fallbacks
    base_config_render.snippets.append(
        ConfigSnippet(
            device_name="sw1",
            backend_type=RenderBackendType.CLI,
            render_role=RenderRole.FALLBACK,
            rendered_text="!"
        )
    )
    base_config_render.snippets.append(
        ConfigSnippet(
            device_name="sw1",
            backend_type=RenderBackendType.CLI,
            render_role=RenderRole.FALLBACK,
            rendered_text="!"
        )
    )
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert not result.passed
    assert any("Duplicate fallback snippets" in e for e in result.errors)

def test_terraform_primary_when_selected(base_change_request, base_config_render):
    settings.execution_backend = "terraform"
    base_config_render.snippets[0].backend_type = RenderBackendType.TERRAFORM
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert result.passed

def test_ansible_primary_when_selected(base_change_request, base_config_render):
    settings.execution_backend = "ansible"
    base_config_render.snippets[0].backend_type = RenderBackendType.ANSIBLE
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert result.passed

def test_api_primary_no_preference(base_change_request, base_config_render):
    settings.execution_backend = "direct_api"
    base_config_render.snippets[0].backend_type = RenderBackendType.API
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert result.passed

def test_api_fallback_with_terraform_primary(base_change_request, base_config_render):
    settings.execution_backend = "terraform"
    base_config_render.snippets[0].backend_type = RenderBackendType.TERRAFORM
    # Add API as fallback
    base_config_render.snippets.append(
        ConfigSnippet(
            device_name="sw1",
            backend_type=RenderBackendType.API,
            render_role=RenderRole.FALLBACK,
            rendered_text="{}"
        )
    )
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert result.passed
    assert any("API is provided as fallback" in w for w in result.warnings)

def test_reject_malformed_json_payload(base_change_request, base_config_render):
    settings.execution_backend = "direct_api"
    base_config_render.snippets[0].rendered_text = "{ malformed json"
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert not result.passed
    assert any("malformed JSON" in e for e in result.errors)

def test_reject_run_id_mismatch(base_change_request, base_config_render):
    base_config_render.meta.run_id = "run-2"
    result = validate_config_render_acceptance(base_change_request, base_config_render)
    assert not result.passed
    assert any("run_id mismatch" in e for e in result.errors)
