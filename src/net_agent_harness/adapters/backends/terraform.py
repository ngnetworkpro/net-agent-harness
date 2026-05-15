import json
import base64
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from textwrap import indent
from typing import Any
from uuid import uuid4

import httpx

from net_agent_harness.adapters.backends.base import BackendAdapter
from net_agent_harness.adapters.backends.cli_snippets import build_cli_fallback_snippet
from net_agent_harness.config import settings
from net_agent_harness.models.artifacts import ArtifactMeta, ConfigRender, ConfigSnippet, ExecutionResult
from net_agent_harness.models.changes import ChangeRequest
from net_agent_harness.models.enums import DeviceVendor, RenderBackendType, RenderRole


class TerraformBackendAdapter(BackendAdapter):

    async def render(self, change_request: ChangeRequest) -> ConfigRender:
        current, source_label = await self._load_terraform_source()

        # Collect VLANs to add from plan_decision diff, grouped per device
        additions_by_device: dict[str, dict[str, str]] = {}
        if change_request.plan_decision:
            if change_request.plan_decision.decision.value != "apply":
                return ConfigRender(
                    meta=self._make_meta(change_request),
                    summary=f"No changes required: decision is '{change_request.plan_decision.decision.value}'.",
                )
            for device_change in change_request.plan_decision.diff:
                device_additions = additions_by_device.setdefault(device_change.device, {})
                for vlan in device_change.changes.vlans_to_create:
                    device_additions[vlan.name] = str(vlan.id)

        if not any(additions_by_device.values()):
            return ConfigRender(
                meta=self._make_meta(change_request),
                summary="No VLAN additions detected in plan decision.",
                warnings=["plan_decision contains no vlans_to_create entries"],
            )

        snippets: list[ConfigSnippet] = []

        # Build lookup maps from plan diff and resolved targets
        ports_by_device: dict[str, list] = {}
        if change_request.plan_decision:
            for device_change in change_request.plan_decision.diff:
                if device_change.changes.ports_to_update:
                    ports_by_device[device_change.device] = device_change.changes.ports_to_update

        vendor_by_device: dict[str, DeviceVendor] = {}
        platform_by_device: dict[str, str | None] = {}
        for target in change_request.resolved_targets:
            if target.vendor:
                vendor_by_device[target.name] = target.vendor
            platform_by_device[target.name] = target.platform

        for device_name, additions in additions_by_device.items():
            if not additions:
                continue

            merged_networks = dict(current)
            merged_networks.update({name: {"vlan_id": vlan_id} for name, vlan_id in additions.items()})
            rendered_text = self._render_primary_terraform_snippet(
                source_label=source_label,
                device_name=device_name,
                networks=merged_networks,
            )

            commands = [
                json.dumps({"name": name, "vlan_id": vlan_id})
                for name, vlan_id in additions.items()
            ]

            snippets.append(
                ConfigSnippet(
                    device_name=device_name,
                    backend_type=RenderBackendType.TERRAFORM,
                    render_role=RenderRole.PRIMARY,
                    path_hint=source_label,
                    commands=commands,
                    rendered_text=rendered_text,
                )
            )

            # Generate a vendor-aware CLI fallback from the plan diff
            device_vendor = vendor_by_device.get(device_name, DeviceVendor.OTHER)
            device_platform = platform_by_device.get(device_name)
            cli_fallback = build_cli_fallback_snippet(
                device_name=device_name,
                vendor=device_vendor,
                vlan_additions=additions,
                port_changes=ports_by_device.get(device_name, []),
                platform=device_platform,
            )
            snippets.append(cli_fallback)

        return ConfigRender(
            meta=self._make_meta(change_request),
            summary=f"Terraform: source-backed render from {source_label} for {len(additions_by_device)} device(s)",
            snippets=snippets,
        )

    async def apply(self, config_render: ConfigRender) -> ExecutionResult:
        if not settings.terraform_networks_file:
            raise ValueError("NET_AGENT_TERRAFORM_NETWORKS_FILE is not set")
        if not settings.github_repo:
            raise ValueError("NET_AGENT_GITHUB_REPO is not set")
        if not settings.github_token:
            raise ValueError("NET_AGENT_GITHUB_TOKEN is not set")

        repo_root = self._find_repo_root()
        networks_path = self._resolve_repo_bounded_path(
            repo_root,
            settings.terraform_networks_file,
            setting_name="NET_AGENT_TERRAFORM_NETWORKS_FILE",
        )
        current = json.loads(networks_path.read_text())

        # Parse additions from snippet commands
        for snippet in config_render.snippets:
            for cmd in snippet.commands:
                entry = self._parse_vlan_command_entry(cmd, snippet.device_name)
                current[entry["name"]] = {"vlan_id": entry["vlan_id"]}

        updated_content = json.dumps(current, indent=2) + "\n"
        networks_path.write_text(updated_content)

        run_id = config_render.meta.run_id
        branch_name = f"agent/vlan-update-{run_id[:8]}"
        pr_url = await self._create_github_pr(updated_content, branch_name)

        return ExecutionResult(
            meta=ArtifactMeta(
                run_id=run_id,
                artifact_id=str(uuid4()),
                version=1,
                created_at=datetime.now(timezone.utc),
                created_by="terraform-backend",
            ),
            backend="terraform",
            status="pending_pr",
            detail=f"networks.json updated locally and PR opened: {pr_url}",
            reference=pr_url,
        )

    async def _create_github_pr(self, updated_content: str, branch_name: str) -> str:
        token = settings.github_token.get_secret_value()
        repo = settings.github_repo
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient(headers=headers, base_url="https://api.github.com") as client:
            # Get base branch SHA
            ref_resp = await client.get(f"/repos/{repo}/git/ref/heads/{settings.github_base_branch}")
            if ref_resp.status_code != 200:
                raise RuntimeError(f"GitHub API error fetching base branch: HTTP {ref_resp.status_code}")
            base_sha = ref_resp.json()["object"]["sha"]

            # Create new branch
            branch_resp = await client.post(f"/repos/{repo}/git/refs", json={
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha,
            })
            if branch_resp.status_code not in (201, 422):  # 422 = branch already exists
                raise RuntimeError(f"GitHub API error creating branch: HTTP {branch_resp.status_code}")

            # Get current file SHA
            file_resp = await client.get(f"/repos/{repo}/contents/networks.json", params={"ref": branch_name})
            file_sha = file_resp.json().get("sha") if file_resp.status_code == 200 else None

            # Update file
            payload: dict = {
                "message": "feat: update networks.json via net-agent",
                "content": base64.b64encode(updated_content.encode()).decode(),
                "branch": branch_name,
            }
            if file_sha:
                payload["sha"] = file_sha
            put_resp = await client.put(f"/repos/{repo}/contents/networks.json", json=payload)
            if put_resp.status_code not in (200, 201):
                raise RuntimeError(f"GitHub API error updating file: HTTP {put_resp.status_code}")

            # Create PR
            pr_resp = await client.post(f"/repos/{repo}/pulls", json={
                "title": "feat: add VLANs via net-agent",
                "head": branch_name,
                "base": settings.github_base_branch,
                "body": "Automated VLAN update generated by net-agent-harness.",
            })
            if pr_resp.status_code == 422:
                # PR likely already exists, try to find it
                pulls_resp = await client.get(f"/repos/{repo}/pulls", params={"head": f"{settings.github_repo.split('/')[0]}:{branch_name}"})
                if pulls_resp.status_code == 200 and pulls_resp.json():
                    return pulls_resp.json()[0]["html_url"]
                raise RuntimeError(f"GitHub API error creating PR: HTTP {pr_resp.status_code} (validation failed or PR exists but not found)")
            elif pr_resp.status_code != 201:
                raise RuntimeError(f"GitHub API error creating PR: HTTP {pr_resp.status_code}")

            return pr_resp.json()["html_url"]

    async def _load_terraform_source(self) -> tuple[dict, str]:
        source_mode = settings.terraform_render_source.strip().lower()
        if source_mode not in {"auto", "local", "github"}:
            raise ValueError(
                "NET_AGENT_TERRAFORM_RENDER_SOURCE must be one of: auto, local, github"
            )

        if source_mode in {"auto", "local"}:
            try:
                return self._load_local_terraform_source()
            except FileNotFoundError:
                if source_mode == "local":
                    raise

        return await self._load_github_terraform_source()

    def _load_local_terraform_source(self) -> tuple[dict, str]:
        source_dir = Path(settings.terraform_source_dir)
        if not source_dir.is_absolute():
            repo_root = self._find_repo_root()
            source_dir = repo_root / source_dir
        source_dir = source_dir.resolve()
        networks_path = self._resolve_repo_bounded_path(
            source_dir,
            settings.terraform_source_networks_file,
            setting_name="NET_AGENT_TERRAFORM_SOURCE_NETWORKS_FILE",
        )
        template_path = self._resolve_repo_bounded_path(
            source_dir,
            settings.terraform_source_template_file,
            setting_name="NET_AGENT_TERRAFORM_SOURCE_TEMPLATE_FILE",
        )

        if not networks_path.exists():
            raise FileNotFoundError(f"Local Terraform source file not found: {networks_path}")
        if not template_path.exists():
            raise FileNotFoundError(f"Local Terraform source file not found: {template_path}")

        self._validate_terraform_template_text(template_path.read_text(), f"local:{template_path}")
        current = json.loads(networks_path.read_text())
        return current, f"local:{networks_path}"

    async def _load_github_terraform_source(self) -> tuple[dict, str]:
        if not settings.github_repo:
            raise ValueError("NET_AGENT_GITHUB_REPO is not set")
        if not settings.github_token:
            raise ValueError("NET_AGENT_GITHUB_TOKEN is not set")

        source_dir = settings.terraform_source_dir.strip("/")
        networks_path = f"{source_dir}/{settings.terraform_source_networks_file}"
        template_path = f"{source_dir}/{settings.terraform_source_template_file}"

        networks_content = await self._fetch_github_file(networks_path)
        template_content = await self._fetch_github_file(template_path)
        self._validate_terraform_template_text(
            template_content,
            f"github:{settings.github_repo}:{template_path}",
        )
        current = json.loads(networks_content)
        return current, f"github:{settings.github_repo}:{networks_path}"

    async def _fetch_github_file(self, file_path: str) -> str:
        if not settings.github_token:
            raise ValueError("NET_AGENT_GITHUB_TOKEN is not set")
        if not settings.github_repo:
            raise ValueError("NET_AGENT_GITHUB_REPO is not set")

        normalized_path = PurePosixPath(file_path)
        if normalized_path.is_absolute() or ".." in normalized_path.parts:
            raise ValueError(f"Invalid GitHub source path: {file_path}")

        token = settings.github_token.get_secret_value()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"/repos/{settings.github_repo}/contents/{file_path}"
        params = {"ref": settings.github_base_branch}

        async with httpx.AsyncClient(headers=headers, base_url="https://api.github.com") as client:
            response = await client.get(url, params=params)
        if response.status_code == 404:
            raise FileNotFoundError(
                f"GitHub Terraform source file not found: {file_path} in {settings.github_repo}@{settings.github_base_branch}"
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"GitHub source lookup failed for {file_path}: HTTP {response.status_code}"
            )
        payload = response.json()
        if payload.get("encoding") != "base64" or "content" not in payload:
            raise RuntimeError(f"Unexpected GitHub contents payload for {file_path}")
        return base64.b64decode(payload["content"]).decode()

    def _render_primary_terraform_snippet(
        self,
        *,
        source_label: str,
        device_name: str,
        networks: dict,
    ) -> str:
        networks_json = json.dumps(networks, indent=2, sort_keys=True)
        return (
            f"# Terraform primary snippet for {device_name}\n"
            f"# Canonical source: {source_label}\n"
            "locals {\n"
            "  mist_networks = jsondecode(<<JSON\n"
            f"{indent(networks_json, '    ')}\n"
            "  JSON\n"
            "  )\n"
            "}\n\n"
            'resource "mist_org_networktemplate" "offices" {\n'
            "  networks = local.mist_networks\n"
            "}\n"
        )

    def _validate_terraform_template_text(self, content: str, source_label: str) -> None:
        terraform_markers = ("resource ", "terraform {", "locals {", "module ", "data ")
        if not any(marker in content.lower() for marker in terraform_markers):
            raise ValueError(f"Terraform source template is not Terraform-shaped: {source_label}")

    def _find_repo_root(self) -> Path:
        for parent in Path(__file__).resolve().parents:
            if (parent / "pyproject.toml").exists():
                return parent
        raise RuntimeError("Unable to resolve repository root from terraform backend path")


    def _make_meta(self, change_request: ChangeRequest) -> ArtifactMeta:
        return ArtifactMeta(
            run_id=change_request.meta.run_id,
            artifact_id=str(uuid4()),
            version=1,
            created_at=datetime.now(timezone.utc),
            created_by="terraform-backend",
        )

    @staticmethod
    def _parse_vlan_command_entry(cmd: str, device_name: str) -> dict[str, str]:
        try:
            entry: Any = json.loads(cmd)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Malformed command entry for device '{device_name}': {cmd!r}"
            ) from exc
        if not isinstance(entry, dict):
            raise ValueError(
                f"Invalid command entry for device '{device_name}': expected object JSON, got {type(entry).__name__}."
            )
        if set(entry.keys()) != {"name", "vlan_id"}:
            raise ValueError(
                f"Invalid command entry keys for device '{device_name}': {sorted(entry.keys())}."
            )
        if not isinstance(entry["name"], str) or not entry["name"].strip():
            raise ValueError(f"Invalid VLAN command name for device '{device_name}'.")
        if not isinstance(entry["vlan_id"], str) or not entry["vlan_id"].strip():
            raise ValueError(f"Invalid VLAN command vlan_id for device '{device_name}'.")
        return {"name": entry["name"], "vlan_id": entry["vlan_id"]}

    @staticmethod
    def _resolve_repo_bounded_path(base_dir: Path, configured_path: str, setting_name: str) -> Path:
        candidate = Path(configured_path)
        resolved = (base_dir / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if not resolved.is_relative_to(base_dir.resolve()):
            raise ValueError(
                f"{setting_name} resolves outside allowed base directory '{base_dir}': {resolved}"
            )
        return resolved
