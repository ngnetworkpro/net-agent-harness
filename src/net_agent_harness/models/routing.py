from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import Capability, NetworkDomain, RequestKind, ResourceType, RoutingStatus

ALLOWED_ROUTING_COMBINATIONS = {
    (RequestKind.ASK, Capability.TOPOLOGY),
    (RequestKind.ASK, Capability.IPAM),
    (RequestKind.PLAN, Capability.CHANGE),
    (RequestKind.PLAN, Capability.IPAM),
    (RequestKind.PLAN, Capability.TOPOLOGY),
    (RequestKind.PLAN, Capability.SITE),
    (RequestKind.REVIEW, Capability.INCIDENT),
}


class RoutedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RoutingStatus = RoutingStatus.ROUTED
    kind: RequestKind | None = None
    capability: Capability | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    requires_run: bool = False
    requires_approval: bool = False
    relevant_domains: list[NetworkDomain] = Field(default_factory=list)
    target_resource_types: list[ResourceType] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_kind_and_capability(self) -> "RoutedRequest":
        if self.status is RoutingStatus.ROUTED:
            if self.kind is None or self.capability is None:
                raise ValueError("Routed requests must include both kind and capability.")
            if (self.kind, self.capability) not in ALLOWED_ROUTING_COMBINATIONS:
                raise ValueError(
                    "Unsupported routed request combination: "
                    f"{self.kind.value}+{self.capability.value}."
                )
            return self

        if self.kind is not None or self.capability is not None:
            raise ValueError(
                "Non-routed requests must not include kind or capability until clarified."
            )
        return self

    @property
    def domain(self) -> NetworkDomain:
        return self.relevant_domains[0] if self.relevant_domains else NetworkDomain.OTHER

    @property
    def matches(self) -> list[str]:
        return self.rationale

    @property
    def ambiguous(self) -> bool:
        return self.status is not RoutingStatus.ROUTED
