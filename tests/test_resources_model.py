from net_agent_harness.models.changes import ChangeRequest, RequestedChange, RollbackPlan
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk, NetworkDomain
from net_agent_harness.models.resources import (
    DeviceResourceRef,
    DeviceToTopologyLinkRelationship,
    InterfaceResourceRef,
    InterfaceToSubnetRelationship,
    SiteResourceRef,
    SiteToDeviceRelationship,
    SubnetResourceRef,
    TopologyLinkResourceRef,
    VlanResourceRef,
)


def test_change_request_accepts_typed_target_resources_and_relationships() -> None:
    site = SiteResourceRef(site_name="HQ")
    device = DeviceResourceRef(device_name="sw1", site_name="HQ")
    interface = InterfaceResourceRef(device_name="sw1", interface_name="ge-0/0/1", site_name="HQ")
    subnet = SubnetResourceRef(cidr="10.10.20.0/24", site_name="HQ")
    topology_link = TopologyLinkResourceRef(
        endpoint_a_device="sw1",
        endpoint_a_interface="ge-0/0/1",
        endpoint_b_device="sw2",
        endpoint_b_interface="ge-0/0/48",
        site_name="HQ",
    )

    model = ChangeRequest(
        meta=ArtifactMeta(run_id="run-1", artifact_id="change-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(site="HQ", device_names=["sw1"]),
        target_scope="device",
        requested_change=RequestedChange(
            summary="Add VLAN 220",
            intent="Add VLAN 220 to sw1",
        ),
        rollback_plan=RollbackPlan(summary="Revert"),
        risk=ChangeRisk.LOW,
        target_resources=[site, device, interface, VlanResourceRef(vlan_id=220, site_name="HQ")],
        resource_relationships=[
            SiteToDeviceRelationship(site=site, device=device),
            InterfaceToSubnetRelationship(interface=interface, subnet=subnet),
            DeviceToTopologyLinkRelationship(device=device, topology_link=topology_link),
        ],
    )

    assert len(model.target_resources) == 4
    assert len(model.resource_relationships) == 3
    assert model.target_resources[0].resource_type == "site"
