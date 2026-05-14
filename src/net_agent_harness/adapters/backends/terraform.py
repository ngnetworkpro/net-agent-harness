import json
import base64
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from net_agent_harness.adapters.backends.base import BackendAdapter
from net_agent_harness.config import settings
from net_agent_harness.models.artifacts import ArtifactMeta, ConfigRender, ConfigSnippet, ExecutionResult
from net_agent_harness.models.changes import ChangeRequest


class TerraformBackendAdapter(BackendAdapter):

    async def render(self, change_request: ChangeRequest) -> ConfigRender:
        if not settings.terraform_networks_file:
            raise ValueError("NET_AGENT_TERRAFORM_NETWORKS_FILE is not set")
        networks_path = Path(settings.terraform_networks_file)
        if not networks_path.exists():
            raise FileNotFoundError(f"networks.json not found at {networks_path}")

        current = json.loads(networks_path.read_text())

        # Collect VLANs to add from plan_decision diff
        additions: dict[str, str] = {}  # name -> vlan_id string
        if change_request.plan_decision:
            if change_request.plan_decision.decision.value != "apply":
                return ConfigRender(
                    meta=self._make_meta(change_request),
                    summary=f"No changes required: decision is '{change_request.plan_decision.decision.value}'.",
                )
            for device_change in change_request.plan_decision.diff:
                for vlan in device_change.changes.vlans_to_create:
                    additions[vlan.name] = str(vlan.id)

        if not additions:
            return ConfigRender(
                meta=self._make_meta(change_request),
                summary="No VLAN additions detected in plan decision.",
                warnings=["plan_decision contains no vlans_to_create entries"],
            )

        diff_lines = [f'  // Current: {len(current)} networks']
        for name, vlan_id in additions.items():
            diff_lines.append(f'+ "{name}": {{"vlan_id": "{vlan_id}"}}')

        # Store additions as JSON commands for apply() to consume
        commands = [json.dumps({"name": name, "vlan_id": vlan_id}) for name, vlan_id in additions.items()]

        snippet = ConfigSnippet(
            device_name="mist_org_networktemplate.offices",
            path_hint="networks.json",
            commands=commands,
            rendered_text="\n".join(diff_lines),
        )

        return ConfigRender(
            meta=self._make_meta(change_request),
            summary=f"Terraform: add {len(additions)} VLAN(s) to networks.json → GitHub PR targeting '{settings.github_base_branch}'",
            snippets=[snippet],
        )

    async def apply(self, config_render: ConfigRender) -> ExecutionResult:
        if not settings.terraform_networks_file:
            raise ValueError("NET_AGENT_TERRAFORM_NETWORKS_FILE is not set")
        if not settings.github_repo:
            raise ValueError("NET_AGENT_GITHUB_REPO is not set")
        if not settings.github_token:
            raise ValueError("NET_AGENT_GITHUB_TOKEN is not set")

        networks_path = Path(settings.terraform_networks_file)
        current = json.loads(networks_path.read_text())

        # Parse additions from snippet commands
        for snippet in config_render.snippets:
            for cmd in snippet.commands:
                entry = json.loads(cmd)
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

    def _make_meta(self, change_request: ChangeRequest) -> ArtifactMeta:
        return ArtifactMeta(
            run_id=change_request.meta.run_id,
            artifact_id=str(uuid4()),
            version=1,
            created_at=datetime.now(timezone.utc),
            created_by="terraform-backend",
        )
