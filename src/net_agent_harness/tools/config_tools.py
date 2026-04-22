from ..models.artifacts import ConfigRender, ConfigSnippet
from ..models.changes import ChangeRequest
from ..models.common import ArtifactMeta


def build_stub_config_render(change_request: ChangeRequest) -> ConfigRender:
    device_names = change_request.scope.device_names or ["unknown-device"]
    primary_device = device_names[0]
    intent = change_request.requested_change.intent.lower()

    commands = [f"! Candidate config for {primary_device}"]
    warnings = []

    if "vlan" in intent:
        vlan_id = "220"
        for token in intent.replace(",", " ").split():
            if token.isdigit():
                vlan_id = token
                break
        commands.extend([
            f"vlan {vlan_id}",
            f" name VLAN_{vlan_id}",
        ])
    else:
        commands.append("! No template matched the request; manual review required")
        warnings.append("No specific rendering template matched the request intent.")

    snippet = ConfigSnippet(
        device_name=primary_device,
        path_hint=f"devices/{primary_device}/candidate.cfg",
        commands=commands,
        rendered_text="\n".join(commands),
    )

    return ConfigRender(
        meta=ArtifactMeta(
            run_id=change_request.meta.run_id,
            artifact_id="config-render-001",
            created_by="build_stub_config_render",
        ),
        summary=f"Candidate config render for {primary_device}",
        snippets=[snippet],
        warnings=warnings,
    )
