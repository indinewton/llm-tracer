"""Data models for tracing service"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict
import json
import logging

logger = logging.getLogger(__name__)

# DynamoDB item sioze limit is 400KB, we use conservative limits
MAX_METADATA_SIZE = 10_000  # 10 KB
MAX_INPUT_OUTPUT_SIZE = 50_000  # 50 KB
MAX_STRING_LENGTH = 10_000  # 10 KB for output/ error strings
MAX_ITEM_SIZE = 350_000  # 350 KB for safety margin for full_item


def truncate_dict(
    data: Dict,
    max_size: int,
    field_name: str = "data",
) -> Dict:
    """Truncate a dictionary to fit within a maximum size in bytes.
    
    Strategies:
    1. Try to serialize as-is.
    2. If too large, truncate string values. This will start addressing Output and Input tokens.
    3. If still too large, remove largest keys until it fits.

    Parameters
    ----------
    data : Dict
        The dictionary to truncate.
    max_size : int
        The maximum size in bytes.
    field_name : str
        The name of the field being truncated, needed only for logging.
    """
    # if empty or none, just return the same back
    if not data:
        return data
    
    serialized = json.dumps(data, default=str)
    # Strategy 1: Try to serialize as-is
    if len(serialized) <= max_size:
        return data
    
    logger.warning(
        f"Truncating {field_name} to fit within size limit of {max_size} bytes"
    )

    # Strategy 2: Truncate string values
    truncated = _truncate_string_values(data.copy(), max_size)
    if len(json.dumps(truncated, default=str)) <= max_size:
        truncated["_truncated"] = True
        return truncated
    
    # Strategy 3: Remove largest keys until it fits
    truncated = _drop_large_keys(data.copy(), max_size)
    truncated["_truncated"] = True
    truncated["_original_size"] = len(serialized)
    return truncated


def _truncate_string_values(
    data: Dict,
    max_size: int,
    max_str_len: int = 1000
) -> Dict:
    """Recursively truncate string values in a dictionary."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str) and len(value) > max_str_len:
            result[key] = value[:max_str_len] + f"... [truncated, was {len(value)} chars]"
        elif isinstance(value, dict):
            result[key] = _truncate_string_values(value, max_size, max_str_len)
        elif isinstance(value, list):
            result[key] = [
                _truncate_string_values(v, max_size, max_str_len) if isinstance(v, dict)
                else (
                    v[:max_str_len] + "..." if isinstance(v, str) and len(v) > max_str_len
                    else v
                )
                for v in value
            ]
        else:
            result[key] = value
    return result


def _drop_large_keys(data: Dict, max_size: int) -> Dict:
    """Remove largest keys by VALUE size until dict fits within max_size."""
    result = data.copy()
    dropped_keys = set()

    while len(json.dumps(result, default=str)) > max_size and result:
        # Find key with largest VALUE that hasn't been dropped yet
        droppable_keys = [k for k in result.keys() if k not in dropped_keys]
        # All keys already dropped, but if we can't shrink further, just break
        if not droppable_keys:
            # Normally, dynamodb has gracious limits set, but someone can create a test case
            # to hit this limit and if not forced to break - goes to infinite loop.
            break

        largest_key = max(
            droppable_keys,
            key=lambda k: len(json.dumps(result[k], default=str))
        )
        dropped_size = len(json.dumps(result[largest_key], default=str))
        result[largest_key] = f"[dropped: {dropped_size} bytes]"
        dropped_keys.add(largest_key)

    return result
        

def truncate_string(
    value: Optional[str],
    max_length: int,
    field_name: str = "string"
) -> Optional[str]:
    """Truncate a string to fit within a maximum length."""
    if not value:
        return value
    if len(value) <= max_length:
        return value

    logger.warning(f"Truncating {field_name}: {len(value)} chars -> {max_length} chars")
    return value[:max_length - 50] + f"\n... [truncated, was {len(value)} chars]"


def stringify_metadata(data: Optional[Dict]) -> Optional[Dict]:
    """Convert metadata dict values to strings for DynamoDB compatibility.

    DynamoDB does not support Python floats and other base types.
    We convert all values to strings to ensure compatibility.
    """
    if not data:
        return data
    return {k: str(v) for k, v in data.items()}


class TraceCreate(BaseModel):
    """Request model for creating a trace"""

    name: str = Field(..., min_length=1, max_length=255)
    project_id: str = Field(..., min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    tags: Optional[List[str]] = Field(default_factory=list, max_items=50)
    user_id: Optional[str] = Field(None, max_length=255)
    session_id: Optional[str] = Field(None, max_length=255)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> List[str]:
        """Sanitize and limit tag length"""
        if v:
            return [tag[:100] for tag in v if tag.strip()]  # Limit tag length
        return []
    
    @field_validator("metadata")
    @classmethod
    def truncate_metadata(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Stringify and truncate metadata for DynamoDB compatibility."""
        if not v:
            return v
        v = stringify_metadata(v)
        return truncate_dict(v, MAX_METADATA_SIZE, "trace.metadata")


class Trace(BaseModel):
    """Complete trace object - DynamoDB Compatible"""

    model_config = ConfigDict(
        populate_by_name=True,  # For accepting aliases defined in Field; you can define camelCase as alias for snake_case
        json_encoders={datetime: lambda v: v.isoformat()},  # Tells pydantic how to encode datetime objects when dumping to JSON
    )

    trace_id: str
    name: str
    project_id: str
    start_time: Union[str, datetime]
    end_time: Optional[Union[str, datetime]] = None
    duration_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    tags: Optional[List[str]] = Field(default_factory=list)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    output: Optional[str] = None
    # Denormalized fields for efficient querying (updated when spans are created/completed)
    span_count: int = 0
    total_cost: Optional[float] = None

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        """Parse datetime from string if needed."""
        if v is None:
            return v
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                # input like: "2025-12-13T01:04:27Z" -> "2025-12-13T01:04:27+00:00"
                # trailing Z is shorthand for UTC, that datetime does not understand.
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                # Instead of raising error, we keep it as-is, to avoid crashing main
                # application.
                return v
        return v
    
    @field_validator("output")
    @classmethod
    def truncate_output(cls, v: Optional[str]) -> Optional[str]:
        """Truncate output to fit DynamoDB item size limit
        
        Note: Purpose of trace is NOT to store outputs of LLM, rather its performance metrics.
        Hence, we truncate to max size of 1000 characters.
        """
        if not v:
            return v
        return truncate_string(v, MAX_STRING_LENGTH, "trace.output")
    
    @field_validator("metadata")
    @classmethod
    def truncate_metadata(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Stringify and truncate metadata for DynamoDB compatibility."""
        if not v:
            return v
        v = stringify_metadata(v)
        return truncate_dict(v, MAX_METADATA_SIZE, "trace.metadata")

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB compatible Dictionary."""
        item = self.model_dump(exclude_none=True)
        if isinstance(item.get("start_time"), datetime):
            item["start_time"] = item["start_time"].isoformat()
        if isinstance(item.get("end_time"), datetime):
            item["end_time"] = item["end_time"].isoformat()
        # Convert total_cost float to Decimal for DynamoDB
        if item.get("total_cost") is not None:
            item["total_cost"] = Decimal(str(item["total_cost"]))

        return item


class SpanCreate(BaseModel):
    """Request model for creating a span - auto-truncates large data."""
    
    name: str = Field(..., min_length=1, max_length=255)
    span_type: str = Field(..., pattern=r'^(llm|tool|agent|function|retrieval|embedding|chain|other)$')
    parent_span_id: Optional[str] = Field(None, max_length=100)
    input_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    model: Optional[str] = Field(None, max_length=255)
    tokens_input: Optional[int] = Field(None, ge=0)
    tokens_output: Optional[int] = Field(None, ge=0)
    cost_usd: Optional[float] = Field(None, ge=0)
    error: Optional[str] = None

    @field_validator("input_data")
    @classmethod
    def truncate_input_data(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Truncate input data to fit DynamoDB item size limit"""
        if not v:
            return v
        return truncate_dict(v, MAX_INPUT_OUTPUT_SIZE, "span.input_data")

    @field_validator("output_data")
    @classmethod
    def truncate_output_data(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Truncate output data to fit DynamoDB item size limit"""
        if not v:
            return v
        return truncate_dict(v, MAX_INPUT_OUTPUT_SIZE, "span.output_data")

    @field_validator("metadata")
    @classmethod
    def truncate_metadata(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Stringify and truncate metadata for DynamoDB compatibility."""
        if not v:
            return v
        v = stringify_metadata(v)
        return truncate_dict(v, MAX_METADATA_SIZE, "span.metadata")


class Span(BaseModel):
    """Complete span object - DynamoDB Compatible"""
    
    model_config = ConfigDict(
        populate_by_name=True,  
        json_encoders={datetime: lambda v: v.isoformat()},  
    )
    
    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    name: str
    span_type: str  # 'llm', 'tool', 'agent', 'function', etc.
    start_time: Union[str, datetime]
    end_time: Optional[Union[str, datetime]] = None
    duration_ms: Optional[int] = None
    input_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    model: Optional[str] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None
    
    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        """Parse datetime from string if needed."""
        if v is None:
            return v
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return v
        return v
    
    @field_validator("input_data")
    @classmethod
    def truncate_input_data(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Truncate input data to fit DynamoDB item size limit"""
        if not v:
            return v
        return truncate_dict(v, MAX_INPUT_OUTPUT_SIZE, "span.input_data")

    @field_validator("output_data")
    @classmethod
    def truncate_output_data(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Truncate output data to fit DynamoDB item size limit"""
        if not v:
            return v
        return truncate_dict(v, MAX_INPUT_OUTPUT_SIZE, "span.output_data")

    @field_validator("error")
    @classmethod
    def truncate_error(cls, v: Optional[str]) -> Optional[str]:
        """Truncate error message"""
        return truncate_string(v, MAX_STRING_LENGTH, "span.error")

    @field_validator("metadata")
    @classmethod
    def truncate_metadata(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Stringify and truncate metadata for DynamoDB compatibility."""
        if not v:
            return v
        v = stringify_metadata(v)
        return truncate_dict(v, MAX_METADATA_SIZE, "span.metadata")

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB compatible Dictionary.

        - Converts datetime to ISO string
        - Converts cost_usd float to Decimal
        - Stringifies all values in input_data and output_data for compatibility
        """
        # Import here to avoid circular import
        from .storage_dynamodb import stringify_for_dynamodb

        item = self.model_dump(exclude_none=True)
        if isinstance(item.get("start_time"), datetime):
            item["start_time"] = item["start_time"].isoformat()
        if isinstance(item.get("end_time"), datetime):
            item["end_time"] = item["end_time"].isoformat()
        if item.get("cost_usd") is not None:
            item["cost_usd"] = Decimal(str(item["cost_usd"]))
        # Stringify input_data and output_data to handle floats and other types
        if item.get("input_data"):
            item["input_data"] = stringify_for_dynamodb(item["input_data"])
        if item.get("output_data"):
            item["output_data"] = stringify_for_dynamodb(item["output_data"])

        return item


class TraceQuery(BaseModel):
    """Query parameters for filtering traces from DynamoDB"""
    
    project_id: str = Field(..., description="Project ID (required) to support multiple projects")
    limit: int = Field(default=50, ge=1, le=1000)
    cursor: Optional[str] = Field(None, description="Cursor for pagination")
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Optional[List[str]] = None
    start_time_from: Optional[str] = None
    start_time_to: Optional[str] = None


class TraceListResponse(BaseModel):
    """Response model for paginated trace list."""

    traces: List[Trace]
    next_cursor: Optional[str] = None
    has_more: bool = False
    count: int


class SpanCompleteRequest(BaseModel):
    """Request model for completing a span - auto truncates."""

    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tokens_input: Optional[int] = Field(None, ge=0)
    tokens_output: Optional[int] = Field(None, ge=0)
    cost_usd: Optional[float] = Field(None, ge=0)
    metdata: Optional[Dict[str, Any]] = None

    @field_validator("output_data")
    @classmethod
    def truncate_output_data(cls, v: Optional[Dict]) -> Optional[Dict]:
        """Truncate output data to fit DynamoDB item size limit"""
        if not v:
            return v
        return truncate_dict(v, MAX_INPUT_OUTPUT_SIZE, "SpanCompleteRequest.output_data")
    
    @field_validator("error")
    @classmethod
    def truncate_error(cls, v: Optional[str]) -> Optional[str]:
        """Truncate error message"""
        return truncate_string(v, MAX_STRING_LENGTH, "SpanCompleteRequest.error")


class TraceCompleteRequest(BaseModel):
    """Request model for completing a trace - auto truncates."""

    output: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("output")
    @classmethod
    def truncate_output(cls, v: Optional[str]) -> Optional[str]:
        """Truncate output to fit DynamoDB item size limit"""
        return truncate_string(v, MAX_STRING_LENGTH, "TraceCompleteRequest.output")
