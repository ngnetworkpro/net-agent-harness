from pydantic_ai import Agent, RunContext
from ..config import settings
from ..models.changes import ChangeRequest
from ..orchestration.run_context import RunContextData
from ..tools.inventory_tools import get_mock_inventory


change_planner = Agent(
    model=f"ollama:{settings.ollama_model}",
    deps_type=RunContextData,
    output_type=ChangeRequest,
    system_prompt=(
        "You are a network change planner. Convert the user request into a valid ChangeRequest. "
        "Use the inventory tool when the site is known. Do not invent devices outside tool results. "
        "Prefer concise, realistic assumptions and rollback steps."
    ),
)


@change_planner.tool
async def get_inventory(ctx: RunContext[RunContextData], site: str):
    """Get inventory for a site to ground the change plan."""
    return get_mock_inventory(ctx, site)
