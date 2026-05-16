import pytest
from unittest.mock import patch, AsyncMock
import httpx

from net_agent_harness.adapters.backends.direct_api import DirectAPIBackendAdapter
from net_agent_harness.models.artifacts import ApiRequestPayload, ConfigRender, ConfigSnippet, ArtifactMeta
from net_agent_harness.models.enums import RenderBackendType, RenderRole

@pytest.fixture
def adapter():
    return DirectAPIBackendAdapter()

@pytest.fixture
def base_meta():
    return ArtifactMeta(run_id="run-1", artifact_id="cr-1", created_by="test")

@pytest.fixture
def api_snippet():
    return ConfigSnippet(
        device_name="sw1",
        backend_type=RenderBackendType.API,
        render_role=RenderRole.PRIMARY,
        api_payload=ApiRequestPayload(method="POST", path="/api/test", body={"id": 10}),
        rendered_text="DO NOT READ THIS",
        commands=[]
    )

@pytest.fixture
def cli_snippet():
    return ConfigSnippet(
        device_name="sw2",
        backend_type=RenderBackendType.CLI,
        render_role=RenderRole.FALLBACK,
        api_payload=None,
        rendered_text="DO NOT READ THIS",
        commands=["set vlan 10"]
    )

@pytest.mark.asyncio
@patch("httpx.AsyncClient.request")
async def test_direct_api_apply_reads_from_api_payload(mock_request, adapter, base_meta, api_snippet):
    # Setup mock to succeed
    from unittest.mock import MagicMock
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_request.return_value = mock_resp

    config_render = ConfigRender(
        meta=base_meta,
        summary="Test render",
        snippets=[api_snippet]
    )

    result = await adapter.apply(config_render)

    assert result.status == "success"
    assert "Successfully executed API operations for 1 actions." in result.detail
    mock_request.assert_called_once_with(
        "POST",
        "https://api.example.com/api/test",
        json={"id": 10},
        params={},
    )

@pytest.mark.asyncio
@patch("httpx.AsyncClient.request")
async def test_direct_api_apply_skips_cli_snippets(mock_request, adapter, base_meta, cli_snippet):
    config_render = ConfigRender(
        meta=base_meta,
        summary="Test render",
        snippets=[cli_snippet]
    )

    result = await adapter.apply(config_render)

    assert result.status == "success"
    assert "No primary API snippets to execute" in result.detail
    mock_request.assert_not_called()

@pytest.mark.asyncio
@patch("httpx.AsyncClient.request")
async def test_direct_api_apply_returns_execution_result(mock_request, adapter, base_meta, api_snippet):
    from unittest.mock import MagicMock
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_request.return_value = mock_resp

    config_render = ConfigRender(
        meta=base_meta,
        summary="Test render",
        snippets=[api_snippet]
    )

    result = await adapter.apply(config_render)

    assert result.backend == "direct-api"
    assert result.status == "success"
    assert result.meta.created_by == "direct-api-backend"
    assert result.meta.run_id == "run-1"

@pytest.mark.asyncio
@patch("httpx.AsyncClient.request")
async def test_direct_api_apply_surfaces_api_errors(mock_request, adapter, base_meta, api_snippet):
    mock_request.side_effect = httpx.ConnectError("Connection refused")

    config_render = ConfigRender(
        meta=base_meta,
        summary="Test render",
        snippets=[api_snippet]
    )

    result = await adapter.apply(config_render)

    assert result.status == "failed"
    assert "Completed with 1 errors" in result.detail
    assert "Connection refused" in result.detail

@pytest.mark.asyncio
@patch("httpx.AsyncClient.request")
async def test_direct_api_apply_does_not_reinterpret_render_summary(mock_request, adapter, base_meta, api_snippet):
    from unittest.mock import MagicMock
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_request.return_value = mock_resp

    config_render = ConfigRender(
        meta=base_meta,
        summary="blocked/no_op text should not affect apply behavior",
        snippets=[api_snippet]
    )

    result = await adapter.apply(config_render)

    assert result.status == "success"
    mock_request.assert_called_once()
