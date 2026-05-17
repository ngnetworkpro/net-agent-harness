import importlib.resources

import yaml

from ..models.artifacts import ConfigRenderOutput, RenderRequest
from ..models.enums import RenderBackendType, RenderRole
from pydantic_ai import RunContext
from pydantic_ai.output import NativeOutput

from ..agents.agent_factory import build_agent

SUPPORTED_RENDER_DOMAINS = {"vlan", "routing"}


def _load_render_context(domain_value: str) -> dict:
    """Load domain-specific render context YAML from glossaries."""
    try:
        text = (
            importlib.resources.files("net_agent_harness.glossaries")
            .joinpath(f"render_context_{domain_value}.yaml")
            .read_text()
        )
        return yaml.safe_load(text) or {}
    except (FileNotFoundError, TypeError):
        return {}


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

    if not deps.payload.has_ops():
        return output

    if not output.snippets:
        raise ValueError(
            "RenderRequest contains operations but no snippets were generated. "
            "Produce at least one ConfigSnippet per device."
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

    domain_errors = deps.payload.validate_snippets(output.snippets)
    if domain_errors:
        raise ValueError(
            "Domain-specific snippet validation failed: " + "; ".join(domain_errors)
        )

    return output


@change_render_agent.system_prompt
def render_system_prompt(ctx: RunContext[RenderRequest]) -> str:
    """Generate the system prompt dynamically using the resolved domain context."""

    deps = ctx.deps
    domain_val = deps.domain.value
    intent_val = deps.intent_type

    context = _load_render_context(domain_val)
    preamble = context.get("preamble", "").strip()
    summary_rules = context.get("summary_format_rules", "").strip()
    snippet_examples = context.get("snippet_examples", [])

    payload_lines = deps.payload.describe_ops()
    payload_section = "\n".join(payload_lines) if payload_lines else "No payload data received."

    parts: list[str] = []

    if preamble:
        parts.append(preamble)
        parts.append("")

    parts.extend([
        "## Input Contract",
        "You receive a RenderRequest with:",
        "- domain: " + domain_val,
        "- intent_type: " + intent_val,
        "",
        "## Render Payload",
        payload_section,
        "",
    ])

    if summary_rules:
        parts.extend([
            "## Summary Format",
            summary_rules,
            "",
        ])

    if snippet_examples:
        parts.append("## Snippet Examples")
        for ex in snippet_examples:
            parts.append(f"- description: {ex.get('description', '')}")
            parts.append(f"  device_name: {ex.get('device_name', '')}")
            parts.append(f"  backend_type: {ex.get('backend_type', '')}")
            parts.append(f"  render_role: {ex.get('render_role', '')}")
            if ex.get("path_hint"):
                parts.append(f"  path_hint: {ex['path_hint']}")
            if ex.get("api_payload"):
                parts.append(f"  api_payload: {ex['api_payload']}")
            if ex.get("commands"):
                parts.append(f"  commands: {ex['commands']}")
        parts.append("")

    parts.extend([
        "## Warnings Policy",
        "Only include warnings when:",
        "- There is a real ambiguity in the payload that affects rendering",
        "- A planned operation could not be rendered due to missing data",
        "- Do NOT warn about missing optional data",
    ])

    return "\n".join(parts)
