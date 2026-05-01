from dataclasses import dataclass
from ..models.enums import RunStage
from ..models.domain import DomainContext
from .intent_router import RouteResult

@dataclass
class RunContextData:
    run_id: str
    stage: RunStage
    operator: str
    model_name: str
    require_approval_for_execute: bool = True
    inventory_source: str = "mock"
    route_result: RouteResult | None = None
    domain_context: DomainContext | None = None
