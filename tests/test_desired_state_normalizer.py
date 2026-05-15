from net_agent_harness.models.enums import NetworkDomain
from net_agent_harness.orchestration.desired_state_normalizer import normalize_desired_state


def test_normalize_vlan_desired_state_keeps_all_vlan_entries():
    normalized = normalize_desired_state(
        NetworkDomain.VLAN,
        {
            "vlans": [
                {"vlan_id": 220, "name": "Engineering"},
                {"vlan_id": 221, "name": "Voice"},
            ]
        },
    )

    assert "operations" in normalized
    assert len(normalized["operations"]) == 2
    assert normalized["operations"][0]["attributes"]["vlan_id"] == 220
    assert normalized["operations"][1]["attributes"]["vlan_id"] == 221
