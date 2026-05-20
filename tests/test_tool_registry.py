"""Tests for capability tool registry (Issue #48)."""
import pytest

from net_agent_harness.models.enums import Capability
from net_agent_harness.policies.tool_registry import (
    CAPABILITY_TOOL_REGISTRY,
    assert_tool_allowed,
    get_allowed_tools,
    is_tool_allowed,
)


class TestIsToolAllowed:
    # --- TOPOLOGY ---
    def test_topology_allows_inventory_tools(self):
        assert is_tool_allowed(Capability.TOPOLOGY, "lookup_inventory") is True
        assert is_tool_allowed(Capability.TOPOLOGY, "resolve_site_targets") is True
        assert is_tool_allowed(Capability.TOPOLOGY, "answer_topology_question") is True

    def test_topology_denies_execution_tools(self):
        assert is_tool_allowed(Capability.TOPOLOGY, "apply_config") is False
        assert is_tool_allowed(Capability.TOPOLOGY, "execute_change") is False
        assert is_tool_allowed(Capability.TOPOLOGY, "push_config") is False
        assert is_tool_allowed(Capability.TOPOLOGY, "write_inventory_snapshot") is False
        assert is_tool_allowed(Capability.TOPOLOGY, "write_ipam_snapshot") is False
        assert is_tool_allowed(Capability.TOPOLOGY, "apply_topology_update") is False

    def test_topology_denies_ipam_tools(self):
        assert is_tool_allowed(Capability.TOPOLOGY, "find_prefix") is False
        assert is_tool_allowed(Capability.TOPOLOGY, "answer_ipam_question") is False

    # --- IPAM ---
    def test_ipam_allows_own_tools(self):
        assert is_tool_allowed(Capability.IPAM, "find_prefix") is True
        assert is_tool_allowed(Capability.IPAM, "find_assignment") is True
        assert is_tool_allowed(Capability.IPAM, "answer_ipam_question") is True

    def test_ipam_denies_execution_tools(self):
        assert is_tool_allowed(Capability.IPAM, "apply_config") is False
        assert is_tool_allowed(Capability.IPAM, "push_config") is False
        assert is_tool_allowed(Capability.IPAM, "write_inventory_snapshot") is False
        assert is_tool_allowed(Capability.IPAM, "write_ipam_snapshot") is False
        assert is_tool_allowed(Capability.IPAM, "apply_topology_update") is False

    def test_ipam_denies_inventory_tools(self):
        assert is_tool_allowed(Capability.IPAM, "lookup_inventory") is False
        assert is_tool_allowed(Capability.IPAM, "resolve_site_targets") is False

    def test_ipam_denies_topology_tools(self):
        assert is_tool_allowed(Capability.IPAM, "answer_topology_question") is False

    # --- CHANGE ---
    def test_change_allows_inventory_tools(self):
        assert is_tool_allowed(Capability.CHANGE, "lookup_inventory") is True
        assert is_tool_allowed(Capability.CHANGE, "resolve_from_scope") is True

    def test_change_allows_evaluation_tools(self):
        assert is_tool_allowed(Capability.CHANGE, "evaluate_intent_state") is True
        assert is_tool_allowed(Capability.CHANGE, "validate_config_render") is True

    def test_change_denies_execution_tools(self):
        assert is_tool_allowed(Capability.CHANGE, "apply_config") is False
        assert is_tool_allowed(Capability.CHANGE, "push_config") is False
        assert is_tool_allowed(Capability.CHANGE, "write_inventory_snapshot") is False
        assert is_tool_allowed(Capability.CHANGE, "write_ipam_snapshot") is False
        assert is_tool_allowed(Capability.CHANGE, "apply_topology_update") is False

    # --- INCIDENT ---
    def test_incident_allows_inventory_and_topology(self):
        assert is_tool_allowed(Capability.INCIDENT, "lookup_inventory") is True
        assert is_tool_allowed(Capability.INCIDENT, "answer_topology_question") is True

    def test_incident_denies_execution_tools(self):
        assert is_tool_allowed(Capability.INCIDENT, "apply_config") is False
        assert is_tool_allowed(Capability.INCIDENT, "write_inventory_snapshot") is False
        assert is_tool_allowed(Capability.INCIDENT, "write_ipam_snapshot") is False
        assert is_tool_allowed(Capability.INCIDENT, "apply_topology_update") is False

    # --- unknown tool ---
    def test_unknown_tool_always_denied(self):
        for cap in Capability:
            assert is_tool_allowed(cap, "nonexistent_tool_xyz") is False


class TestGetAllowedTools:
    def test_returns_frozenset(self):
        tools = get_allowed_tools(Capability.TOPOLOGY)
        assert isinstance(tools, frozenset)

    def test_topology_set_non_empty(self):
        assert len(get_allowed_tools(Capability.TOPOLOGY)) > 0

    def test_ipam_set_only_ipam_tools(self):
        tools = get_allowed_tools(Capability.IPAM)
        assert "find_prefix" in tools
        assert "apply_config" not in tools

    def test_all_capabilities_have_entries(self):
        for cap in Capability:
            assert cap in CAPABILITY_TOOL_REGISTRY


class TestAssertToolAllowed:
    def test_permitted_tool_does_not_raise(self):
        assert_tool_allowed(Capability.TOPOLOGY, "lookup_inventory")  # should not raise

    def test_denied_tool_raises_permission_error(self):
        with pytest.raises(PermissionError, match="apply_config"):
            assert_tool_allowed(Capability.IPAM, "apply_config")

    def test_denied_ipam_tool_raises_with_capability_context(self):
        with pytest.raises(PermissionError, match="ipam"):
            assert_tool_allowed(Capability.IPAM, "lookup_inventory")

    def test_denied_change_execution_raises(self):
        with pytest.raises(PermissionError, match="push_config"):
            assert_tool_allowed(Capability.CHANGE, "push_config")

    def test_denied_source_of_truth_write_raises(self):
        with pytest.raises(PermissionError, match="apply_topology_update"):
            assert_tool_allowed(Capability.TOPOLOGY, "apply_topology_update")
