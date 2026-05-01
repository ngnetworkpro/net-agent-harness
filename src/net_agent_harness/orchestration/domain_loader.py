from functools import lru_cache
import importlib.resources
import yaml
from ..models.domain import DomainContext, TermEntry, IntentSpec, FewShotExample

class DomainLoadError(Exception):
    """Raised when a domain context cannot be loaded."""
    pass

@lru_cache(maxsize=16)
def load_domain_context(domain: str) -> DomainContext:
    try:
        core_text = importlib.resources.files("net_agent_harness.glossaries").joinpath("core_terms.yaml").read_text()
        core = yaml.safe_load(core_text)
    except FileNotFoundError:
        core = {"terms": []}

    try:
        domain_text = importlib.resources.files("net_agent_harness.glossaries.domains").joinpath(f"{domain}.yaml").read_text()
        domain_data = yaml.safe_load(domain_text)
    except FileNotFoundError as exc:
        raise DomainLoadError(f"Domain context not found for '{domain}'") from exc

    terms = [TermEntry(**t) for t in core.get("terms", [])] + \
            [TermEntry(**t) for t in domain_data.get("terms", [])]
    intents = [IntentSpec(**i) for i in domain_data.get("intents", [])]
    examples = [
        FewShotExample(
            user=e["user"],
            normalized_intent=e["normalized_intent"],
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
