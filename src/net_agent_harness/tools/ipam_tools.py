import ipaddress
import re

from ..adapters.ipam_adapter import IPAMAdapter
from ..adapters.mock_ipam_adapter import MockIPAMAdapter

_CIDR_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b")
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _get_adapter(inventory_source: str) -> IPAMAdapter:
    # NetBox-backed IPAM can be added later. Keep behavior deterministic today.
    _ = inventory_source
    return MockIPAMAdapter()


def find_prefix(cidr: str, inventory_source: str = "mock") -> dict:
    adapter = _get_adapter(inventory_source)
    for prefix in adapter.list_prefixes():
        if prefix.cidr == cidr:
            return {"found": True, "prefix": prefix.model_dump(mode="json")}
    return {"found": False, "prefix": None}


def find_assignment(ip_or_cidr: str, inventory_source: str = "mock") -> dict:
    adapter = _get_adapter(inventory_source)
    ip_text = ip_or_cidr.split("/")[0]
    try:
        target_ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return {"found": False, "assignment": None}

    for assignment in adapter.list_assignments():
        iface = ipaddress.ip_interface(assignment.address)
        if iface.ip == target_ip:
            return {"found": True, "assignment": assignment.model_dump(mode="json")}
    return {"found": False, "assignment": None}


def answer_ipam_question(question: str, inventory_source: str = "mock") -> dict:
    cidr_match = _CIDR_RE.search(question)
    if cidr_match:
        cidr = cidr_match.group(0)
        prefix_result = find_prefix(cidr, inventory_source=inventory_source)
        if prefix_result["found"]:
            prefix = prefix_result["prefix"]
            return {
                "answer": f"Prefix {cidr} is assigned at site {prefix['site']} (status: {prefix['status']}).",
                "data": prefix_result,
            }
        return {
            "answer": f"Prefix {cidr} is not currently assigned in the configured IPAM source.",
            "data": prefix_result,
        }

    ip_match = _IP_RE.search(question)
    if ip_match:
        ip_address = ip_match.group(0)
        assignment_result = find_assignment(ip_address, inventory_source=inventory_source)
        if assignment_result["found"]:
            assignment = assignment_result["assignment"]
            interface = assignment.get("interface")
            interface_text = f" ({interface})" if interface else ""
            return {
                "answer": f"IP {ip_address} is assigned to {assignment['device_name']}{interface_text}.",
                "data": assignment_result,
            }
        return {
            "answer": f"IP {ip_address} is not assigned in the configured IPAM source.",
            "data": assignment_result,
        }

    return {
        "answer": "I could not detect a specific IP or prefix in the question.",
        "data": {"found": False},
    }
