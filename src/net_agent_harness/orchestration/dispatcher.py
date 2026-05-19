from enum import Enum

from pydantic import BaseModel, ConfigDict

from ..models.enums import Capability, RequestKind, RoutingStatus, RunStage
from ..models.routing import RoutedRequest


class DispatchMode(str, Enum):
    DIRECT_ANSWER = "direct_answer"
    WORKFLOW_RUN = "workflow_run"
    BLOCKED = "blocked"


class DispatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: DispatchMode
    handler: str
    reason: str
    initial_stage: RunStage | None = None


HANDLER_REGISTRY: dict[Capability, str] = {
    Capability.TOPOLOGY: "topology_answer",
    Capability.IPAM: "ipam_lookup",
    Capability.CHANGE: "change_workflow",
    Capability.INCIDENT: "incident_review",
}

DISPATCH_MODE_BY_ROUTE: dict[tuple[RequestKind, Capability], DispatchMode] = {
    (RequestKind.ASK, Capability.TOPOLOGY): DispatchMode.DIRECT_ANSWER,
    (RequestKind.ASK, Capability.IPAM): DispatchMode.DIRECT_ANSWER,
    (RequestKind.PLAN, Capability.CHANGE): DispatchMode.WORKFLOW_RUN,
    (RequestKind.REVIEW, Capability.INCIDENT): DispatchMode.BLOCKED,
}


def dispatch_request(request: RoutedRequest) -> DispatchDecision:
    if request.status is not RoutingStatus.ROUTED:
        return DispatchDecision(
            mode=DispatchMode.BLOCKED,
            handler="clarification_required",
            reason="Routing did not produce a safe execution path.",
        )

    assert request.kind is not None
    assert request.capability is not None

    handler = HANDLER_REGISTRY[request.capability]
    mode = DISPATCH_MODE_BY_ROUTE[(request.kind, request.capability)]

    if mode is DispatchMode.WORKFLOW_RUN:
        return DispatchDecision(
            mode=mode,
            handler=handler,
            reason="Planner change workflow selected from deterministic routing output.",
            initial_stage=RunStage.PLAN,
        )

    if mode is DispatchMode.DIRECT_ANSWER:
        return DispatchDecision(
            mode=mode,
            handler=handler,
            reason="Request can be handled without starting the staged change workflow.",
        )

    return DispatchDecision(
        mode=mode,
        handler=handler,
        reason="Incident review routing is recognized but no execution workflow is enabled yet.",
    )
