from pydantic_ai import Agent, RunContext
from ..config import settings
from ..models.artifacts import ConfigRender, RenderRequest
from pydantic_ai.output import NativeOutput

from ..agents.agent_factory import build_agent

change_render_agent = build_agent(
    deps_type=RenderRequest,
    output_type=NativeOutput(ConfigRender),
)


@change_render_agent.output_validator
async def _enforce_snippets(
    ctx: RunContext[RenderRequest], output: ConfigRender
) -> ConfigRender:
    """Enforce that snippets are generated when payload contains operations."""
    deps = ctx.deps
    has_vlan_ops = hasattr(deps.payload, 'vlan_ops') and deps.payload.vlan_ops
    has_interface_ops = hasattr(deps.payload, 'interface_ops') and deps.payload.interface_ops

    if (has_vlan_ops or has_interface_ops) and not output.snippets:
        raise ValueError(
            f"RenderRequest contains operations but no snippets were generated. "
            f"vlan_ops={has_vlan_ops}, interface_ops={has_interface_ops}. "
            f"You MUST produce at least one ConfigSnippet per device with rendered commands."
        )

    return output


@change_render_agent.system_prompt
def render_system_prompt(ctx: RunContext[RenderRequest]) -> str:
    """Generate the system prompt dynamically using the resolved domain context."""

    deps = ctx.deps
    payload_parts = []

    if hasattr(deps.payload, 'vlan_ops') and deps.payload.vlan_ops:
        payload_parts.append("VLAN Operations:")
        for op in deps.payload.vlan_ops:
            payload_parts.append(f"  - VLAN {op.vlan_id}: name={op.vlan_name}, operation={op.operation.value}, target={op.target.name}")

    if hasattr(deps.payload, 'interface_ops') and deps.payload.interface_ops:
        payload_parts.append("Interface Operations:")
        for op in deps.payload.interface_ops:
            mode = op.switchport_mode.value if op.switchport_mode else "unknown"
            payload_parts.append(f"  - {op.interface_name}: mode={mode}, access_vlan={op.access_vlan}, target={op.target.name}")

    payload_section = "\n".join(payload_parts) if payload_parts else "No payload data received."

    preamble = [
        f"""You are a network configuration rendering assistant specialized in VLAN operations.
You produce vendor-specific configuration from an approved planned change diff.

## Input Contract
You receive a RenderRequest with:
- domain: {deps.domain.value}
- intent_type: {deps.intent_type}
- payload: VlanRenderPayload or RoutingRenderPayload

## Render Payload
{payload_section}

## Critical Constraints
1. Do NOT re-call the planner or reinterpret the original request.
2. Only consume the payload fields above.
3. Render safe, reviewable candidate config only. Do not claim anything was executed.
4. Do not invent requirements not present in the payload (e.g., VLAN naming patterns, mandatory port assignments).
5. The summary field MUST be derived deterministically from the payload. Use this exact format:
   - For VLAN creation: "Rendered VLAN <id> (<name>) for <device> — <operation>"
   - For interface changes: "Rendered <mode> port <interface> on <device> — <operation>"
   - For mixed: "Rendered <N> VLAN(s) and <M> interface(s) for <devices>"
   Do NOT use placeholder text like "Awaiting Input" or "Render complete".

## Output Format — REQUIRED
You MUST produce a ConfigRender with non-empty snippets for every device in the payload.
Each snippet represents a device's rendered configuration.

For each device in the payload:
1. Create a ConfigSnippet with:
   - device_name: the target device name
   - rendered_text: API payload structure (JSON string)
   - commands: list of CLI commands (strings)

Example for VLAN 13 on sw1:
- device_name: "sw1"
- rendered_text: '{"vlans": [{{"id": 13, "name": "users3"}}]}'
- commands: ["vlan 13", "name users3"]

## API Payload Format
- vlans: list of objects with 'id' (int) and 'name' (str)
- port_configs: list of objects with 'port', 'mode', 'access_vlan', 'native_vlan', 'allowed_vlans_mode'

## CLI Commands (Juniper Mist style)
- VLAN creation: 'vlan <id>' + 'name <name>'
- Access port: 'set interfaces <port> unit 0 family ethernet-switching vlan members <vlan_id>'
- Trunk port: 'set interfaces <port> unit 0 family ethernet-switching vlan members all'
(Use 'all' for allowed_vlans_mode, NOT numeric expansion like '1-4094')

## allowed_vlans_mode Rule
For trunk ports, always use allowed_vlans_mode='all' in API payloads.
In CLI, use 'switchport trunk allowed vlans all' — never expand VLANs numerically.

## Warnings Policy
Only include warnings when:
- There is a real ambiguity in the payload that affects rendering
- A planned VLAN/interface could not be rendered due to missing data
- Do NOT warn about missing optional data (e.g., port assignments when only VLAN creation was requested)"""
    ]

    return "\n\n".join(preamble)