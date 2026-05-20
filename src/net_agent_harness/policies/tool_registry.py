"""
Tool registry — maps each capability to its approved tool allowlist.

Tools are grouped by access level so the policy layer can enforce
the principle of least privilege per capability.

Read-only tools may inspect inventory, IPAM, and topology.
They must never reach execution-capable tool paths.
"""
from ..models.enums import Capability

# Tools that only read inventory, topology, or device context.
_INVENTORY_READ_TOOLS: frozenset[str] = frozenset(
    {
        "lookup_inventory",
        "lookup_inventory_sync",
        "resolve_targets",
        "resolve_site_targets",
        "resolve_device_target",
        "lookup_device_context",
        "lookup_device_context_sync",
        "get_inventory",
        "get_site_targets",
        "get_device",
        "resolve_from_scope",
    }
)

# Tools that read IPAM data.
_IPAM_READ_TOOLS: frozenset[str] = frozenset(
    {
        "find_prefix",
        "find_assignment",
        "answer_ipam_question",
    }
)

# Tools that read topology / link data.
_TOPOLOGY_READ_TOOLS: frozenset[str] = frozenset(
    {
        "answer_topology_question",
    }
)

# Tools that evaluate or validate current state without pushing config.
_EVALUATION_TOOLS: frozenset[str] = frozenset(
    {
        "evaluate_intent_state",
        "validate_config_render",
    }
)

# Tools reserved for future execution or source-of-truth write paths.
# They remain unavailable to all current capabilities until explicit
# approval-gated orchestration is added.
_EXECUTION_TOOLS: frozenset[str] = frozenset(
    {
        "apply_config",
        "execute_change",
        "push_config",
        "write_inventory_snapshot",
        "write_ipam_snapshot",
        "apply_topology_update",
    }
)

# Canonical allowlist per capability.
# Capabilities may only call tools explicitly listed here.
CAPABILITY_TOOL_REGISTRY: dict[Capability, frozenset[str]] = {
    Capability.TOPOLOGY: _INVENTORY_READ_TOOLS | _TOPOLOGY_READ_TOOLS,
    Capability.IPAM: _IPAM_READ_TOOLS,
    Capability.CHANGE: _INVENTORY_READ_TOOLS | _EVALUATION_TOOLS,
    Capability.INCIDENT: _INVENTORY_READ_TOOLS | _TOPOLOGY_READ_TOOLS | _IPAM_READ_TOOLS,
    Capability.SITE: (
        _INVENTORY_READ_TOOLS | _TOPOLOGY_READ_TOOLS | _IPAM_READ_TOOLS | _EVALUATION_TOOLS
    ),
}


def is_tool_allowed(capability: Capability, tool_name: str) -> bool:
    """Return True if *tool_name* is approved for *capability*.

    Execution tools are never returned as allowed — they require a separate
    approval gate that is not yet implemented.
    """
    if tool_name in _EXECUTION_TOOLS:
        return False
    allowed = CAPABILITY_TOOL_REGISTRY.get(capability, frozenset())
    return tool_name in allowed


def get_allowed_tools(capability: Capability) -> frozenset[str]:
    """Return the frozen set of tools approved for *capability*."""
    return CAPABILITY_TOOL_REGISTRY.get(capability, frozenset())


def assert_tool_allowed(capability: Capability, tool_name: str) -> None:
    """Raise PermissionError if *tool_name* is not approved for *capability*."""
    if not is_tool_allowed(capability, tool_name):
        raise PermissionError(
            f"Tool '{tool_name}' is not permitted for capability '{capability.value}'."
        )
