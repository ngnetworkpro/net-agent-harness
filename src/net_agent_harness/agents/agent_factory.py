# agents/agent_factory.py
from __future__ import annotations
import os
from typing import Any
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from ..config import settings


# ── Provider Adapters ────────────────────────────────────────────────────────
# Each adapter returns a configured model instance.
# Add new providers here without touching any agent file.

def _nvidia_adapter() -> OpenAIChatModel:
    api_key = os.environ.get("NET_AGENT_NVIDIA_API_KEY") or settings.nvidia_api_key
    if not api_key:
        raise ValueError("NET_AGENT_NVIDIA_API_KEY is required for the nvidia provider.")
    return OpenAIChatModel(
        settings.nvidia_model,
        provider=OpenAIProvider(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key,
        ),
    )


def _ollama_adapter() -> OllamaModel:
    return OllamaModel(
        settings.ollama_model,
        provider=OllamaProvider(base_url="http://localhost:11434/v1"),
    )


def _openai_adapter() -> OpenAIChatModel:
    api_key = os.environ.get("NET_AGENT_OPENAI_API_KEY") or settings.openai_api_key
    if not api_key:
        raise ValueError("NET_AGENT_OPENAI_API_KEY is required for the openai provider.")
    return OpenAIChatModel(settings.openai_model)  # add openai_model to Settings


_ADAPTERS: dict[str, callable] = {
    "nvidia": _nvidia_adapter,
    "ollama": _ollama_adapter,
    "openai": _openai_adapter,
}


# ── Model Resolver ───────────────────────────────────────────────────────────
# Auto-select: if NVIDIA key is present → nvidia, else → ollama.
# Can be overridden by setting NET_AGENT_PROVIDER in the environment.

def resolve_model(provider: str | None = None):
    """
    Return a model instance for the given provider name.
    If provider is None, auto-selects based on available credentials.
    """
    if provider is None:
        provider = os.environ.get("NET_AGENT_PROVIDER")
    if provider is None:
        provider = "nvidia" if (
            os.environ.get("NVIDIA_API_KEY") or settings.nvidia_api_key
        ) else "ollama"

    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Available: {list(_ADAPTERS)}"
        )
    return adapter()


# ── Agent Factory ────────────────────────────────────────────────────────────

def build_agent(
    *,
    deps_type: type,
    output_type: Any,
    provider: str | None = None,
    retries: int = 2,
    **agent_kwargs,
) -> Agent:
    """
    Create a pydantic_ai Agent wired to the resolved model.

    Usage in any agent file:
        from ..agents.agent_factory import build_agent

        my_agent = build_agent(
            deps_type=MyDeps,
            output_type=NativeOutput(MyOutput),
        )
    """
    model = resolve_model(provider)
    return Agent(
        model,
        deps_type=deps_type,
        output_type=output_type,
        retries=retries,
        **agent_kwargs,
    )