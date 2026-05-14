import pytest
from net_agent_harness.config import Settings
from net_agent_harness.models.enums import RenderBackendType
from net_agent_harness.orchestration.resolve_backend import resolve_render_backend

def test_terraform_selected():
    settings = Settings(execution_backend="terraform")
    assert resolve_render_backend(settings) == RenderBackendType.TERRAFORM
    assert resolve_render_backend(settings, platform="mist") == RenderBackendType.TERRAFORM

def test_ansible_selected():
    settings = Settings(execution_backend="ansible")
    assert resolve_render_backend(settings) == RenderBackendType.ANSIBLE
    assert resolve_render_backend(settings, platform="mist") == RenderBackendType.ANSIBLE

def test_api_for_mist():
    settings = Settings(execution_backend="direct_api")
    assert resolve_render_backend(settings, platform="mist") == RenderBackendType.API
    assert resolve_render_backend(settings, platform="MIST") == RenderBackendType.API

def test_api_for_meraki():
    settings = Settings(execution_backend="direct_api")
    assert resolve_render_backend(settings, platform="meraki") == RenderBackendType.API

def test_cli_fallback():
    settings = Settings(execution_backend="direct_api")
    assert resolve_render_backend(settings) == RenderBackendType.CLI
    assert resolve_render_backend(settings, platform="cisco_ios") == RenderBackendType.CLI
