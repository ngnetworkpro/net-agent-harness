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
from net_agent_harness.models.enums import ChangeRisk, NetworkDomain, PlanDecisionType, RenderRole, TargetScope


def _build_change_request() -> ChangeRequest:
    return ChangeRequest(
        meta=ArtifactMeta(run_id="run-terraform", artifact_id="cr-1", created_by="test"),
        domain=NetworkDomain.VLAN,
        scope=ScopeRef(device_names=["sw1", "sw2"]),
        target_scope=TargetScope.device,
        resolved_targets=[
            ResolvedTarget(name="sw1", platform="mist"),
            ResolvedTarget(name="sw2", platform="mist"),
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

    assert len(render.snippets) == 2
    assert {s.device_name for s in render.snippets} == {"sw1", "sw2"}
    assert all(s.render_role == RenderRole.PRIMARY for s in render.snippets)
    assert all((s.path_hint or "").startswith("local:") for s in render.snippets)
    assert all("locals {" in (s.rendered_text or "") for s in render.snippets)


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
    assert all((s.path_hint or "").startswith("github:ngnetworkpro/net-agent-harness:") for s in render.snippets)


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
