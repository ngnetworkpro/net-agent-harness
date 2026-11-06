from pydantic import ValidationError

from ..models.artifacts import (
    OperationType,
    RenderRequest,
    RenderTarget,
    RoutingRenderPayload,
    StaticRouteOp,
    SviRenderOp,
    VlanInterfaceRenderOp,
    VlanRenderOp,
    VlanRenderPayload,
)
from ..models.changes import ChangeRequest
from ..models.domain import NetworkDomain
from ..models.enums import AllowedVlansMode, SwitchportMode


def build_render_input(change_request: ChangeRequest) -> RenderRequest:
    if change_request is None:
        raise ValueError("change_request is required to build render input.")
    if change_request.domain == NetworkDomain.VLAN:
        return build_vlan_render_input(change_request)
    if change_request.domain == NetworkDomain.ROUTING:
        return build_routing_render_input(change_request)
    raise ValueError(f"No render input builder for domain {change_request.domain}")


def build_vlan_render_input(change_request: ChangeRequest) -> RenderRequest:
    """Build VLAN render input from change request."""
    if change_request.plan_decision is None:
        raise ValueError("Render rejected: plan_decision is required to build render input.")
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
                        vlan_name=vlan_spec.name if vlan_spec.name else str(vlan_spec.id),
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
    if change_request is None:
        raise ValueError("Render rejected: change_request is required to build render input.")

    if change_request.plan_decision is None:
        raise ValueError("Render rejected: plan_decision is required to build render input.")

    decision_val = getattr(
        change_request.plan_decision.decision,
        "value",
        str(change_request.plan_decision.decision),
    ).lower()
    if decision_val != "apply":
        raise ValueError(
            f"Render rejected: plan decision is '{decision_val}', expected 'apply'."
        )

    target_by_name = {
        target.name: target for target in (change_request.resolved_targets or [])
    }

    def _resolve_render_target(device_name: str | None) -> RenderTarget:
        if not device_name:
            raise ValueError("Render rejected: device name is missing or empty.")
        target = target_by_name.get(device_name)
        if target is None:
            raise ValueError(
                f"Render rejected: device '{device_name}' is not present in resolved_targets."
            )
        if not target.platform or not target.platform.strip():
            raise ValueError(
                f"Render rejected: device '{device_name}' is missing platform in resolved_targets."
            )
        return RenderTarget(
            name=target.name,
            site=target.site,
            role=target.role,
            platform=target.platform,
            primary_ip=target.primary_ip,
        )

    for change in (change_request.plan_decision.diff or []):
        _resolve_render_target(change.device)

    route_ops: list[StaticRouteOp] = []

    if change_request.routing_payload and getattr(change_request.routing_payload, "route_ops", None):
        for op in change_request.routing_payload.route_ops:
            op_status = getattr(op, "status", "apply")
            if str(op_status).lower() != "apply":
                raise ValueError(
                    f"Render rejected: route operation for prefix '{getattr(op, 'prefix', 'unknown')}' has non-apply status '{op_status}'."
                )
            target_name = getattr(op.target, "name", None) if getattr(op, "target", None) else None
            if not target_name:
                raise ValueError(
                    f"Render rejected: route operation for prefix '{getattr(op, 'prefix', 'unknown')}' is missing target device name."
                )
            render_target = _resolve_render_target(target_name)
            route_ops.append(
                StaticRouteOp(
                    prefix=op.prefix,
                    next_hop=op.next_hop,
                    operation=op.operation,
                    target=render_target,
                    description=getattr(op, "description", None),
                    admin_distance=getattr(op, "admin_distance", None),
                )
            )
    elif change_request.plan_decision.diff:
        for change in change_request.plan_decision.diff:
            render_target = _resolve_render_target(change.device)
            raw_ops: list[object] = []
            if isinstance(change.changes, list):
                raw_ops = change.changes
            elif hasattr(change.changes, "route_ops") and change.changes.route_ops is not None:
                raw_ops = change.changes.route_ops
            elif isinstance(change.changes, dict):
                if "route_ops" in change.changes and isinstance(change.changes["route_ops"], list):
                    raw_ops = change.changes["route_ops"]
                elif "prefix" in change.changes and "next_hop" in change.changes:
                    raw_ops = [change.changes]
            elif isinstance(change.changes, StaticRouteOp):
                raw_ops = [change.changes]

            for diff_op in raw_ops:
                raw_status = (
                    getattr(diff_op, "status", None)
                    if not isinstance(diff_op, dict)
                    else diff_op.get("status")
                )
                if raw_status is not None and str(raw_status).lower() != "apply":
                    prefix_hint = (
                        getattr(diff_op, "prefix", None)
                        if not isinstance(diff_op, dict)
                        else diff_op.get("prefix", "unknown")
                    )
                    raise ValueError(
                        f"Render rejected: route operation for prefix '{prefix_hint}' has non-apply status '{raw_status}'."
                    )
                if isinstance(diff_op, StaticRouteOp):
                    route_ops.append(
                        StaticRouteOp(
                            prefix=diff_op.prefix,
                            next_hop=diff_op.next_hop,
                            operation=diff_op.operation,
                            target=render_target,
                            description=diff_op.description,
                            admin_distance=diff_op.admin_distance,
                        )
                    )
                elif isinstance(diff_op, dict):
                    try:
                        route_ops.append(
                            StaticRouteOp.model_validate({**diff_op, "target": render_target})
                        )
                    except ValidationError as err:
                        raise ValueError(
                            f"Render rejected: invalid static route operation in diff for device '{change.device}': {err}"
                        ) from err

    # Deterministic sorting
    route_ops.sort(
        key=lambda ro: (
            getattr(ro.target, "name", "") or "",
            ro.prefix,
            ro.next_hop,
            getattr(ro.operation, "value", str(ro.operation)),
            ro.admin_distance or 0,
        )
    )

    intent_type = (
        change_request.requested_change.intent
        if change_request.requested_change and hasattr(change_request.requested_change, "intent")
        else ""
    )

    return RenderRequest(
        domain=NetworkDomain.ROUTING,
        intent_type=intent_type,
        payload=RoutingRenderPayload(
            route_ops=route_ops,
        ),
    )
