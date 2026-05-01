from dataclasses import dataclass
from ..models.enums import RunStage
from ..models.domain import DomainContext


@dataclass
class RunContextData:
    run_id: str
    stage: RunStage
    operator: str
    model_name: str
    require_approval_for_execute: bool = True
    inventory_source: str = "mock"
    domain: str = "generic"
    domain_context: DomainContext | None = None
