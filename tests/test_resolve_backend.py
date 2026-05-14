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

from net_agent_harness.orchestration.resolve_backend import aggregate_and_label_snippets
from net_agent_harness.models.artifacts import ConfigSnippet
from net_agent_harness.models.enums import RenderRole

def test_aggregate_and_label_snippets_collapses_duplicates():
    raw_snippets = [
        ConfigSnippet(device_name="sw1", commands=["cmd1"], rendered_text="text1"),
        ConfigSnippet(device_name="sw1", commands=["cmd2"], rendered_text="text2"),
        ConfigSnippet(device_name="sw2", commands=["cmd3"], rendered_text="text3"),
    ]
    
    result = aggregate_and_label_snippets(raw_snippets, RenderBackendType.TERRAFORM)
    
    # We expect 2 primary snippets (sw1, sw2) and 2 fallback snippets (sw1, sw2)
    assert len(result) == 4
    
    sw1_primaries = [s for s in result if s.device_name == "sw1" and s.render_role == RenderRole.PRIMARY]
    assert len(sw1_primaries) == 1
    assert sw1_primaries[0].backend_type == RenderBackendType.TERRAFORM
    assert sw1_primaries[0].commands == ["cmd1", "cmd2"]
    assert sw1_primaries[0].rendered_text == "text1\n\ntext2"
    
    sw1_fallbacks = [s for s in result if s.device_name == "sw1" and s.render_role == RenderRole.FALLBACK]
    assert len(sw1_fallbacks) == 1
    assert sw1_fallbacks[0].backend_type == RenderBackendType.CLI
    
    sw2_primaries = [s for s in result if s.device_name == "sw2" and s.render_role == RenderRole.PRIMARY]
    assert len(sw2_primaries) == 1
    assert sw2_primaries[0].commands == ["cmd3"]

def test_aggregate_no_fallback_for_cli():
    raw_snippets = [
        ConfigSnippet(device_name="sw1", commands=["cmd1"]),
    ]
    
    result = aggregate_and_label_snippets(raw_snippets, RenderBackendType.CLI)
    
    # We expect 1 primary snippet and NO fallback snippets since CLI is already primary
    assert len(result) == 1
    assert result[0].render_role == RenderRole.PRIMARY
    assert result[0].backend_type == RenderBackendType.CLI
