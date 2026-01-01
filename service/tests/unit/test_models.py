"""Unit tests for data models - focusing on custom validation logic.

Execute this file from the root directory, such that service/ module can be found
at 1st level of the search path.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from pydantic import ValidationError

from service.src.models import (
    Trace,
    Span,
    TraceCreate,
    SpanCreate,
    truncate_dict,
    truncate_string,
    MAX_METADATA_SIZE,
)


class TestTruncateDict:
    """Tests for truncate_dict helper - critical for DynamoDB size limits.
    
    This looks into a dict and truncates keys or nested keys if they exceed
    max_size limit. 
    Internally it calls _truncate_string_values() at relevant levels.
    This operates at all dict levels, trace, span, and also to keys within them.
    """

    def test_small_dict_unchanged(self):
        """Dict under size limit should pass through unchanged."""
        data = {"key": "value", "nested": {"a": 1}}
        result = truncate_dict(data, max_size=1000)

        assert result == data
        assert "_truncated" not in result

    def test_large_string_values_truncated(self):
        """Long string values should be truncated first."""
        large_text = "x" * 5000
        data = {"content": large_text, "keep": "small"}

        result = truncate_dict(data, max_size=2000)

        assert "_truncated" in result
        assert len(result["content"]) < len(large_text)
        assert result["keep"] == "small", "untouched data keys should remain unchanged"

    def test_nested_strings_truncated(self):
        """Nested string values should also be truncated."""
        data = {"outer": {"inner": "x" * 5000}}

        result = truncate_dict(data, max_size=2000)

        assert "_truncated" in result
        assert len(result["outer"]["inner"]) < 5000

    def test_drop_large_keys_when_truncation_insufficient(self):
        """Test dropping large keys when string truncation isn't enough.
        
        When string truncation isn't enough, keys should be dropped (Strategy 3).
        This tests _drop_large_keys() which replaces large values with
        '[dropped: N bytes]' markers when the dict is still too large after
        string truncation.
        """
        # Create data where even truncated strings won't fit in tiny limit
        data = {
            "small": [1, 2, 3, 4, 5],  # Non-string, can't be truncated
            "medium": [10, 20, 30, 40, 50],
            "large": list(range(100)),  # Largest value
        }

        # Very small limit forces key dropping
        result = truncate_dict(data, max_size=50)

        assert "_truncated" in result, "Should be present as keys were dropped"
        assert "_original_size" in result, "Should be present as keys were dropped"

        # At least one key should have been replaced with dropped marker
        dropped_markers = [
            v for v in result.values()
            if isinstance(v, str) and "[dropped:" in v
        ]
        assert len(dropped_markers) > 0, "At least one key should be dropped"

    def test_empty_dict_unchanged(self):
        """Empty dict should return as-is."""
        assert truncate_dict({}, max_size=100) == {}
        assert truncate_dict(None, max_size=100) is None


class TestTruncateString:
    """Tests for truncate_string helper.
    
    This mainly operated of string keys, like output, error, etc."""

    def test_short_string_unchanged(self):
        """String under limit should pass through."""
        result = truncate_string("short", max_length=100)
        assert result == "short"

    def test_long_string_truncated(self):
        """String over limit should be truncated with marker."""
        long_text = "x" * 500
        result = truncate_string(long_text, max_length=100)

        assert len(result) <= 100
        assert "truncated" in result, (
            "This keyword must be present in text to indicate to user."
        )

    def test_none_unchanged(self):
        """None should pass through."""
        assert truncate_string(None, max_length=100) is None


class TestDatetimeParsing:
    """Tests for datetime field parsing - handles multiple formats.
    
    Both Trace and SPan models share the same datetime parsing logic - via
    parse_datetime() validator. Test verify all supported formats.
    """

    def test_trace_datetime_parsing(self):
        """Test datetime parsing for Trace model."""
        base_trace = {
            "trace_id": "t1",
            "name": "test",
            "project_id": "proj",
        }
        now = datetime.now(timezone.utc)

        # Format 1: ISO string with Z suffix
        trace_z = Trace(**base_trace, start_time="2025-01-15T10:30:00Z")
        assert isinstance(trace_z.start_time, datetime)
        assert trace_z.start_time.tzinfo is not None, "should be timezone aware"
    
        # Format 2: ISO string with explicit offset
        trace_offset = Trace(**base_trace, start_time="2025-01-15T10:30:00+00:00")
        assert isinstance(trace_offset.start_time, datetime)
        
        # Format 3: Datetime object (passthrough)
        trace_dt = Trace(**base_trace, start_time=now)
        assert trace_dt.start_time == now, "datetime objects should passthrough"

        # Format 4: Invalid datetime string: should be gracefully handled, no crash
        trace_invalid = Trace(**base_trace, start_time="not-a-date")
        assert trace_invalid.start_time == "not-a-date", "invalid string kept as-is"
        
    def test_span_datetime_parsing(self):
        """Test datetime parsing for Span model."""
        base_span = {
            "span_id": "s1",
            "trace_id": "t1",
            "name": "test",
            "span_type": "llm",
        }
        now = datetime.now(timezone.utc)

        # Format 1: ISO string with Z suffix
        span_z = Span(**base_span, start_time="2025-01-15T10:30:00Z")
        assert isinstance(span_z.start_time, datetime)
        assert span_z.start_time.tzinfo is not None, "should be timezone aware"
    
        # Format 2: ISO string with explicit offset
        span_offset = Span(**base_span, start_time="2025-01-15T10:30:00+00:00")
        assert isinstance(span_offset.start_time, datetime)
        
        # Format 3: Datetime object (passthrough)
        span_dt = Span(**base_span, start_time=now)
        assert span_dt.start_time == now, "datetime objects should passthrough"

        # Format 4: Invalid datetime string: should be gracefully handled, no crash
        span_invalid = Span(**base_span, start_time="not-a-date")
        assert span_invalid.start_time == "not-a-date", "invalid string kept as-is"


class TestToDynamoDBItem:
    """Tests for to_dynamodb_item() conversion.
    
    Trace and Span pydantic objects have to_dynamodb_item() which converts
    them to a dictionary with proper types that can be used to create a 
    DynamoDB "Item".
    """

    def test_trace_to_dynamodb_item(self):
        """Test to_dynamodb_item() for Trace model."""
        base_trace = {
            "trace_id": "t1",
            "name": "test",
            "project_id": "proj",
        }
        now = datetime.now(timezone.utc)
        
        # Test 1: Datetime fields converted to ISO strings for dynamoDB
        trace = Trace(**base_trace, start_time=now, end_time=now)
        item = trace.to_dynamodb_item()
        
        assert isinstance(item["start_time"], str)
        assert isinstance(item["end_time"], str)
        assert "T" in item["start_time"], "Should be ISO format with T separator"

        # Test 2: None fields excluded from dynamoDB item
        trace_w_nones = Trace(
            **base_trace, start_time=now, end_time=None, output=None
        )
        item_w_nones = trace_w_nones.to_dynamodb_item()
        
        assert "end_time" not in item_w_nones
        assert "output" not in item_w_nones
        

    def test_span_to_dynamodb_item(self):
        """Test to_dynamodb_item() for Span model."""
        base_span = {
            "span_id": "s1",
            "trace_id": "t1",
            "name": "test",
            "span_type": "llm",
        }
        now = datetime.now(timezone.utc)

        # Test 1: Datetime field converted to ISO strings
        span = Span(**base_span, start_time=now, end_time=now)
        item = span.to_dynamodb_item()

        assert isinstance(item["start_time"], str)
        assert isinstance(item["end_time"], str)
        assert "T" in item["start_time"], "Should be ISO format with T separator"

        # Test 2: None fields excluded from dynamoDB item
        span_w_nones = Span(
            **base_span, start_time=now, end_time=None, error=None
        )
        item_w_nones = span_w_nones.to_dynamodb_item()
        
        assert "end_time" not in item_w_nones
        assert "error" not in item_w_nones

        # Test 3: cost_usd converted to Decimal
        span_w_cost = Span(**base_span, start_time=now, cost_usd=0.0025)
        item_w_cost = span_w_cost.to_dynamodb_item()
        
        assert isinstance(item_w_cost["cost_usd"], Decimal), "cost_usd should be Decimal."
        assert item_w_cost["cost_usd"] == Decimal("0.0025"), "Decimal value should match."


class TestSpanTypeValidation:
    """Tests for span_type regex validation.
    
    This is mainly to allow strictly matching key words for filtering spans.
    """

    @pytest.mark.parametrize("valid_type", [
        "llm", "tool", "agent", "function",
        "retrieval", "embedding", "chain", "other"
    ])
    def test_valid_span_types(self, valid_type):
        """All documented span types should be accepted."""
        span = SpanCreate(name="test", span_type=valid_type)
        assert span.span_type == valid_type, "Span type should match."

    def test_invalid_span_type_rejected(self):
        """Invalid span type should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SpanCreate(name="test", span_type="invalid")

        assert "span_type" in str(exc_info.value), "Error should be raised here for invalid span_type."


class TestProjectIdValidation:
    """Tests for project_id pattern validation.
    
    Since project_id if used for filtering and must also be part of auth_api, we
    do not allow characters that could be problematic. 
    """

    @pytest.mark.parametrize("valid_id", [
        "myproject",
        "my-project",
        "my_project",
        "Project123",
        "a",
        "test-project-123",
    ])
    def test_valid_project_ids(self, valid_id):
        """Alphanumeric with hyphens/underscores should work."""
        trace = TraceCreate(name="test", project_id=valid_id)
        assert trace.project_id == valid_id

    @pytest.mark.parametrize("invalid_id", [
        "my project",   # space
        "my.project",   # dot
        "my@project",   # special char
        "",             # empty
    ])
    def test_invalid_project_ids_rejected(self, invalid_id):
        """Invalid characters should raise ValidationError."""
        with pytest.raises(ValidationError):
            TraceCreate(name="test", project_id=invalid_id)


class TestTagValidation:
    """Tests for tags field validation.
    
    There is a hidden validator which cuts any single tag among the list of tags, if
    its length exceeds 100 characters. This happens at TraceCreate model.
    """

    def test_long_tags_truncated(self):
        """Tags over 100 chars should be truncated."""
        long_tag = "x" * 150
        trace = TraceCreate(name="test", project_id="proj", tags=[long_tag])

        assert len(trace.tags[0]) == 100

    def test_empty_tags_filtered(self):
        """Empty/whitespace tags should be removed."""
        trace = TraceCreate(
            name="test",
            project_id="proj",
            tags=["valid", "", "  ", "also-valid"]
        )

        assert trace.tags == ["valid", "also-valid"]


class TestMetadataTruncation:
    """Tests for automatic metadata truncation on models.
    
    Checking not so obvious metadata validators - at Trace and Span creations."""

    def test_large_metadata_truncated_on_trace_create(self):
        """TraceCreate should truncate oversized metadata."""
        large_metadata = {"content": "x" * (MAX_METADATA_SIZE + 1000)}

        trace = TraceCreate(
            name="test",
            project_id="proj",
            metadata=large_metadata,
        )

        # Should not raise, should truncate
        assert "_truncated" in trace.metadata, "failed to truncate metadata on TraceCreate."

    def test_large_input_data_truncated_on_span(self):
        """Span should truncate oversized input_data."""
        large_data = {"prompt": "x" * 100_000}

        span = Span(
            span_id="s1",
            trace_id="t1",
            name="test",
            span_type="llm",
            start_time=datetime.now(timezone.utc),
            input_data=large_data,
        )

        assert "_truncated" in span.input_data, "failed to truncate metadata on Span."
