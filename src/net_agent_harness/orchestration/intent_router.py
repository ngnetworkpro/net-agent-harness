from dataclasses import dataclass

@dataclass
class RouteResult:
    domain: str
    confidence: float
    matches: list[str]
    ambiguous: bool = False

DOMAIN_SIGNALS: dict[str, list[str]] = {
    "vlan": ["vlan", "trunk", "access port", "802.1q", "tagged", "untagged", "svi"],
    "acl":  ["acl", "access-list", "permit", "deny", "rule", "firewall"],
    "routing": ["route", "ospf", "bgp", "static route", "prefix", "next-hop", "gateway"],
    "wireless": ["ssid", "ap", "wireless", "wifi", "radio", "channel"],
}

ROUTING_PRIORITY = [
    "vlan",
    "acl",
    "routing",
    "wireless",
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
        return RouteResult(FALLBACK_DOMAIN, 0.0, [], ambiguous=True)

    return RouteResult(best_domain, min(1.0, 0.5 + 0.2 * best_score), best_hits, ambiguous=False)
