import re

from .inventory_tools import lookup_inventory_sync

_NEIGHBOR_RE = re.compile(r"\b(?:to|toward)\s+([a-z0-9_-]+)\b", re.IGNORECASE)
_DEVICE_RE = re.compile(r"\b[a-z]{1,8}\d+\b", re.IGNORECASE)


def _extract_edges(inventory: dict) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    devices = inventory.get("results", [])
    known_names = {str(device.get("name", "")).lower() for device in devices}
    for device in devices:
        source = device.get("name")
        for interface in device.get("interfaces", []):
            description = interface.get("description") or ""
            match = _NEIGHBOR_RE.search(description)
            if not match:
                continue
            target = match.group(1)
            if target.lower() not in known_names:
                continue
            edges.append(
                {
                    "source_device": source,
                    "source_interface": interface.get("name"),
                    "target_device": target,
                }
            )
    return edges


def answer_topology_question(question: str, inventory_source: str = "mock") -> dict:
    inventory = lookup_inventory_sync(inventory_source=inventory_source, site="HQ")
    edges = _extract_edges(inventory)
    device_match = _DEVICE_RE.search(question)
    if device_match:
        device_name = device_match.group(0)
        related = [edge for edge in edges if edge["source_device"] == device_name]
        if related:
            targets = ", ".join(f"{edge['target_device']} via {edge['source_interface']}" for edge in related)
            return {"answer": f"{device_name} has links to {targets}.", "data": {"links": related}}
        return {"answer": f"No topology links found for {device_name}.", "data": {"links": []}}

    return {
        "answer": f"Discovered {len(edges)} topology links in inventory.",
        "data": {"links": edges},
    }
