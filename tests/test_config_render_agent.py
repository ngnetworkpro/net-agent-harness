import pytest
from unittest.mock import patch
from net_agent_harness.agents.config_render_agent import _enforce_snippets
from pydantic import ValidationError
from net_agent_harness.models.artifacts import ApiRequestPayload, ConfigRenderOutput, ConfigSnippet, RenderRequest, VlanRenderPayload, VlanRenderOp, RenderTarget
from net_agent_harness.models.artifacts import OperationType
from net_agent_harness.models.enums import NetworkDomain, RenderBackendType, RenderRole

@pytest.fixture
def mock_ctx():
    # Construct a dummy RunContext
    payload = VlanRenderPayload(
        vlan_ops=[
            VlanRenderOp(
                target=RenderTarget(name="sw1"),
                vlan_id=10,
                operation=OperationType.ENSURE_PRESENT
            )
        ]
    )
    req = RenderRequest(
        domain=NetworkDomain.VLAN,
        intent_type="set_access_vlan",
        payload=payload
    )
    # Using a dummy object for context
    class DummyCtx:
        deps = req
    return DummyCtx()

@pytest.mark.asyncio
async def test_validator_passes_api_primary_snippet(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(method="POST", path="/vlans", body={"vlan_id": 10}),
                commands=[]
            )
        ]
    )
    result = await _enforce_snippets(mock_ctx, output)
    assert result == output

@pytest.mark.asyncio
async def test_validator_passes_cli_fallback_snippet(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.CLI,
                render_role=RenderRole.FALLBACK,
                api_payload=None,
                commands=["vlan 10"]
            )
        ]
    )
    result = await _enforce_snippets(mock_ctx, output)
    assert result == output

@pytest.mark.asyncio
async def test_validator_passes_mixed_snippets(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(
                    method="POST",
                    path="/operations/batch",
                    body={"operations": [{"action": "create_vlan"}]},
                ),
                commands=[]
            ),
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.CLI,
                render_role=RenderRole.FALLBACK,
                api_payload=None,
                commands=["set vlans users vlan-id 10"]
            ),
        ]
    )
    result = await _enforce_snippets(mock_ctx, output)
    assert result == output

@pytest.mark.asyncio
async def test_validator_rejects_empty_snippets_when_ops_present(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[]
    )
    with pytest.raises(ValueError, match="Produce at least one ConfigSnippet"):
        await _enforce_snippets(mock_ctx, output)


@pytest.mark.asyncio
async def test_validator_bypasses_snippet_enforcement_when_no_ops_present():
    req = RenderRequest(
        domain=NetworkDomain.VLAN,
        intent_type="set_access_vlan",
        payload=VlanRenderPayload(),
    )

    class DummyCtx:
        deps = req

    output = ConfigRenderOutput(summary="Test", snippets=[])
    result = await _enforce_snippets(DummyCtx(), output)
    assert result == output

@pytest.mark.asyncio
async def test_validator_rejects_api_snippet_with_missing_payload(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=None,
                commands=[]
            )
        ]
    )
    with pytest.raises(ValueError, match="must have a non-empty api_payload"):
        await _enforce_snippets(mock_ctx, output)

@pytest.mark.asyncio
async def test_validator_rejects_cli_snippet_with_missing_commands(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.CLI,
                render_role=RenderRole.FALLBACK,
                api_payload=None,
                commands=[]
            )
        ]
    )
    with pytest.raises(ValueError, match="must have non-empty commands"):
        await _enforce_snippets(mock_ctx, output)


@pytest.mark.asyncio
async def test_validator_rejects_domain_specific_snippet_errors(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(method="POST", path="/vlans", body={"vlan_id": 10}),
                commands=[],
            )
        ],
    )
    with patch.object(VlanRenderPayload, "validate_snippets", return_value=["domain-rule violation"]):
        with pytest.raises(ValueError, match="Domain-specific snippet validation failed"):
            await _enforce_snippets(mock_ctx, output)


@pytest.mark.asyncio
async def test_validator_allows_domain_specific_snippet_noop(mock_ctx):
    output = ConfigRenderOutput(
        summary="Test",
        snippets=[
            ConfigSnippet(
                device_name="sw1",
                backend_type=RenderBackendType.API,
                render_role=RenderRole.PRIMARY,
                api_payload=ApiRequestPayload(method="POST", path="/vlans", body={"vlan_id": 10}),
                commands=[],
            )
        ],
    )
    with patch.object(VlanRenderPayload, "validate_snippets", return_value=[]):
        result = await _enforce_snippets(mock_ctx, output)
    assert result == output


def test_api_request_payload_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ApiRequestPayload(
            method="POST",
            path="/vlans",
            body={"id": 10},
            extra_field="nope",
        )
