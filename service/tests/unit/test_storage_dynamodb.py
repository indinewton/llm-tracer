"""Unit test for DynamoDB storage.

Execute this file from service/ for async tests to pass
# Note: pytest adds the parent directory (llm-tracer/) to sys.path during test collection,
# making 'service' importable as a package. Run tests from service/ directory with: uv run pytest
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, UTC

from botocore.exceptions import ClientError

from service.src.storage_dynamodb import DynamoDBStorage
from service.src.models import Trace, Span


# =============================================================================
# DynamoDB Error Handling Tests
# =============================================================================
# These tests verify that storage methods handle DynamoDB failures gracefully
# without crashing. In production, DynamoDB can fail due to:
# - Throttling (ProvisionedThroughputExceededException)
# - Service unavailable
# - Network timeouts
# - Access denied
# =============================================================================

def make_client_error(error_code: str, message: str = "Test error") -> ClientError:
    """Helper to create boto3 ClientError exceptions."""
    return ClientError(
        error_response={
            "Error": {
                "Code": error_code,
                "Message": message,
            }
        },
        operation_name="TestOperation",
    )


@pytest.mark.asyncio
async def test_get_trace_handles_dynamodb_client_error(dynamodb_tables):
    """Verify get_trace returns None when DynamoDB raises ClientError."""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",
        spans_table_name="test-spans",
    )

    # Patch the table's get_item to raise a ClientError (simulating throttling)
    with patch.object(
        storage.traces_table,
        "get_item",
        side_effect=make_client_error("ProvisionedThroughputExceededException"),
    ):
        result = await storage.get_trace("some-trace-id")

    # Should return None, not raise an exception
    assert result is None


@pytest.mark.asyncio
async def test_get_traces_handles_dynamodb_client_error(dynamodb_tables):
    """Verify get_traces returns empty result when DynamoDB raises ClientError."""
    from service.src.models import TraceQuery

    storage = DynamoDBStorage(
        traces_table_name="test-traces",
        spans_table_name="test-spans",
    )

    query = TraceQuery(project_id="test-project", limit=10)

    # Patch the table's query to raise a ClientError
    with patch.object(
        storage.traces_table,
        "query",
        side_effect=make_client_error("ServiceUnavailable", "DynamoDB is temporarily unavailable"),
    ):
        result = await storage.get_traces(query)

    # Should return empty result structure, not raise an exception
    assert result == {"items": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_get_span_handles_dynamodb_client_error(dynamodb_tables):
    """Verify get_span returns None when DynamoDB raises ClientError."""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",
        spans_table_name="test-spans",
    )

    with patch.object(
        storage.spans_table,
        "get_item",
        side_effect=make_client_error("AccessDeniedException", "Access denied"),
    ):
        result = await storage.get_span("some-span-id")

    assert result is None


@pytest.mark.asyncio
async def test_get_spans_handles_dynamodb_client_error(dynamodb_tables):
    """Verify get_spans returns empty list when DynamoDB raises ClientError."""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",
        spans_table_name="test-spans",
    )

    with patch.object(
        storage.spans_table,
        "query",
        side_effect=make_client_error("InternalServerError"),
    ):
        result = await storage.get_spans("some-trace-id")

    assert result == []


@pytest.mark.asyncio
async def test_complete_span_handles_dynamodb_client_error(dynamodb_tables, sample_span):
    """Verify complete_span returns False when DynamoDB update fails."""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",
        spans_table_name="test-spans",
    )

    # First save a span so it exists
    span = Span(**sample_span, end_time=None, duration_ms=None)
    await storage.save_span(span)

    # Now patch update_item to fail
    with patch.object(
        storage.spans_table,
        "update_item",
        side_effect=make_client_error("ProvisionedThroughputExceededException"),
    ):
        result = await storage.complete_span(
            span_id=sample_span["span_id"],
            end_time=datetime.now(UTC),
            output_data={"result": "test"},
        )

    # Should return False, not raise an exception
    assert result is False


@pytest.mark.asyncio
async def test_complete_trace_handles_dynamodb_client_error(dynamodb_tables, sample_trace):
    """Verify complete_trace returns False when DynamoDB update fails."""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",
        spans_table_name="test-spans",
    )

    # First save a trace so it exists
    trace = Trace(**sample_trace)
    await storage.save_trace(trace)

    # Now patch update_item to fail
    with patch.object(
        storage.traces_table,
        "update_item",
        side_effect=make_client_error("RequestLimitExceeded"),
    ):
        result = await storage.complete_trace(
            trace_id=sample_trace["trace_id"],
            end_time=datetime.now(UTC),
            output="test output",
        )

    # Should return False, not raise an exception
    assert result is False


@pytest.mark.asyncio
async def test_get_stats_handles_dynamodb_client_error(dynamodb_tables):
    """Verify get_stats returns zero stats when DynamoDB fails."""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",
        spans_table_name="test-spans",
    )

    with patch.object(
        storage.traces_table,
        "query",
        side_effect=make_client_error("ThrottlingException"),
    ):
        result = await storage.get_stats("test-project")

    # Should return zeroed stats, not raise an exception
    assert result == {
        "total_traces": 0,
        "total_spans": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
    }


# =============================================================================
# Original Unit Tests
# =============================================================================


@pytest.mark.asyncio
async def test_save_trace(dynamodb_tables, sample_trace):
    """Test saving a trace to DynamoDB"""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",  # as named in conftest.py
        spans_table_name="test-spans",
    )

    trace = Trace(**sample_trace)
    trace_id = await storage.save_trace(trace)

    assert trace_id == sample_trace["trace_id"], (
        f"Trace ID mismatch: expected {sample_trace['trace_id']}, "
        f"got {trace_id} saved in DynamoDB traces table."
    )

    # Verify in DynamoDB; dynamodb_tables is fixture from conftest.py
    item = dynamodb_tables["traces"].get_item(Key={"trace_id": trace_id})
    
    assert item["Item"]["name"] == sample_trace["name"], (
        f"Trace name mismatch: expected {sample_trace['name']}, "
        f"got {item['Item']['name']}: save_trace overwrote 'name' field."
    )
    assert "ttl" in item["Item"], (
        "TTL was not added to trace item; this should have worked by default."
    )


@pytest.mark.asyncio
async def test_get_trace(dynamodb_tables, sample_trace):
    """Test getting a trace from DynamoDB"""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",  # as named in conftest.py
        spans_table_name="test-spans",
    )

    trace = Trace(**sample_trace)
    await storage.save_trace(trace)

    # Get
    retrieved = await storage.get_trace(sample_trace["trace_id"])

    assert retrieved is not None, (
        f"Trace {sample_trace['trace_id']} not found in DynamoDB traces table."
    )
    try:
        assert retrieved["trace_id"] == sample_trace["trace_id"]
        assert retrieved["name"] == sample_trace["name"]
        assert "ttl" not in retrieved  # TTL must be removed from response-
    except Exception as e:
        assert False, (
            f"Trace {sample_trace['trace_id']} either not found or "
            f"has unexpected fields: {e}"
        )

    # test for project_id security check
    result = await storage.get_trace(
        sample_trace["trace_id"],
        project_id="test-project",
    )
    assert result is not None, "project_id 'test-project' not found"
    
    # Wrong project - should return None
    result = await storage.get_trace(
        sample_trace["trace_id"],
        project_id="wrong-project",
    )
    assert result is None, (
        "project_id 'wrong-project' returned trace; "
        "project_id security is not working properly."
    )


@pytest.mark.asyncio
async def test_save_span(dynamodb_tables, sample_span):
    """Test saving a span to DynamoDB"""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",  # as named in conftest.py
        spans_table_name="test-spans",
    )

    span = Span(**sample_span, end_time=None, duration_ms=None)
    span_id = await storage.save_span(span)

    assert span_id == sample_span["span_id"], (
        f"Span ID mismatch: expected {sample_span['span_id']}, "
        f"got {span_id} saved in DynamoDB spans table."
    )

    # Verify in DynamoDB; dynamodb_tables is fixture from conftest.py
    item = dynamodb_tables["spans"].get_item(Key={"span_id": span_id})
    try:
        assert item["Item"]["name"] == sample_span["name"]
        assert item["Item"]["tokens_input"] == 100
    except Exception as e:
        assert False, (
            f"Span {span_id} as fetched from DynamoDB spans table "
            f"has unexpected fields: {e}"
        )


@pytest.mark.asyncio
async def test_complete_span(dynamodb_tables, sample_span):
    """Test completing a span in DynamoDB"""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",  # as named in conftest.py
        spans_table_name="test-spans",
    )

    span = Span(**sample_span, end_time=None, duration_ms=None)
    await storage.save_span(span)

    # Complete the span
    end_time = datetime.now(UTC)
    result = await storage.complete_span(
        span_id=sample_span["span_id"],
        end_time=end_time,
        output_data={"result": "success"},
        tokens_input=100,
        tokens_output=50,
    )

    assert result is True, "Span completion failed"

    # Verify completed span in DynamoDB
    item = dynamodb_tables["spans"].get_item(Key={"span_id": sample_span["span_id"]})
    try:
        assert "end_time" in item["Item"]
        assert "duration_ms" in item["Item"]
        assert item["Item"]["output_data"]["result"] == "success"
    except Exception as e:
        assert False, (
            f"Span {sample_span['span_id']} as fetched from DynamoDB spans table "
            f"has unexpected fields: {e}"
        )


@pytest.mark.asyncio
async def test_get_spans_for_trace(dynamodb_tables, sample_trace, sample_span):
    """Test querying spans by trace_id."""
    storage = DynamoDBStorage(
        traces_table_name="test-traces",  # as named in conftest.py
        spans_table_name="test-spans",
    )

    # Save trace
    trace = Trace(**sample_trace)
    await storage.save_trace(trace)

    # Save multiple span
    for i in range(3):
        span = Span(
            **{**sample_span, "span_id": f"span-{i}"},  # replace existing key and expand as kwargs
            end_time=None,
            duration_ms=None,
        )
        await storage.save_span(span)

    # Query
    spans = await storage.get_spans(sample_trace["trace_id"])

    assert len(spans) == 3, "Incorrect number of spans returned"
    assert all(s["trace_id"] == sample_trace["trace_id"] for s in spans), (
        "All spans do not have the same trace_id"
    )
