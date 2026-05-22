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
    Capability.SITE: "site_workflow",
}

DISPATCH_MODE_BY_ROUTE: dict[tuple[RequestKind, Capability], DispatchMode] = {
    (RequestKind.ASK, Capability.TOPOLOGY): DispatchMode.DIRECT_ANSWER,
    (RequestKind.ASK, Capability.IPAM): DispatchMode.DIRECT_ANSWER,
    (RequestKind.PLAN, Capability.CHANGE): DispatchMode.WORKFLOW_RUN,
    (RequestKind.PLAN, Capability.IPAM): DispatchMode.WORKFLOW_RUN,
    (RequestKind.PLAN, Capability.TOPOLOGY): DispatchMode.WORKFLOW_RUN,
    (RequestKind.PLAN, Capability.SITE): DispatchMode.WORKFLOW_RUN,
    (RequestKind.REVIEW, Capability.INCIDENT): DispatchMode.WORKFLOW_RUN,
}

INITIAL_STAGE_BY_ROUTE: dict[tuple[RequestKind, Capability], RunStage] = {
    (RequestKind.PLAN, Capability.CHANGE): RunStage.PLAN,
    (RequestKind.PLAN, Capability.IPAM): RunStage.PLAN,
    (RequestKind.PLAN, Capability.TOPOLOGY): RunStage.PLAN,
    (RequestKind.PLAN, Capability.SITE): RunStage.DISCOVER,
    (RequestKind.REVIEW, Capability.INCIDENT): RunStage.INCIDENT,
}


def dispatch_request(request: RoutedRequest) -> DispatchDecision:
    if request.status is not RoutingStatus.ROUTED:
        return DispatchDecision(
            mode=DispatchMode.BLOCKED,
            handler="clarification_required",
            reason="Routing did not produce a safe execution path.",
        )

    if request.kind is None or request.capability is None:
        # Invariant: request.status check above plus model-validator
        # ensures these are not None when status is ROUTED.
        raise ValueError("Routed request is missing kind or capability.")

    handler = HANDLER_REGISTRY[request.capability]
    mode = DISPATCH_MODE_BY_ROUTE[(request.kind, request.capability)]

    if mode is DispatchMode.WORKFLOW_RUN:
        initial_stage = INITIAL_STAGE_BY_ROUTE.get((request.kind, request.capability))
        return DispatchDecision(
            mode=mode,
            handler=handler,
            reason="Workflow selected from deterministic routing output.",
            initial_stage=initial_stage,
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
        reason="Request routing is recognized but no execution workflow is enabled yet.",
    )
