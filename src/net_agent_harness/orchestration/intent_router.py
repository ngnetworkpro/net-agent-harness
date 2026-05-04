from dataclasses import dataclass
from ..models.enums import NetworkDomain

@dataclass
class RouteResult:
    domain: NetworkDomain
    confidence: float
    matches: list[str]
    ambiguous: bool = False

DOMAIN_SIGNALS: dict[str, list[str]] = {
    "vlan": ["vlan", "trunk", "access port", "802.1q", "tagged", "untagged", "svi"],
    "acl":  ["acl", "access-list", "permit", "deny", "rule", "firewall"],
    "routing": ["route", "ospf", "bgp", "static route", "prefix", "next-hop", "gateway"],
    "wireless": ["ssid", "ap", "wireless", "wifi", "radio", "channel"],
    "prefix-list": ["prefix-list", "ip prefix"],
    "route-map": ["route-map", "route-policy"],
}

ROUTING_PRIORITY = [
    "vlan",
    "acl",
    "routing",
    "wireless",
    "prefix-list",
    "route-map",
]

FALLBACK_DOMAIN = "generic"

def route_intent(request: str) -> RouteResult:
    lower = request.lower()
    best_domain = FALLBACK_DOMAIN
    best_score = 0
    best_hits = []

    for domain in ROUTING_PRIORITY:
        if domain not in DOMAIN_SIGNALS:
            continue
        signals = DOMAIN_SIGNALS[domain]
        hits = [sig for sig in signals if sig in lower]
        score = len(hits)
        if score > best_score:
            best_domain = domain
            best_score = score
            best_hits = hits

    if best_score == 0:
        return RouteResult(NetworkDomain.OTHER, 0.0, [], ambiguous=True)

    return RouteResult(NetworkDomain(best_domain), min(1.0, 0.5 + 0.2 * best_score), best_hits, ambiguous=False)
