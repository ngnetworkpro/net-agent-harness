from ..models.artifacts import ConfigRenderOutput, RenderRequest
from ..models.enums import RenderBackendType, RenderRole
from pydantic_ai import RunContext
from pydantic_ai.output import NativeOutput

from ..agents.agent_factory import build_agent
from ..orchestration.domain_loader import load_render_context

change_render_agent = build_agent(
    deps_type=RenderRequest,
    output_type=NativeOutput(ConfigRenderOutput),
)


@change_render_agent.output_validator
async def _enforce_snippets(
    ctx: RunContext[RenderRequest], output: ConfigRenderOutput
) -> ConfigRenderOutput:
    """Enforce that snippets are generated when payload contains operations."""
    deps = ctx.deps
    has_vlan_ops = hasattr(deps.payload, "vlan_ops") and deps.payload.vlan_ops
    has_interface_ops = hasattr(deps.payload, "interface_ops") and deps.payload.interface_ops

    if not (has_vlan_ops or has_interface_ops):
        return output

    if not output.snippets:
        raise ValueError(
            f"RenderRequest contains operations but no snippets were generated. "
            f"vlan_ops={has_vlan_ops}, interface_ops={has_interface_ops}. "
            f"Produce at least one ConfigSnippet per device."
        )

    for snippet in output.snippets:
        is_api_primary = (
            snippet.backend_type == RenderBackendType.API
            and snippet.render_role == RenderRole.PRIMARY
        )
        is_cli_fallback = (
            snippet.backend_type == RenderBackendType.CLI
        )
        if is_api_primary and not snippet.api_payload:
            raise ValueError(
                f"API-primary snippet for device '{snippet.device_name}' "
                f"must have a non-empty api_payload."
            )
        if is_cli_fallback and not snippet.commands:
            raise ValueError(
                f"CLI fallback snippet for device '{snippet.device_name}' "
                f"must have non-empty commands."
            )

    return output


@change_render_agent.system_prompt
def render_system_prompt(ctx: RunContext[RenderRequest]) -> str:
    """Generate the system prompt dynamically using the resolved domain context."""

    deps = ctx.deps
    domain_val = deps.domain.value
    intent_val = deps.intent_type

    # Load per-domain render context from YAML.
    render_context = load_render_context(domain_val)

    # Build the payload description using describe_ops() when available.
    if hasattr(deps.payload, "describe_ops"):
        payload_lines = deps.payload.describe_ops()
        payload_section = "\n".join(payload_lines) if payload_lines else "No payload data received."
    else:
        payload_section = "No payload data received."

    parts: list[str] = []

    # 1. Domain preamble (from YAML).
    parts.append(render_context["preamble"].rstrip())
    parts.append("")

    # 2. Input Contract (shared invariant — dynamic domain/intent values).
    parts += [
        "## Input Contract",
        "You receive a RenderRequest with:",
        "- domain: " + domain_val,
        "- intent_type: " + intent_val,
        "- payload: VlanRenderPayload or RoutingRenderPayload",
        "",
    ]

    # 3. Render Payload (dynamic, from payload.describe_ops()).
    parts += [
        "## Render Payload",
        payload_section,
        "",
    ]

    # 4. Domain summary format rules (from YAML).
    summary_rules = render_context["summary_format_rules"].strip()
    if summary_rules:
        parts.append(summary_rules)
        parts.append("")

    # 5. Output Format — REQUIRED (shared invariant).
    parts += [
        "## Output Format — REQUIRED",
        "You MUST produce output with a summary string and non-empty snippets for every device in the payload.",
        "Each snippet represents a device's rendered configuration.",
        "",
        "For API-primary devices:",
        "Create a ConfigSnippet with:",
        '   - device_name: the target device name',
        '   - backend_type: "api"',
        '   - render_role: "primary"',
        '   - path_hint: endpoint or resource path hint (e.g., "/networks/{networkId}/vlans")',
        "   - api_payload: structured dict with the full API request body",
        "   - rendered_text: human-readable JSON preview of the API call",
        "   - commands: [] (empty — CLI commands do not belong in an API-primary snippet)",
        "",
        "For CLI-fallback snippets (emitted alongside the primary when applicable):",
        "Create a second ConfigSnippet with:",
        "   - device_name: same device name",
        '   - backend_type: "cli"',
        '   - render_role: "fallback"',
        "   - commands: ordered list of vendor-appropriate CLI commands",
        "   - rendered_text: commands joined as readable text",
        "   - api_payload: null",
        "",
    ]

    # 6. Domain snippet examples (from YAML, formatted as text).
    for example in render_context["snippet_examples"]:
        desc = example.get("description", "Example snippet")
        parts.append(f"{desc}:")
        for field, value in example.items():
            if field != "description":
                parts.append(f"- {field}: {value}")
        parts.append("")

    # 7. Shared invariants — API payload format, CLI commands, mode rules, warnings.
    parts += [
        "## API Payload Format",
        "- The api_payload is the canonical field for API operations.",
        "- vlans: list of objects with id (int) and name (str)",
        "- port_configs: list of objects with port, mode, access_vlan, native_vlan, allowed_vlans_mode",
        "",
        "## CLI Commands",
        "- Produce CLI commands in the `commands` list for each CLI-fallback ConfigSnippet.",
        "- Use the command syntax appropriate for the target device's vendor/platform.",
        "- Do NOT invent CLI syntax. Use only the operations described in the payload.",
        "- For VLAN creation: include commands that create the VLAN and set its name.",
        "- For interface changes: include commands that set the switchport mode and VLAN membership.",
        "",
        "## allowed_vlans_mode Rule",
        "For trunk ports, always use allowed_vlans_mode=all in API payloads.",
        "Never expand VLANs numerically (e.g., do not use 1-4094).",
        "",
        "## Warnings Policy",
        "Only include warnings when:",
        "- There is a real ambiguity in the payload that affects rendering",
        "- A planned VLAN/interface could not be rendered due to missing data",
        "- Do NOT warn about missing optional data (e.g., port assignments when only VLAN creation was requested)",
    ]

    return "\n".join(parts)
