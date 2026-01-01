"""Unit tests for LLM Tracer client library.

These tests verify client behavior without requiring a running server.
Uses httpx mocking since the client uses httpx.AsyncClient.

Most client integrations tests are already covered by:
 - service/tests/integration/test_api_endpoints.py
 - service/tests/integration/test_complete_workflow.py
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from client.llm_tracer import (
    TracerClient,
    SyncTracerClient,
    TraceContext,
    SpanContext
)


class TestTracerClientInit:
    """Test client initialization with various configurations"""

    def test_init_w_explicit_config(self):
        """Client accepts explicit config"""
        client = TracerClient(
            base_url="http://custom:8000",
            api_key="project-myproject",
        )
        
        assert client.base_url == "http://custom:8000"
        assert client.api_key == "project-myproject"
        assert client.project_id == "myproject"  # Extracted from api_key
        assert client.enabled is True    

    def test_init_wo_apikey_disables_tracing(self):
        """Client disables tracing if no api_key is provided"""
        # patching the environment with clear=True clears out all environment variables
        # so that TRACER_API_KEY is not read by default.
        with patch.dict("os.environ", {}, clear=True):
            client = TracerClient(base_url="http://localhost:8001")
        
        assert client.enabled is False
    
    def test_init_tracing_disabled_via_env(self):
        """Client respects TRACING_ENABLED=false"""
        # Here patch is used to override only the env var within the context
        with patch.dict("os.environ", {"TRACING_ENABLED": "false"}):
            client = TracerClient(api_key="project-test")
        
        assert client.enabled is False
    
    def test_project_id_extracted_from_api_key(self):
        """Check that project ID is auto-extracted from api_key format"""
        client = TracerClient(api_key="project-test")
        assert client.project_id == "test"
    

class TestTracerClientGracefulFailure:
    """Test that client never blocks or crashes the main application"""

    @pytest.mark.asyncio
    async def test_create_trace_fails_gracefully(self):
        """Test that create_trace never blocks or crashes"""
        client = TracerClient(
            base_url="http://unreachable:9999",
            api_key="project-test"
        )

        # Should not raise, rather just return None
        trace_id = await client.create_trace("test-trace")
        
        assert trace_id is None
        await client.close()
    
    @pytest.mark.asyncio
    async def test_disabled_client_returns_none(self):
        """Disabled client returns None without making requests"""
        client = TracerClient(base_url="http://localhost:8001")
        client.enabled = False
        
        trace_id = await client.create_trace("test_trace")
        span_id = await client.create_span("t1", "span", "llm")
        
        assert trace_id is None
        assert span_id is None
        await client.close()
    

class TestAsyncContextManagers:
    """Test async context manager behavior with mocked HTTP requests"""

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx.AsyncClient for testing"""
        with patch("client.llm_tracer.client.httpx.AsyncClient") as mock:
            mock_instance = AsyncMock()
            mock.return_value = mock_instance

            # Mock successful response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "trace_id": "trace_123",
                "status": "created"
            }
            mock_response.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_response

            mock_patch_response = MagicMock()
            mock_patch_response.raise_for_status = MagicMock()
            mock_instance.patch.return_value = mock_patch_response

            yield mock_instance

    @pytest.mark.asyncio
    async def test_trace_context_manager(self, mock_httpx_client):
        """Trace context manager creates and completes the trace."""
        client = TracerClient(
            base_url="http://localhost:8001",
            api_key="project-test"
        )
        client._client = mock_httpx_client

        async with client.trace("test-operation") as trace:
            assert trace.trace_id == "trace_123"
            trace.set_output("completed")
        
        # Verify trace was created and completed
        assert mock_httpx_client.post.called  # create_trace
        assert mock_httpx_client.patch.called  # complete_trace

    @pytest.mark.asyncio
    async def test_span_context_manager(self, mock_httpx_client):
        """Span context manager creates and completes the span."""
        # Update mock for span creation
        mock_httpx_client.post.return_value.json.side_effect = [
            {"trace_id": "trace_123", "status": "created"},
            {"span_id": "span_123", "status": "created"},
        ]

        client = TracerClient(
            base_url="http://localhost:8001",
            api_key="project-test",
        )
        client._client = mock_httpx_client

        async with client.trace("operation") as trace:
            async with client.span("llm-call", "llm", model="gpt-4") as span:
                span.set_output(
                    output_data={"response": "Hello"},
                    tokens_input=10,
                    tokens_output=5,
                )
        
        # 2 POST calls: trace + span
        assert mock_httpx_client.post.call_count == 2
        
        # 2 PATCH call: complete span + complete trace
        assert mock_httpx_client.patch.call_count == 2
    
    @pytest.mark.asyncio
    async def test_exception_captured_in_span(self, mock_httpx_client):
        """Exceptions within span are captured as errors."""
        mock_httpx_client.post.return_value.json.side_effect = [
            {"trace_id": "trace_123"},
            {"span_id": "span_456"},
        ]

        client = TracerClient(
            base_url="http://localhost:8001",
            api_key="project-test",
        )
        client._client = mock_httpx_client

        with pytest.raises(ValueError):
            async with client.trace("operation") as trace:
                async with client.span("failing-op", "function") as span:
                    raise ValueError("Purposefully meant to fail here.")
        
        # Span should still be completed (with error captured)
        assert mock_httpx_client.patch.called
    

class TestSpanContext:
    """Test SpanContext data capture methods."""

    def test_set_output_stores_data(self):
        """set_output stores all metrics"""
        mock_client = MagicMock()
        span = SpanContext(mock_client, "span-1", "trace-1")
        # Here, mock_client accepts any mathod call or attribute access. It just does
        # nothing without crashing. SpanContext needs client, but we are not interested
        # in testing the client here, rather the SpanContext logic. So mock_client is 
        # perfect for such cases.

        span.set_output(
            output_data={"result": "success"},
            tokens_input=100,
            tokens_output=50,
            cost_usd=0.002,
        )

        assert span._output_data == {"result": "success"}
        assert span._tokens_input == 100
        assert span._tokens_output == 50
        assert span._cost_usd == 0.002
    
    def test_set_error_stores_message(self):
        """set_error stores error msg."""
        mock_client = MagicMock()
        span = SpanContext(mock_client, "span-1", "trace-1")
        
        span.set_error("Rate_limit_exceeded.")
        assert span._error == "Rate_limit_exceeded."


class TestSyncClient:
    """Test synchronous client wrapper.
    
    We do not need exhaustive test as SyncTracerClient is just a wrapper around TracerClient
    async behaviors that we then simple force to loop and be thread aware. It is not a full fledged class.
    Its client handle refers to "TracerClient"
    """

    def test_sync_client_init(self):
        """Sync client initializes properly."""
        client = SyncTracerClient(
            base_url="http://localhost:8001",
            api_key="project-test",
        )

        assert client._async_client is not None
        assert client._async_client.api_key == "project-test"
    
    def test_sync_trace_context_manager(self):
        """Sync trace context manager works without async/await."""
        # Tests that SyncTracerClient works correctly by mocking just 2 async methods,
        # instead of the entire HTTP layer.
        with patch.object(TracerClient, "create_trace", new_callable=AsyncMock) as mock_create:
            # Before patch: TracerClient.create_trace  →  Real method that calls HTTP POST
            # After patch: TracerClient.create_trace  →  AsyncMock (fake, no HTTP)
            with patch.object(TracerClient, "complete_trace", new_callable=AsyncMock) as mock_complete:
                # After patch: TracerClient.complete_trace  →  AsyncMock (fake, no HTTP)

                mock_create.return_value = "trace-sync-123"

                client = SyncTracerClient(
                    base_url="http://localhost:8001",
                    api_key="project-test",
                )

                with client.trace("sync-operation") as trace:
                    assert trace.trace_id == "trace-sync-123"
                    trace.set_output("done")
                
                mock_create.assert_called_once()
                mock_complete.assert_called_once()
