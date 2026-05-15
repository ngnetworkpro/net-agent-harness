import pytest
from pydantic import ValidationError

from net_agent_harness.models.artifacts import Finding
from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk, NetworkDomain


def test_pydantic_bounds_validation():
    from net_agent_harness.models.changes import VlanSpec, PortSpec

    # Test VLAN ID bounds (must be between 1 and 4094)
    with pytest.raises(ValidationError):
        VlanSpec(id=-5, name="Invalid")

    with pytest.raises(ValidationError):
        VlanSpec(id=5000, name="Invalid")

    # Valid VLAN ID should pass
    valid_vlan = VlanSpec(id=10, name="Valid")
    assert valid_vlan.id == 10

    # Test PortSpec mode enum
    with pytest.raises(ValidationError):
        PortSpec(interface="ge-0/0/1", vlan_id=220, mode="hybrid")

    # Valid PortSpec should pass
    valid_port = PortSpec(interface="ge-0/0/1", vlan_id=220, mode="access")
    assert valid_port.mode == "access"

def test_strict_structural_validation():
    from net_agent_harness.models.changes import VlanDesiredState, VlanDesiredStateOperation, VlanAttributes

    # Test forbid extra properties
    with pytest.raises(ValidationError):
        VlanDesiredStateOperation(
            object_type="vlan",
            operation="ensure_present",
            attributes=VlanAttributes(vlan_id=10),
            invented_property="should fail"
        )

    with pytest.raises(ValidationError):
        VlanDesiredState(
            operations=[],
            apply_immediately=True
        )

def test_change_request_model():
    model = ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="change-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            requested_by="tester",
            intent="Add VLAN 220 to sw1",
        ),
        target_scope="device",
        rollback_plan=RollbackPlan(
            summary="Revert",
            trigger_conditions=["Error"],
            rollback_steps=["Undo"]
        ),
        risk=ChangeRisk.LOW,
    )
    assert model.scope.site == "HQ"


def test_requested_change_prefers_vlan_desired_state_model():
    requested = RequestedChange(
        summary="Update VLAN intent",
        intent="Ensure VLAN 220 exists",
        desired_state={
            "operations": [
                {
                    "object_type": "vlan",
                    "operation": "ensure_present",
                    "attributes": {"vlan_id": 220, "name": "Engineering"},
                }
            ]
        },
    )
    assert requested.desired_state.__class__.__name__ == "VlanDesiredState"


def test_finding_severity_is_constrained():
    with pytest.raises(ValidationError):
        Finding(code="X", severity="urgent", message="bad")
