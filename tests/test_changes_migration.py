from net_agent_harness.models.changes import PortSpec, VlanChange
from net_agent_harness.models.enums import SwitchportMode


def test_legacy_ports_to_update_access_mode_migrates_to_set_access_vlan() -> None:
    change = VlanChange.model_validate(
        {
            "ports_to_update": [
                PortSpec(interface="ge-0/0/1", vlan_id=12, mode=SwitchportMode.ACCESS),
            ]
        }
    )
    assert len(change.operations) == 1
    assert change.operations[0].op == "set_access_vlan"
