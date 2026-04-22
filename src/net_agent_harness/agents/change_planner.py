from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.output import NativeOutput
from pydantic_ai.providers.ollama import OllamaProvider

from ..config import settings
from ..models.changes import PlannedChange
from ..orchestration.run_context import RunContextData
from ..tools.inventory_tools import lookup_inventory

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
        "For requested_change.summary, write a short human-readable sentence. "
        "For requested_change.intent, preserve the user's request in plain English with minimal rewriting. "
        "Do not convert intent into a slug, code, identifier, or compressed keyword string. "
        "Extract explicit scope details from the request, including site names, device names, and device roles when present. "
        "If the user says 'sw1 at HQ', then device_names should include 'sw1' and site should be 'HQ'. "
        "Use the inventory tool when the site is known. "
        "Do not invent devices outside tool results. "
        "Keep assumptions and rollback steps concise and operationally realistic."
    ),
    retries=2,
)


@change_planner.tool
async def get_inventory(ctx: RunContext[RunContextData], site: str):
    return lookup_inventory(ctx, site=site)