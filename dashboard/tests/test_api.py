"""Tests for the Tracer API client.

These tests mock HTTP requests at the transport level using respx.
This validates that api.py makes correct requests without hitting real servers.
"""

import pytest
import httpx
import respx

from dashboard.api import (
    get_stats, get_traces, get_trace_detail, check_health,
    API_URL, API_KEY,
)


class TestGetStats:
    """Tests for get_stats function."""

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint_with_api_key(self, respx_mock):
        """Should call /api/stats with correct headers."""
        route = respx_mock.get(f"{API_URL}/api/stats").mock(
            return_value=httpx.Response(200, json={"total_traces": 10})
        )

        await get_stats()

        assert route.called
        assert route.calls[0].request.headers["X-API-Key"] == API_KEY

    @pytest.mark.asyncio
    async def test_returns_parsed_response(self, respx_mock):
        """Should return stats from API response."""
        respx_mock.get(f"{API_URL}/api/stats").mock(
            return_value=httpx.Response(200, json={
                "total_traces": 100,
                "total_spans": 500,
                "total_tokens": 50000,
                "total_cost": 1.25,
            })
        )

        result = await get_stats()

        assert result["total_traces"] == 100
        assert result["total_cost"] == 1.25

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, respx_mock):
        """Should raise HTTPStatusError on 4xx/5xx."""
        respx_mock.get(f"{API_URL}/api/stats").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await get_stats()


class TestGetTraces:
    """Tests for get_traces function."""

    @pytest.mark.asyncio
    async def test_calls_endpoint_with_limit_param(self, respx_mock):
        """Should pass limit as query param to API."""
        route = respx_mock.get(f"{API_URL}/api/traces").mock(
            return_value=httpx.Response(200, json={"traces": []})
        )

        await get_traces(limit=25)

        assert route.called
        assert route.calls[0].request.url.params["limit"] == "25"

    @pytest.mark.asyncio
    async def test_includes_cursor_when_provided(self, respx_mock):
        """Should include cursor param when provided for pagination."""
        route = respx_mock.get(f"{API_URL}/api/traces").mock(
            return_value=httpx.Response(200, json={"traces": []})
        )

        await get_traces(limit=10, cursor="next_page_token")

        assert route.calls[0].request.url.params["cursor"] == "next_page_token"

    @pytest.mark.asyncio
    async def test_omits_cursor_when_none(self, respx_mock):
        """Should not include cursor param when None."""
        route = respx_mock.get(f"{API_URL}/api/traces").mock(
            return_value=httpx.Response(200, json={"traces": []})
        )

        await get_traces(limit=10, cursor=None)

        assert "cursor" not in route.calls[0].request.url.params

    @pytest.mark.asyncio
    async def test_raises_on_unauthorized(self, respx_mock):
        """Should raise on 401 (invalid API key)."""
        respx_mock.get(f"{API_URL}/api/traces").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid API key"})
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await get_traces()

        assert exc_info.value.response.status_code == 401


class TestGetTraceDetail:
    """Tests for get_trace_detail function."""

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint_with_trace_id(self, respx_mock):
        """Should call /api/traces/{trace_id} endpoint."""
        trace_id = "abc-123"
        route = respx_mock.get(f"{API_URL}/api/traces/{trace_id}").mock(
            return_value=httpx.Response(200, json={"trace": {}, "spans": []})
        )

        await get_trace_detail(trace_id)

        assert route.called

    @pytest.mark.asyncio
    async def test_raises_on_not_found(self, respx_mock):
        """Should raise on 404 (trace not found)."""
        respx_mock.get(f"{API_URL}/api/traces/nonexistent").mock(
            return_value=httpx.Response(404, json={"detail": "Trace not found"})
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await get_trace_detail("nonexistent")

        assert exc_info.value.response.status_code == 404


class TestCheckHealth:
    """Tests for check_health function."""

    @pytest.mark.asyncio
    async def test_returns_true_on_healthy(self, respx_mock):
        """Should return True when API is healthy."""
        respx_mock.get(f"{API_URL}/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )

        result = await check_health()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_unhealthy(self, respx_mock):
        """Should return False when API is unavailable."""
        respx_mock.get(f"{API_URL}/health").mock(
            return_value=httpx.Response(503)
        )

        result = await check_health()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self, respx_mock):
        """Should return False on connection timeout."""
        respx_mock.get(f"{API_URL}/health").mock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )

        result = await check_health()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self, respx_mock):
        """Should return False when server is unreachable."""
        respx_mock.get(f"{API_URL}/health").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await check_health()

        assert result is False
