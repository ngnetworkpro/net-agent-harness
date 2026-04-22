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
    temperature=0,
)

change_planner = Agent(
    model,
    deps_type=RunContextData,
    output_type=NativeOutput(PlannedChange),
    system_prompt=(
        "You are a network change planner. "
        "Return only valid structured output matching the schema. "
        "Do not use placeholder values like 'string', 'unknown', example timestamps, or fake IDs. "
        "If a field is not known, use null or an empty list where allowed. "
        "Use the inventory tool when the site is known. "
        "Do not invent devices outside tool results. "
        "Keep the plan concise and operationally realistic."
    ),
    retries=2,
)


@change_planner.tool
async def get_inventory(ctx: RunContext[RunContextData], site: str):
    return lookup_inventory(ctx, site=site)