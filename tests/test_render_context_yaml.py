"""Tests for per-domain render context YAML files in glossaries/."""
import importlib.resources

import yaml


def _load_render_context(filename: str) -> dict:
    """Load a render context YAML file from the glossaries package using yaml.safe_load."""
    text = (
        importlib.resources.files("net_agent_harness.glossaries")
        .joinpath(filename)
        .read_text()
    )
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{filename} did not parse as a YAML mapping")
    for key in ("preamble", "summary_format_rules", "snippet_examples"):
        if key not in data:
            raise KeyError(f"Required key '{key}' missing from {filename}")
    return data


class TestRenderContextVlan:
    def test_file_loads_without_error(self):
        data = _load_render_context("render_context_vlan.yaml")
        assert isinstance(data, dict)

    def test_required_keys_present(self):
        data = _load_render_context("render_context_vlan.yaml")
        assert "preamble" in data
        assert "summary_format_rules" in data
        assert "snippet_examples" in data

    def test_preamble_mentions_vlan(self):
        data = _load_render_context("render_context_vlan.yaml")
        assert "VLAN" in data["preamble"]

    def test_summary_format_rules_non_empty(self):
        data = _load_render_context("render_context_vlan.yaml")
        assert data["summary_format_rules"].strip()

    def test_snippet_examples_has_at_least_two(self):
        data = _load_render_context("render_context_vlan.yaml")
        assert isinstance(data["snippet_examples"], list)
        assert len(data["snippet_examples"]) >= 2

    def test_snippet_examples_contain_api_and_cli(self):
        data = _load_render_context("render_context_vlan.yaml")
        backend_types = {ex["backend_type"] for ex in data["snippet_examples"]}
        assert "api" in backend_types
        assert "cli" in backend_types

    def test_api_snippet_has_required_fields(self):
        data = _load_render_context("render_context_vlan.yaml")
        api_snippets = [ex for ex in data["snippet_examples"] if ex.get("backend_type") == "api"]
        assert api_snippets, "Expected at least one API snippet"
        for snippet in api_snippets:
            assert "device_name" in snippet
            assert "render_role" in snippet
            assert "path_hint" in snippet
            assert "api_payload" in snippet
            assert isinstance(snippet["api_payload"], dict)
            assert "commands" in snippet
            assert snippet["commands"] == []

    def test_cli_snippet_has_required_fields(self):
        data = _load_render_context("render_context_vlan.yaml")
        cli_snippets = [ex for ex in data["snippet_examples"] if ex.get("backend_type") == "cli"]
        assert cli_snippets, "Expected at least one CLI snippet"
        for snippet in cli_snippets:
            assert "device_name" in snippet
            assert "render_role" in snippet
            assert "commands" in snippet
            assert isinstance(snippet["commands"], list)
            assert len(snippet["commands"]) > 0
            assert snippet.get("api_payload") is None

    def test_domain_field_is_vlan(self):
        data = _load_render_context("render_context_vlan.yaml")
        assert data.get("domain") == "vlan"


class TestRenderContextRouting:
    def test_file_loads_without_error(self):
        data = _load_render_context("render_context_routing.yaml")
        assert isinstance(data, dict)

    def test_required_keys_present(self):
        data = _load_render_context("render_context_routing.yaml")
        assert "preamble" in data
        assert "summary_format_rules" in data
        assert "snippet_examples" in data

    def test_preamble_mentions_routing(self):
        data = _load_render_context("render_context_routing.yaml")
        assert "routing" in data["preamble"].lower()

    def test_snippet_examples_is_list(self):
        data = _load_render_context("render_context_routing.yaml")
        assert isinstance(data["snippet_examples"], list)

    def test_domain_field_is_routing(self):
        data = _load_render_context("render_context_routing.yaml")
        assert data.get("domain") == "routing"
