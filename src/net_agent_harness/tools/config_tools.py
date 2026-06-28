from ..agents.config_render_agent import change_render_agent
from ..models.artifacts import ConfigRender, ConfigRenderOutput
from ..models.changes import ChangeRequest
from ..models.common import ArtifactMeta
from ..orchestration.build_render import build_render_input


async def render_vlan_config(change_request: ChangeRequest) -> ConfigRender:
    plan_decision = change_request.plan_decision
    if plan_decision is None:
        raise ValueError("plan_decision is required for rendering")

    render_input = build_render_input(change_request)

    result = await change_render_agent.run(
        "Render the configuration.",
        deps=render_input,
    )

    render_result: ConfigRenderOutput = result.output

    return ConfigRender(
        meta=ArtifactMeta(
            run_id=change_request.meta.run_id,
            artifact_id="config-render-001",
            created_by="config_render_agent",
        ),
        summary=render_result.summary,
        snippets=render_result.snippets,
        warnings=render_result.warnings,
    )