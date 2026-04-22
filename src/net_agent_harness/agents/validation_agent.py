from pydantic_ai import Agent
from ..config import settings
from ..models.artifacts import ValidationReport
from ..orchestration.run_context import RunContextData


validation_agent = Agent(
    model=f"ollama:{settings.ollama_model}",
    deps_type=RunContextData,
    output_type=ValidationReport,
    system_prompt=(
        "You are a network configuration validation assistant. "
        "Review candidate config output and produce a valid ValidationReport artifact. "
        "Do not approve execution if warnings or obvious gaps exist."
    ),
)
