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

    intent = change_request.requested_change.intent.lower()
    desired_state = change_request.requested_change.desired_state

    if "access" in intent and "trunk" not in intent:
        intent_type: str = "set_access_vlan"
        mode: str = "access"
    elif "trunk" in intent or "provision_vlan_trunk" in intent:
        intent_type = "provision_vlan_trunk"
        mode = "trunk"
    else:
        intent_type = "set_access_vlan"
        mode = "access"

    render_input = VlanRenderInput(
        intent_type=intent_type,
        vlans_to_create=plan_decision.diff.vlans_to_create,
        ports_to_update=plan_decision.diff.ports_to_update,
        target_device=primary_device,
        vlan_name=desired_state.get("vlans", [{}])[0].get("name") if desired_state.get("vlans") else None,
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