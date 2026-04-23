from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.output import NativeOutput
from pydantic_ai.providers.ollama import OllamaProvider

from ..config import settings
from ..models.changes import PlannedChange
from ..orchestration.run_context import RunContextData
from ..tools.inventory_tools import lookup_inventory, resolve_device_target, resolve_site_targets

model = OllamaModel(
    settings.ollama_model,
    provider=OllamaProvider(base_url="http://localhost:11434/v1"),
)

change_planner = Agent(
    model,
    deps_type=RunContextData,
    output_type=NativeOutput(PlannedChange),
    system_prompt=(
        "You are a network change planner. "
        "Return only valid structured output matching the schema. "
        "Do not use placeholder values such as 'string' or 'unknown'. "
        "If a field is not known and the schema allows it, use null or an empty list. "
        "Write requested_change.summary as a short human-readable sentence. "
        "Write requested_change.intent in plain English and preserve important details from the user's request, including VLAN IDs, device names, and site names. "
        "Do not convert intent into a slug, identifier, or code-like label. "
        "Extract explicit scope details from the request, including site names, device names, and device roles when present. "
        "Always call an inventory tool when a site or device name is known. "
        "Populate resolved_targets only with devices returned from inventory tools. "
        "Do not invent targets. "
        "If inventory returns no matching targets, set clarifications_needed to explain why. "
        "Classify target_scope as device, site, or ambiguous based on what can be resolved. "
        "If the user says 'sw1 at HQ', call get_device_target('HQ', 'sw1') and use the result. "
        "If the user says 'site HQ', call get_site_targets('HQ') and use the result. "
        "If the request cannot be safely targeted, target_scope should be ambiguous and clarifications_needed should explain what is missing. "
        "Use the inventory tool when the site is known. "
        "Do not invent devices outside tool results. "
        "Always return a rollback_plan object. "
        "Keep assumptions and rollback steps concise and operationally realistic."
    ),
    retries=2,
)


@change_planner.tool
async def get_inventory(ctx: RunContext[RunContextData], site: str):
    return lookup_inventory(ctx, site=site)

@change_planner.tool
async def get_site_targets(ctx: RunContext[RunContextData], site: str):
    return resolve_site_targets(ctx, site=site)


@change_planner.tool
async def get_device_target(ctx: RunContext[RunContextData], site: str | None, device_name: str):
    return resolve_device_target(ctx, site=site, device_name=device_name)