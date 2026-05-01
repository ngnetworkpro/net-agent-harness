DOMAIN_SIGNALS: dict[str, list[str]] = {
    "vlan": ["vlan", "trunk", "access port", "802.1q", "tagged", "untagged"],
    "acl":  ["acl", "access-list", "permit", "deny", "rule", "firewall"],
    "routing": ["route", "ospf", "bgp", "static route", "prefix", "next-hop"],
    "wireless": ["ssid", "ap", "wireless", "wifi", "radio", "channel"],
}
FALLBACK_DOMAIN = "generic"

def route_intent(request: str) -> str:
    lower = request.lower()
    for domain, signals in DOMAIN_SIGNALS.items():
        if any(sig in lower for sig in signals):
            return domain
    return FALLBACK_DOMAIN
