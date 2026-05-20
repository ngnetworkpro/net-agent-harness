from net_agent_harness.adapters.inventory_adapter import (
    GuardedInventoryWriteAdapter,
    InventoryWriteRequest,
)
from net_agent_harness.adapters.ipam_adapter import GuardedIPAMWriteAdapter, IPAMWriteRequest
from net_agent_harness.adapters.topology_adapter import (
    GuardedTopologyWriteAdapter,
    TopologyWriteRequest,
)
from net_agent_harness.config import Settings
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import PlanDecisionType
from net_agent_harness.models.inventory import InventorySnapshot
from net_agent_harness.models.ipam import IpamSnapshot
from net_agent_harness.models.topology import TopologyDelta, TopologyState, TopologyUpdatePlan
from net_agent_harness.policies.approvals import (
    PolicyDenied,
    WriteApprovalContext,
    WriteCapability,
    assert_write_allowed,
)
import pytest


def _settings(**updates: bool) -> Settings:
    return Settings(**updates)


def _artifact_meta(artifact_id: str) -> ArtifactMeta:
    return ArtifactMeta(
        run_id="run-001",
        artifact_id=artifact_id,
        created_by="pytest",
    )


def _inventory_request() -> InventoryWriteRequest:
    return InventoryWriteRequest(
        summary="Write inventory snapshot",
        snapshot=InventorySnapshot(meta=_artifact_meta("inventory-snapshot-001")),
    )


def _ipam_request() -> IPAMWriteRequest:
    return IPAMWriteRequest(
        summary="Write IPAM snapshot",
        snapshot=IpamSnapshot(meta=_artifact_meta("ipam-snapshot-001")),
    )


def _topology_request() -> TopologyWriteRequest:
    return TopologyWriteRequest(
        summary="Apply topology update",
        plan=TopologyUpdatePlan(
            meta=_artifact_meta("topology-plan-001"),
            scope=ScopeRef(site="HQ"),
            summary="Add a new access uplink",
            current_state=TopologyState(devices=["sw1"]),
            desired_state=TopologyState(devices=["sw1", "sw2"]),
            delta=TopologyDelta(devices_added=["sw2"]),
            decision=PlanDecisionType.APPLY,
        ),
    )


def _approved_context(capability: WriteCapability) -> WriteApprovalContext:
    return WriteApprovalContext(
        approved_artifact_id="validation-report-001",
        evidence=["change_request:change-request-001", "validation_report:validation-report-001"],
        capability_grants=[capability],
    )


def test_write_gate_denies_when_capability_is_disabled() -> None:
    with pytest.raises(PolicyDenied, match="disabled by configuration"):
        assert_write_allowed(
            WriteCapability.IPAM,
            _approved_context(WriteCapability.IPAM),
            s=_settings(enable_ipam_writes=False),
        )


def test_write_gate_denies_without_approved_artifact() -> None:
    approval = WriteApprovalContext(
        approved_artifact_id=None,
        evidence=["validation_report:validation-report-001"],
        capability_grants=[WriteCapability.INVENTORY],
    )

    with pytest.raises(PolicyDenied, match="approved artifact"):
        assert_write_allowed(
            WriteCapability.INVENTORY,
            approval,
            s=_settings(enable_inventory_writes=True),
        )


def test_write_gate_denies_without_capability_grant() -> None:
    approval = WriteApprovalContext(
        approved_artifact_id="validation-report-001",
        evidence=["validation_report:validation-report-001"],
        capability_grants=[],
    )

    with pytest.raises(PolicyDenied, match="explicit capability grant"):
        assert_write_allowed(
            WriteCapability.TOPOLOGY,
            approval,
            s=_settings(enable_topology_writes=True),
        )


def test_write_gate_denies_without_evidence() -> None:
    approval = WriteApprovalContext(
        approved_artifact_id="validation-report-001",
        evidence=[],
        capability_grants=[WriteCapability.IPAM],
    )

    with pytest.raises(PolicyDenied, match="evidence"):
        assert_write_allowed(
            WriteCapability.IPAM,
            approval,
            s=_settings(enable_ipam_writes=True),
        )


def test_inventory_write_stub_remains_unimplemented_after_approval() -> None:
    adapter = GuardedInventoryWriteAdapter()
    request = _inventory_request()

    with pytest.raises(NotImplementedError, match="inventory_write"):
        adapter.write_inventory_snapshot(
            request,
            approval=_approved_context(WriteCapability.INVENTORY),
            s=_settings(enable_inventory_writes=True),
        )


def test_ipam_write_stub_remains_unimplemented_after_approval() -> None:
    adapter = GuardedIPAMWriteAdapter()
    request = _ipam_request()

    with pytest.raises(NotImplementedError, match="ipam_write"):
        adapter.write_ipam_snapshot(
            request,
            approval=_approved_context(WriteCapability.IPAM),
            s=_settings(enable_ipam_writes=True),
        )


def test_topology_write_stub_remains_unimplemented_after_approval() -> None:
    adapter = GuardedTopologyWriteAdapter()
    request = _topology_request()

    with pytest.raises(NotImplementedError, match="topology_write"):
        adapter.apply_topology_update(
            request,
            approval=_approved_context(WriteCapability.TOPOLOGY),
            s=_settings(enable_topology_writes=True),
        )
