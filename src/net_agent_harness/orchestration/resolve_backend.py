from ..config import Settings
from ..models.enums import RenderBackendType

# Platforms known to support direct API rendering
API_SUPPORTED_PLATFORMS = {"mist", "meraki"}

def resolve_render_backend(
    settings: Settings,
    platform: str | None = None,
) -> RenderBackendType:
    """Determine the primary render backend deterministically.

    Priority:
    1. User/env-selected terraform or ansible -> that backend is primary.
    2. No user preference + platform supports API -> api is primary.
    3. Fallback -> cli.
    """
    user_backend = settings.execution_backend  # "terraform" | "direct_api" | "ansible"

    if user_backend == "terraform":
        return RenderBackendType.TERRAFORM
    if user_backend == "ansible":
        return RenderBackendType.ANSIBLE

    # "direct_api" or no explicit preference -> check platform for API support
    if platform and platform.lower() in API_SUPPORTED_PLATFORMS:
        return RenderBackendType.API

    return RenderBackendType.CLI

from ..models.artifacts import ConfigSnippet

def generate_cli_fallback_snippet(primary_snippet: ConfigSnippet) -> ConfigSnippet:
    """Generate a CLI fallback snippet from a primary API/Terraform snippet."""
    from ..models.enums import RenderBackendType, RenderRole
    
    # Very basic placeholder generation: just convert the payload text to a comment
    # In a real implementation, this would translate the JSON/YAML to actual CLI commands
    cli_commands = ["! Fallback CLI configuration auto-generated from primary snippet"]
    if primary_snippet.commands:
        cli_commands.append("! Original commands:")
        for cmd in primary_snippet.commands:
            cli_commands.append(f"! {cmd}")
            
    return ConfigSnippet(
        device_name=primary_snippet.device_name,
        backend_type=RenderBackendType.CLI,
        render_role=RenderRole.FALLBACK,
        commands=cli_commands,
        rendered_text="\n".join(cli_commands)
    )

def aggregate_and_label_snippets(
    raw_snippets: list[ConfigSnippet],
    primary_backend: RenderBackendType
) -> list[ConfigSnippet]:
    """Aggregate raw snippets by device, assign roles, and generate fallbacks."""
    from ..models.enums import RenderRole

    aggregated_raw: dict[str, ConfigSnippet] = {}
    for snippet in raw_snippets:
        if snippet.device_name in aggregated_raw:
            existing = aggregated_raw[snippet.device_name]
            existing.commands.extend(snippet.commands)
            if snippet.rendered_text:
                if existing.rendered_text:
                    existing.rendered_text += "\n\n" + snippet.rendered_text
                else:
                    existing.rendered_text = snippet.rendered_text
        else:
            aggregated_raw[snippet.device_name] = snippet

    final_snippets = []
    for snippet in aggregated_raw.values():
        snippet.backend_type = primary_backend
        snippet.render_role = RenderRole.PRIMARY
        final_snippets.append(snippet)
        
        if primary_backend != RenderBackendType.CLI:
            fallback = generate_cli_fallback_snippet(snippet)
            if fallback:
                final_snippets.append(fallback)
                
    return final_snippets
