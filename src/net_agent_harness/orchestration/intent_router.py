import re
from collections.abc import Iterable

from ..models.enums import Capability, NetworkDomain, RequestKind, RoutingStatus
from ..models.routing import RoutedRequest

DOMAIN_SIGNALS: dict[NetworkDomain, tuple[str, ...]] = {
    NetworkDomain.VLAN: ("vlan", "trunk", "access port", "802.1q", "tagged", "untagged", "svi"),
    NetworkDomain.ACL: ("acl", "access-list", "permit", "deny", "rule", "firewall"),
    NetworkDomain.ROUTING: (
        "route",
        "ospf",
        "bgp",
        "static route",
        "prefix",
        "next-hop",
        "gateway",
    ),
    NetworkDomain.WIRELESS: ("ssid", "ap", "wireless", "wifi", "radio", "channel"),
    NetworkDomain.PREFIX_LIST: ("prefix-list", "ip prefix"),
    NetworkDomain.ROUTE_MAP: ("route-map", "route-policy"),
}

ROUTING_PRIORITY: tuple[NetworkDomain, ...] = (
    NetworkDomain.VLAN,
    NetworkDomain.ACL,
    NetworkDomain.ROUTING,
    NetworkDomain.WIRELESS,
    NetworkDomain.PREFIX_LIST,
    NetworkDomain.ROUTE_MAP,
)

QUESTION_TERMS = ("what", "which", "where", "who", "when", "why", "how", "is", "are", "does")
INFO_REQUEST_TERMS = ("show", "list", "display", "describe", "tell me")
CHANGE_VERBS = (
    "add",
    "allow",
    "block",
    "configure",
    "create",
    "delete",
    "enable",
    "disable",
    "modify",
    "provision",
    "remove",
    "set",
    "update",
)
TOPOLOGY_TERMS = (
    "connected",
    "connection",
    "uplink",
    "downlink",
    "neighbor",
    "topology",
    "path",
    "attached",
)
IPAM_TERMS = ("assigned", "available", "free", "subnet", "cidr", "address space", "ipam")
INVENTORY_TERMS = ("device", "switch", "router", "firewall", "site", "inventory", "stack")
INCIDENT_TERMS = (
    "incident",
    "outage",
    "down",
    "failed",
    "failing",
    "broken",
    "degraded",
    "impact",
)

DEVICE_REFERENCE_RE = re.compile(r"\b[a-z]{1,8}\d+\b", re.IGNORECASE)


def _match_terms(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if term in text]


def _detect_domains(text: str) -> dict[NetworkDomain, list[str]]:
    return {domain: _match_terms(text, signals) for domain, signals in DOMAIN_SIGNALS.items()}


def _matched_domains(domain_hits: dict[NetworkDomain, list[str]]) -> list[NetworkDomain]:
    return [domain for domain in ROUTING_PRIORITY if domain_hits.get(domain)]


def _is_question(request: str, lower: str) -> tuple[bool, list[str]]:
    stripped = lower.strip()
    question_hits = _match_terms(lower, QUESTION_TERMS)
    info_hits = _match_terms(lower, INFO_REQUEST_TERMS)
    starts_with_question = any(stripped.startswith(f"{term} ") for term in QUESTION_TERMS)
    question_like = "?" in request or bool(info_hits) or starts_with_question
    return question_like, question_hits + info_hits


def _build_routed_request(
    kind: RequestKind,
    capability: Capability,
    score: int,
    rationale: list[str],
    relevant_domains: list[NetworkDomain],
) -> RoutedRequest:
    return RoutedRequest(
        status=RoutingStatus.ROUTED,
        kind=kind,
        capability=capability,
        confidence=min(0.99, 0.45 + (0.08 * score)),
        requires_run=kind is RequestKind.PLAN,
        requires_approval=capability is Capability.CHANGE,
        relevant_domains=relevant_domains,
        rationale=rationale,
    )


def route_intent(request: str) -> RoutedRequest:
    lower = request.casefold()
    domain_hits = _detect_domains(lower)
    relevant_domains = _matched_domains(domain_hits)

    question_like, question_markers = _is_question(request, lower)
    change_hits = _match_terms(lower, CHANGE_VERBS)
    topology_hits = _match_terms(lower, TOPOLOGY_TERMS)
    ipam_hits = _match_terms(lower, IPAM_TERMS)
    inventory_hits = _match_terms(lower, INVENTORY_TERMS)
    incident_hits = _match_terms(lower, INCIDENT_TERMS)

    if DEVICE_REFERENCE_RE.search(request):
        inventory_hits = [*inventory_hits, "device-reference"]

    domain_signal_hits = [f"{domain.value}:{hit}" for domain, hits in domain_hits.items() for hit in hits]
    signal_count = (
        len(question_markers)
        + len(change_hits)
        + len(topology_hits)
        + len(ipam_hits)
        + len(inventory_hits)
        + len(incident_hits)
        + len(domain_signal_hits)
    )

    candidate_scores: dict[tuple[RequestKind, Capability], int] = {}
    candidate_rationales: dict[tuple[RequestKind, Capability], list[str]] = {}

    topology_score = (2 if question_like else 0) + len(topology_hits) + len(inventory_hits)
    if topology_hits or (question_like and inventory_hits):
        candidate = (RequestKind.ASK, Capability.TOPOLOGY)
        candidate_scores[candidate] = topology_score
        candidate_rationales[candidate] = [*question_markers, *topology_hits, *inventory_hits]

    ipam_score = (2 if question_like else 0) + len(ipam_hits)
    if ipam_hits and question_like:
        candidate = (RequestKind.ASK, Capability.IPAM)
        candidate_scores[candidate] = ipam_score
        candidate_rationales[candidate] = [*question_markers, *ipam_hits]

    change_score = len(domain_signal_hits) + (2 + len(change_hits) if change_hits else 0)
    if relevant_domains and not question_like:
        change_score += 2
    if relevant_domains and (change_hits or not question_like):
        candidate = (RequestKind.PLAN, Capability.CHANGE)
        candidate_scores[candidate] = change_score
        candidate_rationales[candidate] = [*change_hits, *domain_signal_hits]

    incident_score = len(incident_hits) + (1 if question_like or lower.startswith("review ") else 0)
    if incident_hits:
        candidate = (RequestKind.REVIEW, Capability.INCIDENT)
        candidate_scores[candidate] = incident_score
        candidate_rationales[candidate] = incident_hits.copy()

    if not candidate_scores:
        status = RoutingStatus.NEEDS_CLARIFICATION if signal_count else RoutingStatus.BLOCKED
        rationale = (
            ["Request contained weak signals but no safe routing outcome."]
            if signal_count
            else ["No routing signals matched the supported request taxonomy."]
        )
        return RoutedRequest(
            status=status,
            confidence=0.25 if signal_count else 0.0,
            requires_run=False,
            requires_approval=False,
            relevant_domains=relevant_domains,
            rationale=rationale,
        )

    ranked_candidates = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
    (best_kind, best_capability), best_score = ranked_candidates[0]

    if len(ranked_candidates) > 1 and ranked_candidates[1][1] == best_score:
        return RoutedRequest(
            status=RoutingStatus.NEEDS_CLARIFICATION,
            confidence=min(0.6, 0.3 + (0.05 * best_score)),
            requires_run=False,
            requires_approval=False,
            relevant_domains=relevant_domains,
            rationale=[
                "Multiple routing outcomes matched with the same score.",
                f"Top candidates: {best_kind.value}.{best_capability.value} and "
                f"{ranked_candidates[1][0][0].value}.{ranked_candidates[1][0][1].value}.",
            ],
        )

    if best_score < 3:
        return RoutedRequest(
            status=RoutingStatus.NEEDS_CLARIFICATION,
            confidence=min(0.6, 0.3 + (0.05 * best_score)),
            requires_run=False,
            requires_approval=False,
            relevant_domains=relevant_domains,
            rationale=[
                "Matched signals were too weak for a safe routing decision.",
                *candidate_rationales[(best_kind, best_capability)],
            ],
        )

    best_domains = relevant_domains if best_capability is Capability.CHANGE else relevant_domains[:1]
    return _build_routed_request(
        kind=best_kind,
        capability=best_capability,
        score=best_score,
        rationale=candidate_rationales[(best_kind, best_capability)],
        relevant_domains=best_domains,
    )
