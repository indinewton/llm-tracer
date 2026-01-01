"""Unit test for DynamoDB storage.

Execute pytest <this file> from root dir where service/ is a module.
"""

import pytest
from datetime import datetime, UTC

from service.src.storage_dynamodb import DynamoDBStorage
from service.src.models import Trace, Span


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
        output={"result": "success"},
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
