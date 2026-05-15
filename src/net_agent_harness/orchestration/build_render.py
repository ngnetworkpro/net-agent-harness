from ..models.changes import ChangeRequest
from ..models.domain import NetworkDomain
from ..models.artifacts import RenderRequest, VlanRenderPayload, VlanRenderOp, VlanInterfaceRenderOp, OperationType, RenderTarget

def build_render_input(change_request: ChangeRequest):
    if change_request.domain == NetworkDomain.VLAN:
        return build_vlan_render_input(change_request)
    if change_request.domain == NetworkDomain.ROUTING:
        return build_routing_render_input(change_request)
    raise ValueError(f"No render input builder for domain {change_request.domain}")

def build_vlan_render_input(change_request: ChangeRequest):
    """Build VLAN render input from change request."""
    if change_request.plan_decision is None:
        raise ValueError("plan_decision is required to build render input.")
    if change_request.plan_decision.decision.value != "apply":
        raise ValueError(
            f"Render rejected: plan decision is '{change_request.plan_decision.decision.value}', expected 'apply'."
        )

    vlan_ops = []
    interface_ops = []
    for change in change_request.plan_decision.diff:
        if change.changes.vlans_to_remove:
            raise ValueError(
                f"Render rejected: VLAN removal is not supported for device '{change.device}'."
            )
        if change.changes.vlans_to_create:
            for vlan_spec in change.changes.vlans_to_create:
                vlan_ops.append(
                    VlanRenderOp(
                        vlan_id=vlan_spec.id,
                        vlan_name=vlan_spec.name if vlan_spec.name else None,
                        operation=OperationType.ENSURE_PRESENT,
                        target=RenderTarget(name=change.device)
                    )
                )

        for port_spec in change.changes.ports_to_update:
            interface_ops.append(
                VlanInterfaceRenderOp(
                    interface_name=port_spec.interface,
                    target=RenderTarget(name=change.device),
                    access_vlan=port_spec.vlan_id if port_spec.mode == "access" else None,
                    switchport_mode=port_spec.mode,
                )
            )
    

    return RenderRequest(
        domain=change_request.domain,
        intent_type=change_request.requested_change.intent,
        payload=VlanRenderPayload(
            vlan_ops=vlan_ops,
            interface_ops=interface_ops,
        ),
    )

def build_routing_render_input(change_request: ChangeRequest):
    """Build routing render input from change request."""
    # TODO: Build routing render input
    raise NotImplementedError("Routing render input not yet implemented")
