from net_agent_harness.adapters.backends.base import BackendAdapter
from net_agent_harness.models.artifacts import ConfigRender, ExecutionResult
from net_agent_harness.models.changes import ChangeRequest


class DirectAPIBackendAdapter(BackendAdapter):
    async def render(self, change_request: ChangeRequest) -> ConfigRender:
        if not change_request.plan_decision or change_request.plan_decision.decision.value != "apply":
            reason = getattr(change_request.plan_decision, "decision", "None")
            if hasattr(reason, "value"):
                reason = reason.value
            return ConfigRender(
                meta=self._make_meta(change_request, "direct-api-backend"),
                summary=f"No changes required: decision is '{reason}'.",
            )

        additions_by_device: dict[str, dict[str, str]] = {}
        ports_by_device: dict[str, list] = {}
        
        for device_change in change_request.plan_decision.diff:
            device = device_change.device
            device_additions = additions_by_device.setdefault(device, {})
            for vlan in device_change.changes.vlans_to_create:
                device_additions[vlan.name] = str(vlan.id)
            if device_change.changes.ports_to_update:
                ports_by_device[device] = device_change.changes.ports_to_update

        vendor_by_device = {}
        platform_by_device = {}
        for target in change_request.resolved_targets:
            if target.vendor:
                vendor_by_device[target.name] = target.vendor
            platform_by_device[target.name] = target.platform

        snippets = []
        from net_agent_harness.adapters.backends.api_operations import build_api_primary_snippet
        from net_agent_harness.adapters.backends.cli_snippets import build_cli_fallback_snippet

        for device_name, additions in additions_by_device.items():
            if not additions and not ports_by_device.get(device_name):
                continue
            
            device_vendor = vendor_by_device.get(device_name)
            device_platform = platform_by_device.get(device_name)
            port_changes = ports_by_device.get(device_name, [])

            primary_snippet = build_api_primary_snippet(
                device_name=device_name,
                vendor=device_vendor,
                vlan_additions=additions,
                port_changes=port_changes,
                platform=device_platform,
            )
            snippets.append(primary_snippet)

            cli_fallback = build_cli_fallback_snippet(
                device_name=device_name,
                vendor=device_vendor,
                vlan_additions=additions,
                port_changes=port_changes,
                platform=device_platform,
            )
            snippets.append(cli_fallback)

        if not snippets:
            return ConfigRender(
                meta=self._make_meta(change_request, "direct-api-backend"),
                summary="No operations detected in plan decision.",
                warnings=["plan_decision contains no vlans_to_create or ports_to_update entries"],
            )

        return ConfigRender(
            meta=self._make_meta(change_request, "direct-api-backend"),
            summary=f"Direct API: Rendered operations for {len(snippets)//2} device(s)",
            snippets=snippets,
        )

    async def apply(self, config_render: ConfigRender) -> ExecutionResult:
        import httpx
        from uuid import uuid4
        from datetime import datetime, timezone
        from net_agent_harness.models.enums import RenderBackendType, RenderRole
        from net_agent_harness.models.artifacts import ExecutionResult, ArtifactMeta

        results = []
        errors = []

        async with httpx.AsyncClient() as client:
            for snippet in config_render.snippets:
                if snippet.backend_type != RenderBackendType.API or snippet.render_role != RenderRole.PRIMARY:
                    continue
                
                payload = snippet.api_payload
                if not payload:
                    continue

                device_name = snippet.device_name
                action = f"{payload.method} {payload.path}"

                try:
                    url = f"https://api.example.com{payload.path}"
                    response = await client.request(
                        payload.method,
                        url,
                        json=payload.body,
                        params=payload.query,
                    )
                    response.raise_for_status()
                    results.append(f"Success for {device_name} - {action}")
                except Exception as e:
                    errors.append(f"Error on {device_name} - {action}: {type(e).__name__}({e})")

        status = "failed" if errors else "success"
        if errors:
            detail = f"Completed with {len(errors)} errors: " + "; ".join(errors)
        elif not results and not errors:
            detail = "No primary API snippets to execute."
        else:
            detail = f"Successfully executed API operations for {len(results)} actions."

        return ExecutionResult(
            meta=ArtifactMeta(
                run_id=config_render.meta.run_id,
                artifact_id=str(uuid4()),
                version=1,
                created_at=datetime.now(timezone.utc),
                created_by="direct-api-backend",
            ),
            backend="direct-api",
            status=status,
            detail=detail,
            reference="none",
        )
