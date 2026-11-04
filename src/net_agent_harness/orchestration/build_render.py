from ..models.artifacts import (
    OperationType,
    RenderRequest,
    RenderTarget,
    SviRenderOp,
    VlanInterfaceRenderOp,
    VlanRenderOp,
    VlanRenderPayload,
)
from ..models.changes import ChangeRequest
from ..models.domain import NetworkDomain
from ..models.enums import AllowedVlansMode, SwitchportMode


def build_render_input(change_request: ChangeRequest) -> RenderRequest:
    if change_request.domain == NetworkDomain.VLAN:
        return build_vlan_render_input(change_request)
    if change_request.domain == NetworkDomain.ROUTING:
        return build_routing_render_input(change_request)
    raise ValueError(f"No render input builder for domain {change_request.domain}")


def build_vlan_render_input(change_request: ChangeRequest) -> RenderRequest:
    """Build VLAN render input from change request."""
    if change_request.plan_decision is None:
        raise ValueError("plan_decision is required to build render input.")
    if change_request.plan_decision.decision.value != "apply":
        raise ValueError(
            f"Render rejected: plan decision is '{change_request.plan_decision.decision.value}', expected 'apply'."
        )

    target_by_name = {target.name: target for target in change_request.resolved_targets}
    vlan_ops: list[VlanRenderOp] = []
    interface_ops: list[VlanInterfaceRenderOp] = []
    svi_ops: list[SviRenderOp] = []
    for change in change_request.plan_decision.diff:
        target = target_by_name.get(change.device)
        if target is None:
            raise ValueError(
                f"Render rejected: device '{change.device}' is not present in resolved_targets."
            )
        if not target.platform:
            raise ValueError(
                f"Render rejected: device '{change.device}' is missing platform in resolved_targets."
            )
        render_target = RenderTarget(
            name=change.device,
            site=target.site,
            role=target.role,
            platform=target.platform,
            primary_ip=target.primary_ip,
        )
        if change.changes.vlans_to_create:
            for vlan_spec in change.changes.vlans_to_create:
                vlan_ops.append(
                    VlanRenderOp(
                        vlan_id=vlan_spec.id,
                        vlan_name=vlan_spec.name if vlan_spec.name else None,
                        operation=OperationType.ENSURE_PRESENT,
                        target=render_target,
                    )
                )
        if change.changes.vlans_to_remove:
            for vlan_spec in change.changes.vlans_to_remove:
                vlan_ops.append(
                    VlanRenderOp(
                        vlan_id=vlan_spec.id,
                        vlan_name=vlan_spec.name if vlan_spec.name else None,
                        operation=OperationType.REMOVE,
                        target=render_target,
                    )
                )

        for port_spec in change.changes.ports_to_update:
            allowed_vlans = list(getattr(port_spec, "allowed_vlans", []) or [])
            explicit_mode = getattr(port_spec, "allowed_vlans_mode", None)
            if explicit_mode is not None:
                allowed_vlans_mode = explicit_mode
            elif port_spec.mode == SwitchportMode.TRUNK:
                allowed_vlans_mode = (
                    AllowedVlansMode.LIST if allowed_vlans else AllowedVlansMode.ALL
                )
            else:
                allowed_vlans_mode = None

            interface_ops.append(
                VlanInterfaceRenderOp(
                    interface_name=port_spec.interface,
                    target=render_target,
                    access_vlan=(
                        port_spec.vlan_id
                        if port_spec.mode == SwitchportMode.ACCESS
                        else None
                    ),
                    switchport_mode=port_spec.mode,
                    native_vlan=getattr(port_spec, "native_vlan", None),
                    allowed_vlans=allowed_vlans,
                    allowed_vlans_mode=allowed_vlans_mode,
                )
            )

        for op in getattr(change.changes, "operations", []):
            if getattr(op, "change_type", None) == "svi" and getattr(op, "status", None) == "apply":
                svi_op_type = (
                    OperationType.REMOVE
                    if getattr(op, "op", None) == "remove"
                    else OperationType.ENSURE_PRESENT
                )
                svi_ops.append(
                    SviRenderOp(
                        target=render_target,
                        vlan_id=op.vlan_id,
                        operation=svi_op_type,
                        interface_name=getattr(op, "interface_name", None)
                        or getattr(op, "interface", None),
                        ip_address=getattr(op, "ip_address", None),
                        prefix_length=getattr(op, "prefix_length", None),
                    )
                )

    return RenderRequest(
        domain=change_request.domain,
        intent_type=change_request.requested_change.intent,
        payload=VlanRenderPayload(
            vlan_ops=vlan_ops,
            interface_ops=interface_ops,
            svi_ops=svi_ops,
        ),
    )


def build_routing_render_input(change_request: ChangeRequest) -> RenderRequest:
    """Build routing render input from change request."""
    # TODO: Build routing render input
    raise NotImplementedError("Routing render input not yet implemented")
