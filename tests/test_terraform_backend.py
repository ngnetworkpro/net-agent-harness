import base64

import pytest
from pydantic import SecretStr

from net_agent_harness.adapters.backends.terraform import TerraformBackendAdapter
from net_agent_harness.config import settings
from net_agent_harness.models.changes import (
    ChangeRequest,
    DeviceChange,
    PlanDecision,
    PortSpec,
    RequestedChange,
    ResolvedTarget,
    RollbackPlan,
    VlanChange,
    VlanSpec,
)
from net_agent_harness.models.common import ArtifactMeta, ScopeRef
from net_agent_harness.models.enums import ChangeRisk, DeviceVendor, NetworkDomain, PlanDecisionType, RenderRole, TargetScope


def _build_change_request() -> ChangeRequest:
    return ChangeRequest(
        meta=ArtifactMeta(run_id="run-terraform", artifact_id="cr-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(device_names=["sw1", "sw2"]),
        target_scope=TargetScope.device,
        resolved_targets=[
            ResolvedTarget(name="sw1", platform="mist", vendor=DeviceVendor.JUNIPER),
            ResolvedTarget(name="sw2", platform="mist", vendor=DeviceVendor.JUNIPER),
        ],
        requested_change=RequestedChange(summary="test", intent="test"),
        risk=ChangeRisk.LOW,
        rollback_plan=RollbackPlan(summary="none"),
        plan_decision=PlanDecision(
            decision=PlanDecisionType.APPLY,
            reason="test",
            diff=[
                DeviceChange(
                    device="sw1",
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[VlanSpec(id=220, name="Engineering")],
                        ports_to_update=[PortSpec(interface="ge-0/0/1", vlan_id=220, mode="access")],
                    ),
                ),
                DeviceChange(
                    device="sw2",
                    domain=NetworkDomain.VLAN,
                    changes=VlanChange(
                        vlans_to_create=[VlanSpec(id=221, name="Voice")],
                        ports_to_update=[],
                    ),
                ),
            ],
        ),
    )


@pytest.mark.asyncio
async def test_render_uses_local_source_by_default(tmp_path, monkeypatch):
    source_dir = tmp_path / "tf-source"
    source_dir.mkdir()
    (source_dir / "mist_networks.json").write_text('{"Access": {"vlan_id": "11"}}')
    (source_dir / "mist.tf").write_text('resource "mist_org_networktemplate" "offices" {}')

    monkeypatch.setattr(settings, "terraform_render_source", "local")
    monkeypatch.setattr(settings, "terraform_source_dir", str(source_dir))
    monkeypatch.setattr(settings, "terraform_source_networks_file", "mist_networks.json")
    monkeypatch.setattr(settings, "terraform_source_template_file", "mist.tf")

    render = await TerraformBackendAdapter().render(_build_change_request())

    # 2 devices × (1 primary + 1 fallback) = 4 snippets
    assert len(render.snippets) == 4
    primary = [s for s in render.snippets if s.render_role == RenderRole.PRIMARY]
    fallback = [s for s in render.snippets if s.render_role == RenderRole.FALLBACK]
    assert len(primary) == 2
    assert len(fallback) == 2
    assert {s.device_name for s in primary} == {"sw1", "sw2"}
    assert {s.device_name for s in fallback} == {"sw1", "sw2"}

    # Primary snippets must contain real Terraform HCL
    for s in primary:
        assert (s.path_hint or "").startswith("local:")
        assert "locals {" in (s.rendered_text or "")
        assert "resource " in (s.rendered_text or "")

    # CLI fallback for sw1 must contain real VLAN + interface commands
    sw1_fb = [s for s in fallback if s.device_name == "sw1"][0]
    assert "set vlans Engineering vlan-id 220" in sw1_fb.rendered_text
    assert "set interfaces ge-0/0/1 unit 0 family ethernet-switching vlan members 220" in sw1_fb.rendered_text

    # CLI fallback for sw2 (no ports, only VLAN)
    sw2_fb = [s for s in fallback if s.device_name == "sw2"][0]
    assert "set vlans Voice vlan-id 221" in sw2_fb.rendered_text


@pytest.mark.asyncio
async def test_render_uses_github_source(monkeypatch):
    class _Response:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            if url.endswith("/mist_networks.json"):
                content = base64.b64encode(b'{"Access": {"vlan_id": "11"}}').decode()
                return _Response(200, {"encoding": "base64", "content": content})
            if url.endswith("/mist.tf"):
                content = base64.b64encode(b'resource "mist_org_networktemplate" "offices" {}').decode()
                return _Response(200, {"encoding": "base64", "content": content})
            return _Response(404, {})

    monkeypatch.setattr(settings, "terraform_render_source", "github")
    monkeypatch.setattr(settings, "github_repo", "ngnetworkpro/net-agent-harness")
    monkeypatch.setattr(settings, "github_token", SecretStr("token"))
    monkeypatch.setattr(settings, "github_base_branch", "main")
    monkeypatch.setattr("net_agent_harness.adapters.backends.terraform.httpx.AsyncClient", _FakeClient)

    render = await TerraformBackendAdapter().render(_build_change_request())
    primary = [s for s in render.snippets if s.render_role == RenderRole.PRIMARY]
    assert all((s.path_hint or "").startswith("github:ngnetworkpro/net-agent-harness:") for s in primary)


@pytest.mark.asyncio
async def test_render_github_source_missing_repo(monkeypatch):
    monkeypatch.setattr(settings, "terraform_render_source", "github")
    monkeypatch.setattr(settings, "github_repo", None)
    monkeypatch.setattr(settings, "github_token", SecretStr("token"))

    with pytest.raises(ValueError, match="NET_AGENT_GITHUB_REPO is not set"):
        await TerraformBackendAdapter().render(_build_change_request())


@pytest.mark.asyncio
async def test_render_github_source_missing_token(monkeypatch):
    monkeypatch.setattr(settings, "terraform_render_source", "github")
    monkeypatch.setattr(settings, "github_repo", "ngnetworkpro/net-agent-harness")
    monkeypatch.setattr(settings, "github_token", None)

    with pytest.raises(ValueError, match="NET_AGENT_GITHUB_TOKEN is not set"):
        await TerraformBackendAdapter().render(_build_change_request())


@pytest.mark.asyncio
async def test_render_github_source_missing_remote_file(monkeypatch):
    class _Response:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            if url.endswith("/mist_networks.json"):
                content = base64.b64encode(b'{"Access": {"vlan_id": "11"}}').decode()
                return _Response(200, {"encoding": "base64", "content": content})
            return _Response(404, {})

    monkeypatch.setattr(settings, "terraform_render_source", "github")
    monkeypatch.setattr(settings, "github_repo", "ngnetworkpro/net-agent-harness")
    monkeypatch.setattr(settings, "github_token", SecretStr("token"))
    monkeypatch.setattr(settings, "github_base_branch", "main")
    monkeypatch.setattr("net_agent_harness.adapters.backends.terraform.httpx.AsyncClient", _FakeClient)

    with pytest.raises(FileNotFoundError, match="GitHub Terraform source file not found"):
        await TerraformBackendAdapter().render(_build_change_request())


@pytest.mark.asyncio
async def test_apply_rejects_malformed_command_entries(tmp_path, monkeypatch):
    adapter = TerraformBackendAdapter()
    source_dir = tmp_path / "tf-source"
    source_dir.mkdir()
    (source_dir / "mist_networks.json").write_text('{"Access": {"vlan_id": "11"}}')
    (source_dir / "mist.tf").write_text('resource "mist_org_networktemplate" "offices" {}')
    networks_file = tmp_path / "networks.json"
    networks_file.write_text('{"Access": {"vlan_id": "11"}}')

    monkeypatch.setattr(settings, "terraform_render_source", "local")
    monkeypatch.setattr(settings, "terraform_source_dir", str(source_dir))
    monkeypatch.setattr(settings, "terraform_source_networks_file", "mist_networks.json")
    monkeypatch.setattr(settings, "terraform_source_template_file", "mist.tf")
    monkeypatch.setattr(settings, "terraform_networks_file", str(networks_file))
    monkeypatch.setattr(settings, "github_repo", "ngnetworkpro/net-agent-harness")
    monkeypatch.setattr(settings, "github_token", SecretStr("token"))
    monkeypatch.setattr(adapter, "_find_repo_root", lambda: tmp_path)

    render = await adapter.render(_build_change_request())
    render.snippets[0].commands.append('{"name":"bad"}')

    with pytest.raises(ValueError, match="Invalid command entry keys"):
        await adapter.apply(render)


@pytest.mark.asyncio
async def test_render_rejects_local_source_path_escape(tmp_path, monkeypatch):
    source_dir = tmp_path / "tf-source"
    source_dir.mkdir()
    (source_dir / "mist.tf").write_text('resource "mist_org_networktemplate" "offices" {}')

    monkeypatch.setattr(settings, "terraform_render_source", "local")
    monkeypatch.setattr(settings, "terraform_source_dir", str(source_dir))
    monkeypatch.setattr(settings, "terraform_source_networks_file", "../escape.json")
    monkeypatch.setattr(settings, "terraform_source_template_file", "mist.tf")

    with pytest.raises(ValueError, match="resolves outside allowed base directory"):
        await TerraformBackendAdapter().render(_build_change_request())
