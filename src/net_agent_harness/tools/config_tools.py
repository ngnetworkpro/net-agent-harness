from ..agents.config_render_agent import change_render_agent
from ..models.artifacts import ConfigRender, VlanRenderInput
from ..models.changes import ChangeRequest
from ..models.common import ArtifactMeta


async def render_vlan_config(change_request: ChangeRequest) -> ConfigRender:
    plan_decision = change_request.plan_decision
    if plan_decision is None:
        raise ValueError("plan_decision is required for rendering")

    device_names = change_request.scope.device_names or ["unknown-device"]
    primary_device = device_names[0]

    intent_type = "set_access_vlan"
    mode = "access"

    device_diff = plan_decision.diff[0].changes if plan_decision.diff else None

    if device_diff and device_diff.ports_to_update:
        first_port = device_diff.ports_to_update[0]
        if first_port.mode == "trunk":
            intent_type = "provision_vlan_trunk"
            mode = "trunk"

    vlan_name = None
    if device_diff and device_diff.vlans_to_create:
        vlan_name = device_diff.vlans_to_create[0].name

    render_input = VlanRenderInput(
        intent_type=intent_type,
        vlans_to_create=device_diff.vlans_to_create if device_diff else [],
        ports_to_update=device_diff.ports_to_update if device_diff else [],
        target_device=primary_device,
        vlan_name=vlan_name,
        mode=mode,
    )

    result = await change_render_agent.run(
        prompt="",
        deps=render_input,
    )

    config_render = result.output
    config_render.meta = ArtifactMeta(
        run_id=change_request.meta.run_id,
        artifact_id="config-render-001",
        created_by="config_render_agent",
    )

    return config_render