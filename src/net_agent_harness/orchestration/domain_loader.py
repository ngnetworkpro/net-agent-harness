import copy
from functools import lru_cache
import importlib.resources
from typing import Any
import yaml
from ..models.domain import DomainContext, TermEntry, IntentSpec, FewShotExample
from ..models.enums import NetworkDomain

class DomainLoadError(Exception):
    """Raised when a domain context cannot be loaded."""
    pass

@lru_cache(maxsize=16)
def _load_domain_context_cached(domain: NetworkDomain) -> DomainContext:
    try:
        core_text = importlib.resources.files("net_agent_harness.glossaries").joinpath("core_terms.yaml").read_text()
        core = yaml.safe_load(core_text)
    except FileNotFoundError:
        core = {"terms": []}

    try:
        domain_text = importlib.resources.files("net_agent_harness.glossaries.domains").joinpath(f"{domain.value}.yaml").read_text()
        domain_data = yaml.safe_load(domain_text)
    except FileNotFoundError as exc:
        raise DomainLoadError(f"Domain context not found for '{domain}'") from exc

    terms = [TermEntry(**t) for t in core.get("terms", [])] + \
            [TermEntry(**t) for t in domain_data.get("terms", [])]
    intents = [IntentSpec(**i) for i in domain_data.get("intents", [])]
    examples = [
        FewShotExample(
            user=e["user"],
            normalized_intent=e.get("normalized_intent"),
            extra={k: v for k, v in e.items() if k not in ("user", "normalized_intent")}
        )
        for e in domain_data.get("examples", [])
    ]
    return DomainContext(
        domain=domain,
        description=domain_data.get("description", ""),
        terms=terms,
        intents=intents,
        examples=examples,
    )


def load_domain_context(domain: NetworkDomain) -> DomainContext:
    return copy.deepcopy(_load_domain_context_cached(domain))


@lru_cache(maxsize=16)
def load_render_context(domain: str) -> dict[str, Any]:
    """Load the render context YAML for the given domain name.

    Locates ``glossaries/render_context_{domain}.yaml`` and returns its
    contents as a plain dict.  The returned dict is guaranteed to contain
    the keys ``preamble``, ``summary_format_rules``, and
    ``snippet_examples``.

    Raises:
        FileNotFoundError: if the render context file does not exist for
            the given domain.
        KeyError: if a required key is missing from the YAML file.
    """
    filename = f"render_context_{domain}.yaml"
    try:
        text = (
            importlib.resources.files("net_agent_harness.glossaries")
            .joinpath(filename)
            .read_text()
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Render context not found for domain '{domain}': {filename}"
        ) from exc

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"Render context file '{filename}' did not parse as a YAML mapping"
        )

    required_keys = ("preamble", "summary_format_rules", "snippet_examples")
    for key in required_keys:
        if key not in data:
            raise KeyError(
                f"Required key '{key}' missing from render context file '{filename}'"
            )

    return data
