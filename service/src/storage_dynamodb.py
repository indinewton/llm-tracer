"""DynamoDB storage backend for LLM tracer."""

import os
import time
import logging
import base64
import json
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .models import Trace, Span, TraceQuery

logger = logging.getLogger(__name__)


class DynamoDBStorage:
    """DynamoDB storage backend for traces and spans"""

    def __init__(
        self,
        traces_table_name: Optional[str] = None,
        spans_table_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        """Initialize DynamoDB storage backend
        
        Parameters
        ----------
        traces_table_name : Optional[str]
            The name of the traces table. If not provided, the value of the DYNAMODB_TRACES_TABLE environment variable is used.
        spans_table_name : Optional[str]
            The name of the spans table. If not provided, the value of the DYNAMODB_SPANS_TABLE environment variable is used.
        endpoint_url : Optional[str]
            The endpoint URL for the DynamoDB service. If not provided, the value of the DYNAMODB_ENDPOINT_URL environment variable is used.
        region_name : Optional[str]
            The region name for the DynamoDB service. If not provided, the value of the AWS_REGION environment variable is used.
        
        """
        self.traces_table_name = traces_table_name or os.getenv(
            "DYNAMODB_TRACES_TABLE", "llm-tracer-dev-traces"
        )
        self.spans_table_name = spans_table_name or os.getenv(
            "DYNAMODB_SPANS_TABLE", "llm-tracer-dev-spans"
        )
        # For local testing with DynamoDB Local
        self.endpoint_url = endpoint_url or os.getenv("DYNAMODB_ENDPOINT_URL")
        self.region_name = region_name or os.getenv("AWS_REGION", "eu-central-1")

        # Create dynamodb resource
        kwargs = {"region_name": self.region_name}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
            # For local testing
            kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "test")
            kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "test")


        self.dynamodb = boto3.resource("dynamodb", **kwargs)
        self.traces_table = self.dynamodb.Table(self.traces_table_name)
        self.spans_table = self.dynamodb.Table(self.spans_table_name)

        logger.info(
            f"DynamoDB Storage initialized: traces = {self.traces_table_name}, "
            f"spans = {self.spans_table_name}, "
            f"region_name = {self.region_name}"
        )

    def get_type(self) -> str:
        """Return storage type identifier"""
        return "dynamodb"

    def _add_ttl(self, item: Dict, days: int = 90) -> Dict:
        """Add TTL (Time to Live) to item for auto-deletion.
        
        Parameters
        ----------
        item : Dict
            The item to add TTL to.
        days : int, optional
            The number of days until deletion, by default 90.
        
        Returns
        -------
        Dict
            The item with TTL field added.
        """
        ttl = int(time.time()) + (days * 24*60*60)
        item["ttl"] = ttl
        return item
    
    def _validate_datetime(
        self,
        value: Union[str, datetime],
        field_name: str,
    ) -> datetime:
        """Validate and normalize datetime input.
        
        Accepts:
        - datetime object with UTC timezone (recommended)
        - datetime object with any timezone (will be used as-is)
        - ISO format string (will be parsed)

        Parameters
        ----------
        value : Union[str, datetime]
            The datetime value to validate and normalize.
        field_name : str
            The name of the field being validated.
        
        Returns
        -------
        datetime
            validated datetime object
        
        Raises
        ------
        ValueError
            If the value is not a valid datetime format.

        Examples
        --------
        Valid inputs:
          - datetime.now(timezone.utc)
          - datetime(2025, 1, 1, tzinfo=timezone.utc)
          - "2025-01-01T00:00:00+00:00"
          - "2025-01-01T00:00:00Z"

        Invalid inputs:
          - "2025-01-01" (no time component)
          - "not a date"
          - 1234567890 (timestamp int)
        """
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError(
                    f"{field_name}: datetime must be timezone-aware. "
                    f"Use datetime.now(timezone.utc) instead of datetime.now()."
                )
            return value
        
        if isinstance(value, str):
            try:
                # handle 'Z' suffix for UTC
                normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
                return datetime.fromisoformat(normalized)
            except ValueError as e:
                raise ValueError(
                    f"{field_name}: Invalid ISO format string '{value}'. "
                    f"Expected format: 'YYYY-MM-DDTHH:MM:SS+00:00' or 'YYYY-MM-DDTHH:MM:SSZ'. "
                    f"Parse error: {e}"
                )
        
        raise ValueError(
            f"Invalid datetime format for {field_name}, got {type(value).__name__}"
        )


    async def save_trace(self, trace: Trace) -> str:
        """Save a trace to DynamoDB.
        
        Parameters
        ----------
        trace : Trace
            The Trace model object to save.
        
        Returns
        -------
        str
            The trace ID
        """
        # Validate first whether datetime fields are valid
        self._validate_datetime(trace.start_time, "trace.start_time")
        if trace.end_time is not None:
            self._validate_datetime(trace.end_time, "trace.end_time")
        # Use model's serialisation method
        trace_dict = trace.to_dynamodb_item()

        # Add TTL for auto-deletion after 90 days
        trace_dict = self._add_ttl(trace_dict)

        # put item in dynamodb
        self.traces_table.put_item(Item=trace_dict)
        
        logger.debug(f"Saved trace: {trace_dict['trace_id']}")
        return trace_dict['trace_id']
    
    async def get_trace(
        self,
        trace_id: str,
        project_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Get a trace by ID
        
        Parameters
        ----------
        trace_id : str
            The trace ID to get.
        project_id : Optional[str]
            The project ID for security check. One table should not have more than 1 project_id.
        
        Returns
        -------
        Optional[Dict]
            The trace data dictionary if found, None otherwise.
        """
        try:
            response = self.traces_table.get_item(Key={"trace_id": trace_id})
            item = response.get("Item")
            if not item:
                return None
            
            # Security check: verify project ownership
            if project_id and item.get("project_id") != project_id:
                logger.warning(
                    f"Access Denied: trace {trace_id} belongs to project "
                    f"{item.get('project_id')}, not {project_id}"
                )
                return None

            # Remove TTL field from response (internal field)
            item.pop('ttl', None)
            return item
        
        except ClientError as e:
            logger.error(f"Error getting trace {trace_id}: {e}")
            return None

    async def get_traces(self, query: TraceQuery) -> List[Dict]:
        """Query traces with filters.

        Parameters
        ----------
        query : TraceQuery
            TraceQuery object with project_id, limit, cursor, filters

        Returns
        -------
        Dict
            Dict with 'items' (list of traces) and 'next_cursor' (for pagination)
        """
        try:
            query_kwargs = {
                "IndexName": "project-time-index",
                "KeyConditionExpression": Key("project_id").eq(query.project_id),
                "ScanIndexForward": False,  # Newest first
                "Limit": query.limit,
            }

            # Handel cursor (LastEvaluatedKey from previous query)
            if query.cursor:
                try:
                    decoded = base64.b64decode(query.cursor).decode("utf-8")
                    query_kwargs["ExclusiveStartKey"] = json.loads(decoded)
                except Exception as e:
                    pass  # Invalid cursor, start from the beginning

            response = self.traces_table.query(**query_kwargs)
            items = response.get("Items", [])
            
            # Remove TTL from all items
            for item in items:
                item.pop("ttl", None)
            
            # Apply optional filters (post-query filtering)
            if query.user_id:
                items = [i for i in items if i.get("user_id") == query.user_id]
            
            if query.session_id:
                items = [i for i in items if i.get("session_id") == query.session_id]
            
            if query.tags:
                items = [
                    i for i in items
                    if any(tag in i.get("tags", []) for tag in query.tags)
                ]
            
            # Build next cursor from LastEvaluatedKey
            next_cursor = None
            last_key = response.get("LastEvaluatedKey")
            if last_key:
                next_cursor = base64.b64encode(json.dumps(last_key).encode()).decode()
            
            return {
                "items": items,
                "next_cursor": next_cursor,
            }
        
        except ClientError as e:
            logger.error(f"Error querying traces for project {query.project_id}: {e}")
            return {"items": [], "next_cursor": None}

    async def complete_trace(
        self,
        trace_id: str,
        end_time: datetime,
        output: Optional[str] = None,
    ) -> bool:
        """Update a trace as to be completed..

        Parameters
        ----------
        trace_id : str
            The trace ID to update.
        end_time : datetime
            Completion timestamp.
        output : Optional[str]
            Final output.

        Returns
        -------
        bool
            True if the trace was updated.
        
        Usage
        -----
        ```python
        from datetime import datetime, timezone
        
        await storage.complete_trace(
            trace_id="trace-xyz-456",
            end_time=datetime.now(timezone.utc),
            output="Trace output string"
        )
        ```
        Generated DynamoDB Args that are then used to update the trace in DynamoDB.
        ```json
        {
            "Key": {
                "trace_id": "trace-xyz-456"
            },
            "UpdateExpression": "SET end_time = :end_time, duration_ms = :duration_ms, output = :output",
            "ExpressionAttributeValues": {
                ":end_time": "2025-12-13T01:37:35.123456+00:00",
                ":duration_ms": 1500,
                ":output": "Trace output string"
            }
        }
        ```
        """
        # first check if end_time passed is valid
        end_time = self._validate_datetime(end_time, "end_time")

        try:
            # Get current trace to calculate duration
            trace = await self.get_trace(trace_id)
            if not trace:
                logger.error(f"Trace {trace_id} not found")
                return False
            
            # Calculate duration
            start_time_str = trace['start_time']
            if start_time_str.endswith("Z"):
                start_time_str = start_time_str.replace("Z", "+00:00")
            start_time = datetime.fromisoformat(start_time_str)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Build update expression
            update_expr = "SET end_time = :end_time, duration_ms = :duration_ms"
            expr_attr_values = {
                ":end_time": end_time.isoformat(),
                ":duration_ms": duration_ms,
            }

            if output:
                update_expr += ", output = :output"
                expr_attr_values[":output"] = output


            # Update trace
            self.traces_table.update_item(
                Key={"trace_id": trace_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_attr_values,
            )

            logger.debug(f"Completed trace: {trace_id} (duration: {duration_ms} ms)")
            return True

        except Exception as e:
            logger.error(f"Error updating trace {trace_id}: {e}")
            return False


    async def save_span(self, span: Span) -> str:
        """Save a span to DynamoDB.
        
        Parameters
        ----------
        span : Span
            The Span model object to save.
        
        Returns
        -------
        str
            The span ID
        """
        # Validate datetime format in Span object
        self._validate_datetime(span.start_time, "span.start_time")
        if span.end_time is not None:
            self._validate_datetime(span.end_time, "span.end_time")

        # Use model's serialisation method (handles Decimal conversion for cost_usd)
        span_dict = span.to_dynamodb_item()
        
        # Add TTL for auto-deletion
        span_dict = self._add_ttl(span_dict)

        # put item in dynamodb
        self.spans_table.put_item(Item=span_dict)
        
        logger.debug(f"Saved span: {span_dict['span_id']}")
        return span_dict['span_id']

    async def get_span(self, span_id: str) -> Optional[Dict]:
        """Get a span by ID
        
        Parameters
        ----------
        span_id : str
            The span ID to get.
        
        Returns
        -------
        Optional[Dict]
            The span data dictionary if found, None otherwise.
        """
        try:
            response = self.spans_table.get_item(Key={"span_id": span_id})
            item = response.get("Item")
            if item:
                # Remove TTL field from response (internal field)
                item.pop('ttl', None)
        
            return item

        except ClientError as e:
            logger.error(f"Error getting span {span_id}: {e}")
            return None

    async def get_spans(
        self,
        trace_id: str,
        project_id: Optional[str] = None,
    ) -> List[Dict]:
        """Get all spans for a trace.
        
        Parameters
        ----------
        trace_id : str
            The trace ID to get spans for.
        project_id : Optional[str]
            The project ID to filter spans by. If None, returns all spans for the trace.
        
        Returns
        -------
        List[Dict]
            A list of span dictionaries.
        """
        try:
            # Verify trace ownership if project_id is provided
            if project_id:
                trace = await self.get_trace(trace_id, project_id)
                if not trace:
                    return []
            
            # Query using trace-index GSI
            response = self.spans_table.query(
                IndexName="trace-index",
                KeyConditionExpression=Key("trace_id").eq(trace_id)
            )
            items = response["Items"]

            for item in items:
                # Remove TTL field from response (internal field)
                item.pop('ttl', None)
            
            return items

        except ClientError as e:
            logger.error(f"Error getting spans for trace {trace_id}: {e}")
            return []


    async def complete_span(
        self,
        span_id: str,
        end_time: datetime,
        output_data: Optional[Dict] = None,
        error: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
    ) -> bool:
        """Update a span.
        
        Parameters
        ----------
        span_id : str
            The span ID to update.
        end_time : datetime
            The end time of the span.
        output_data : Optional[Dict]
            The output data of the span.
        error : Optional[str]
            The error of the span.
        tokens_input : Optional[int]
            The number of input tokens.
        tokens_output : Optional[int]
            The number of output tokens.
        
        Returns
        -------
        bool
            True if the span was updated.

        """
        # Check if end_time is valid
        end_time = self._validate_datetime(end_time, "end_time")

        try:
            # Get current span to calculate duration
            response = self.spans_table.get_item(Key={"span_id": span_id})
            span = response.get("Item")

            if not span:
                logger.error(f"Span {span_id} not found")
                return False
            
            # calculate duration
            start_time_str = span["start_time"]
            if start_time_str.endswith("Z"):
                start_time_str = start_time_str.replace("Z", "+00:00")
            
            start_time = datetime.fromisoformat(start_time_str)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            
            # Build update expression
            update_parts = ["end_time = :end_time", "duration_ms = :duration_ms"]
            expr_attr_values = {
                ":end_time": end_time.isoformat(),
                ":duration_ms": duration_ms,
            }
            expr_attr_names = {}
            
            if output_data is not None:
                update_parts.append("output_data = :output_data")
                expr_attr_values[":output_data"] = output_data
            
            if error is not None:
                update_parts.append("#error_field = :error")
                expr_attr_values[":error"] = error
                expr_attr_names["#error_field"] = "error"  # error is a reserved keyword in DynamoDB
            
            if tokens_input is not None:
                update_parts.append("tokens_input = :tokens_input")
                expr_attr_values[":tokens_input"] = tokens_input
            
            if tokens_output is not None:
                update_parts.append("tokens_output = :tokens_output")
                expr_attr_values[":tokens_output"] = tokens_output
            
            update_expr = "SET " + ", ".join(update_parts)
            
            kwargs = {
                "Key": {"span_id": span_id},
                "UpdateExpression": update_expr,
                "ExpressionAttributeValues": expr_attr_values,
            }

            if expr_attr_names:
                kwargs["ExpressionAttributeNames"] = expr_attr_names

            self.spans_table.update_item(**kwargs)
            logger.debug(f"Completed span: {span_id} (duration: {duration_ms} ms)")
            return True
        
        except ClientError as e:
            logger.error(f"Error completing span {span_id}: {e}")
            return False
    
    async def get_stats(self, project_id: str) -> Dict:
        """Get stats for a project."""
        try:
            # Query traces for project (count only)
            traces_response = self.traces_table.query(
                IndexName="project-time-index",
                KeyConditionExpression=Key("project_id").eq(project_id),
                Select="COUNT",
            )
            total_traces = traces_response.get("Count", 0)

            # Get recent traces to calculate span stats
            query = TraceQuery(project_id=project_id, limit=50)
            recent_result = await self.get_traces(query)
            recent_traces = recent_result.get("items", [])

            total_spans = 0
            total_tokens = 0
            total_cost = 0.0

            for trace in recent_traces:
                spans = await self.get_spans(trace["trace_id"])
                total_spans += len(spans)

                for span in spans:
                    total_tokens += (span.get("tokens_input") or 0) + (span.get("tokens_output") or 0)
                    cost = span.get("cost_usd")
                    if cost:
                        total_cost += float(cost)

            return {
                "total_traces": total_traces,
                "total_spans": total_spans,
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 4),
            }

        except ClientError as e:
            logger.error(f"Error getting stats for project {project_id}: {e}")
            return {
                "total_traces": 0,
                "total_spans": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
            }
