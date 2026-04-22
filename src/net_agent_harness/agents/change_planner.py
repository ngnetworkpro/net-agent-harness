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
        "Do not use placeholder values such as 'string', 'unknown', or example timestamps. "
        "If a field is not known and the schema allows it, use null or an empty list. "
        "Preserve key details from the user's request in requested_change.intent, "
        "including VLAN IDs, device names, interface names, and site names. "
        "Do not shorten intent to a single verb. "
        "Keep requested_change.summary short but specific. "
        "Use the inventory tool when the site is known. "
        "Do not invent devices outside tool results. "
        "Prefer concise, operationally realistic assumptions and rollback steps."
    ),
    retries=2,
)


@change_planner.tool
async def get_inventory(ctx: RunContext[RunContextData], site: str):
    return lookup_inventory(ctx, site=site)