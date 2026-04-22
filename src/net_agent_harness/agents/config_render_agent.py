from pydantic_ai import Agent
from ..config import settings
from ..models.artifacts import ConfigRender
from ..orchestration.run_context import RunContextData


config_render_agent = Agent(
    model=f"ollama:{settings.ollama_model}",
    deps_type=RunContextData,
    output_type=ConfigRender,
    system_prompt=(
        "You are a network configuration rendering assistant. "
        "Given a requested change, produce a valid ConfigRender artifact. "
        "Render safe, reviewable candidate commands only. "
        "Do not claim anything was executed. "
        "Prefer minimal config snippets and include warnings when assumptions are required."
    ),
)
