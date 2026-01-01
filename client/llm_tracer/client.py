"""
Lightweight tracing client for integration with any LLM application

Design Principles:
- Non-Intrusive: Never block the main application workflow
- Graceful degradation: Failures are logged as warning, not raised
- Easy to use: Context managers handle all lifecycle management arounda Trace
- Production readiness to any project: Proper output/error capture, nested spans, cost tracking.

NOTE: Due to limitation on DynamoDB size (~400kb), longer outputs could be truncated for
such traces. If you need to capture Outputs and intermediated tokens, consider saving the response
from LLMs in some database that has generous limits.
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
import httpx
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True), override=True)

logger = logging.getLogger(__name__)


class SpanContext:
    """Context object for span operations.

    Provides methods to set output, error, and token usage within the span's
    lifecycle. All data is sent to server when the context exists.

    Attributes
    ----------
        span_id: str
            Unique identifier for the span
        trace_id: str
            Unique identifier for the trace
        parent_span_id: str
            Unique identifier for the parent span (for nested spans)
    """

    def __init__(
        self,
        client: "TracerClient",
        span_id: Optional[str],  # Required, but can be passed None.
        trace_id: str,
        parent_span_id: Optional[str] = None,
    ):
        self._client = client
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_span_id = parent_span_id

        # Data to send on completion of span after LLM has finished its response
        self._output_data: Optional[Dict[str, Any]] = None
        self._error: Optional[str] = None
        self._tokens_input: Optional[int] = None
        self._tokens_output: Optional[int] = None
        self._cost_usd: Optional[float] = None
    
    def set_output(
        self,
        output_data: Optional[Dict[str, Any]] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Set span output data and metrics.

        Call this before the span context exits to record the operation's results.

        Parameters
        ----------
        output_data: Optional[Dict[str, Any]]
            Output data of the operation.
        tokens_input: Optional[int]
            Number of tokens used as input to the operation.
        tokens_output: Optional[int]
            Number of tokens used as output to the operation.
        cost_usd: Optional[float]
            Cost of the operation in USD (for LLM spans)
        
        Examples
        --------
            ```python
            # just an analogy of calling any LLM; this is non-functional example
            async with trace.span("llm-call", "llm") as span:
                response = await llm.complete(prompt)  
                span.set_output(
                    output_data={"content": response.text},
                    tokens_input=response.usage.prompt_tokens,
                    tokens_output=response.usage.completion_tokens,
                    cost_usd=calculate_cost(response)
                )
            ```
        """
        self._output_data = output_data
        self._tokens_input = tokens_input
        self._tokens_output = tokens_output
        self._cost_usd = cost_usd

    def set_error(self, error: str) -> None:
        """Set and mark span failed with error message..

        Parameters
        ----------
        error: str
            Error message of the operation or exception string.
        
        Examples
        --------
            ```python
            # just an analogy of calling any LLM; this is non-functional example
            async with trace.span("api-call", "tool") as span:
                try:
                    result = await external_api.call() 
                except Exception as e:
                    span.set_error(str(e))
                    raise
            ```
        """
        self._error = error
    
    @asynccontextmanager
    async def span(
        self,
        name: str,
        span_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ):
        """Create a nested child span under this span.

        Use this for sub-operations within a parent operation.

        Parameters
        ----------
        name: str
            Name of the span, should be human-readable.
        span_type: str
            Type of the span allowed: (llm, tool, agent, function, retrieval, embedding, chain, other)
            Any other type will likely throw an error as this is regex verified on server side.
        input_data: Optional[Dict[str, Any]]
            Input data of the operation.
        metadata: Optional[Dict[str, Any]]
            Metadata of the operation.
        model: Optional[str]
            Model used for the operation.
        
        Examples
        --------
            ```python
            # just an analogy of calling any LLM; this is non-functional example
            async with trace.span("data-processing", "agent") as parent:
                async with parent.span("data-fetch", "tool") as child:
                    data = await fetch()
                    child.set_output(output_data={"records":len(data)})
            ```        
        """
        child_context = SpanContext(
            client=self._client,
            span_id=None,
            trace_id=self.trace_id,
            parent_span_id=self.span_id
        )

        if self._client.enabled and self.span_id:
            child_span_id = await self._client.create_span(
                trace_id=self.trace_id,
                name=name,
                span_type=span_type,
                input_data=input_data,
                metadata=metadata,
                model=model,
                parent_span_id=self.span_id,
            )
            child_context.span_id = child_span_id
        
        try:
            yield child_context

        except Exception as e:
            child_context._error = str(e)
            raise
        
        finally:
            if child_context.span_id:
                await self._client.complete_span(
                    span_id=child_context.span_id,
                    output_data=child_context._output_data,
                    error=child_context._error,
                    tokens_input=child_context._tokens_input,
                    tokens_output=child_context._tokens_output,
                    cost_usd=child_context._cost_usd,
                )


class TraceContext:
    """Context object for trace operations.

    A trace is one full operation of one request. A trace can have multiple spans.
    This provides methods to create spans and set trace output within trace's lifecycle.
    
    NOTE: All spans created through this context are automatically associated with this trace.
    So that one doesn't need to pass trace_id for each span creation.

    Attributes
    ----------
    trace_id: str
        Unique Trace ID of the trace.
    """

    def __init__(
        self,
        client: "TracerClient",
        trace_id: str,
    ):
        self._client = client
        self.trace_id = trace_id
        self._output: Optional[str] = None
    
    def set_output(self, output: str) -> None:
        """Set the output of the trace.

        Parameters
        ----------
        output: str
            Output of the trace.
        
        Examples
        --------
            ```python
            # This is a non functional example, just to show how to use this method.
            async with tracer.trace("user_query) as trace:
                result = await process_query()
                trace.set_output(f"Processed query with {len(result)} results")
            ```
        """
        self._output = output

    @asynccontextmanager
    async def span(
        self,
        name: str,
        span_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ):
        """Create a span within this trace.
        
        This could also serve a parent span for coming children spans.

        Parameters
        ----------
        name: str
            Name of the span, should be human-readable.
        span_type: str
            Type of the span allowed: (llm, tool, agent, function, retrieval, embedding, chain, other)
            Any other type will likely throw an error as this is regex verified on server side.
        input_data: Optional[Dict[str, Any]]
            Input data of the operation.
        metadata: Optional[Dict[str, Any]]
            Metadata of the operation.
        model: Optional[str]
            Model used for the operation.
        
        Yields
        ------
        SpanContext
            SpanContext object for the span with set_output() and set_error() methods.
        
        Examples
        --------
            ```python
            # just an analogy of calling any LLM; this is non-functional example
            async with tracer.trace("chat") as trace:
                async with trace.span("gpt-4-call", "llm", model="gpt-4") as span:
                    response = await openai.complete(messages)
                    span.set_output(
                        output_data={"content": response.content},
                        tokens_input=response.usage.prompt_tokens,
                        tokens_output=response.usage.completion_tokens,
                    )
            ```        
        """
        span_context = SpanContext(
            client=self._client,
            span_id=None,
            trace_id=self.trace_id,
            parent_span_id=None
        )

        if self._client.enabled and self.trace_id:
            span_id = await self._client.create_span(
                trace_id=self.trace_id,
                name=name,
                span_type=span_type,
                input_data=input_data,
                metadata=metadata,
                model=model,
            )
            span_context.span_id = span_id
        
        try:
            yield span_context
        
        except Exception as e:
            span_context._error = str(e)
            raise
        
        finally:
            if span_context.span_id:
                await self._client.complete_span(
                    span_id=span_context.span_id,
                    output_data=span_context._output_data,
                    error=span_context._error,
                    tokens_input=span_context._tokens_input,
                    tokens_output=span_context._tokens_output,
                    cost_usd=span_context._cost_usd,
                )


class TracerClient:
    """Async client for the tracing service.
    
    This client is designed to be non-instrusive and fail graciously.
    All failures are logged as warnings and do not raise exceptions,
    ensuring that tracing issues never break your main application.

    Configuration
    -------------
    (via environment variables or constructor)
    - TRACER_URL: Base URL of the tracing service (default: http://localhost:8001).
    - TRACER_API_KEY: API key in format `project-{project_id}` (required).
    - TRACER_PROJECT_ID: Project ID (extracted from API key if not provided).
    - TRACING_ENABLED: Set to "false" to disable tracing (default: True).
    
    Examples
    --------
    ```python
    # Initialize tracer with environment variables
    tracer = TracerClient()
    
    # Or initialize tracer with constructor arguments
    tracer = TracerClient(
        base_url="http://localhost:8001",
        api_key="project-123456",
    )

    async with tracer.trace("user-request") as trace:
        async with trace.span("llm-call", "llm") as span:
            # Your LLM call here
            span.set_output(output_data={"response": "..."})
    ```
    """

    def __init__(
        self, 
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout: float = 5.0,
    ):
        """Initialize the tracer client.
        
        Parameters
        ----------
        base_url: Optional[str]
            Base URL of the tracing service. (default: from TRACER_URL env var)
        api_key: Optional[str]
            API key in format `project-{project_id}`. (default: from TRACER_API_KEY env var)
        project_id: Optional[str]
            Project ID (extracted from API key if not provided).
        timeout: float
            Timeout for requests in seconds to the tracing service (default: 5.0).
        """
        self.base_url = (
            base_url or os.getenv("TRACER_URL", "http://localhost:8001")
        ).rstrip("/")

        self.api_key = api_key or os.getenv("TRACER_API_KEY")
        if not self.api_key:
            logger.warning("No api_key for tracer provided. Tracing will be disabled.")
            self.enabled = False
        else:
            self.enabled = os.getenv("TRACING_ENABLED", "true").lower() == "true"
        
        # project id is also contained in api_key
        self.project_id = project_id or os.getenv("TRACER_PROJECT_ID")
        if not self.project_id and self.api_key and self.api_key.startswith("project-"):
            self.project_id = self.api_key.replace("project-", "", 1)

        self._client = httpx.AsyncClient(timeout=timeout)
        
        if self.enabled:
            logger.info(
                f"TracerClient initialized: {self.base_url} [project: {self.project_id}]"
            )
        else:
            logger.info("TracerClient initialized but tracing is disabled.")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with API key for requests."""
        return {"X-API-KEY": self.api_key} if self.api_key else {}

    async def create_trace(
        self,
        name: str,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new trace.

        Parameters
        ----------
        name: str
            Name of the trace - should be human-readable.
        project_id: Optional[str]
            Override project_id. (default: from client config)
        metadata: Optional[Dict[str, Any]]
            Additional metadata dictionary for the trace.
        tags: Optional[List[str]]
            List of string tags for filtering traces.
        user_id: Optional[str]
            User ID for filtering.
        session_id: Optional[str]
            Session ID for filtering.
        
        Returns
        -------
        Optional[str]
            Trace ID if successful, None if failed.
        
        """
        if not self.enabled:
            return None
        
        pid = project_id or self.project_id
        if not pid:
            logger.warning("No project_id provided. Trace not created.")
            return None
        
        try:
            response = await self._client.post(
                f"{self.base_url}/api/traces",
                json={
                    "name": name,
                    "project_id": pid,
                    "metadata": metadata or {},
                    "tags": tags or [],
                    "user_id": user_id,
                    "session_id": session_id,
                },
                headers=self._get_headers(),  # passing api key
                timeout=2.0,  # Short timeout - don't block main app
            )
            response.raise_for_status()
            result = response.json()
            trace_id = result["trace_id"]

            logger.info(f"Created trace: {trace_id} [project: {pid}]")
            return trace_id
        
        except Exception as e:
            logger.warning(f"Failed to create trace: {e}")
            return None

    async def create_span(
        self,
        trace_id: str,
        name: str,
        span_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new span within a trace.
        
        Parameters
        ----------
        trace_id: str
            Trace ID to which the span belongs.
        name: str
            Name of the span (human-readable)
        span_type: str
            Type of the span (allowed: llm, tool, agent, function, retrieval, embedding, chain, other).
        input_data: Optional[Dict[str, Any]]
            Input data for the operation being traced by this span.
        metadata: Optional[Dict[str, Any]]
            Additional metadata for the span.
        model: Optional[str]
            Model used for the span (pass only for llm spans).
        parent_span_id: Optional[str]
            Parent span ID for nested spans.
        
        Returns
        -------
        Optional[str]
            Span ID if successful, None if failed.
        
        """
        if not self.enabled:
            return None
        
        try:
            response = await self._client.post(
                f"{self.base_url}/api/traces/{trace_id}/spans",
                json={
                    "name": name,
                    "span_type": span_type,
                    "input_data": input_data or {},
                    "metadata": metadata or {},
                    "model": model,
                    "parent_span_id": parent_span_id,
                },
                headers=self._get_headers(),
                timeout=2.0,  # Short timeout - don't block main app
            )
            response.raise_for_status()
            result = response.json()
            span_id = result["span_id"]

            logger.debug(f"Created span: {span_id}")
            return span_id
        
        except Exception as e:
            logger.warning(f"Failed to create span: {e}")
            return None

    # Fire and forget design - as trace and span already exists for complete_*
    # methods, so except for some logs - there is no new info that server
    # needs to send to client. Just either silently execute or fail.
    async def complete_span(
        self,
        span_id: str,
        output_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Mark a span complete with final data.
        
        This is typically called automatically by the span context manager.

        Parameters
        ----------
        span_id: str
            ID of the span to complete.
        output_data: Optional[Dict[str, Any]]
            Output data for the span.
        error: Optional[str]
            Error message for the span, if failed.
        tokens_input: Optional[int]
            Number of input tokens for the span.
        tokens_output: Optional[int]
            Number of output tokens for the span.
        cost_usd: Optional[float]
            Cost of the span in USD.
        """
        if not self.enabled:
            return
        
        try:
            response = await self._client.patch(
                f"{self.base_url}/api/spans/{span_id}/complete",
                json={
                    "output_data": output_data or {},
                    "error": error,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "cost_usd": cost_usd,
                },
                headers=self._get_headers(),
                timeout=2.0,
            )
            logger.debug(f"Completed span: {span_id}")
        
        except Exception as e:
            logger.warning(f"Failed to complete span: {e}")

    async def complete_trace(
        self,
        trace_id: str,
        output: Optional[str] = None,
    ) -> Optional[str]:
        """Mark a trace as complete.
        
        This is typically called automatically by the trace context manager.

        Parameters
        ----------
        trace_id: str
            ID of the trace to complete.
        output: Optional[str]
            Output of the trace.
        """
        if not self.enabled:
            return
        
        try:
            response = await self._client.patch(
                f"{self.base_url}/api/traces/{trace_id}/complete",
                json={"output": output},
                headers=self._get_headers(),
                timeout=2.0,
            )
            logger.debug(f"Completed trace: {trace_id}")
        
        except Exception as e:
            logger.warning(f"Failed to complete trace: {e}")
    
    @asynccontextmanager
    async def trace(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Context manager for tracing a complete operation

        Creates a trace on entry and automatically completes it on exit. 
        Use trace.span() within the context to create spans.
        
        Parameters
        ----------
        name: str
            Name of the trace (human-readable)
        metadata: Optional[Dict[str, Any]]
            Additional metadata for the trace.
        tags: Optional[List[str]]
            List of string tags for filtering.
        user_id: Optional[str]
            user identifier - also for filtering.
        session_id: Optional[str]
            session identifier - also for filtering.

        Yields
        -----
        TraceContext
            TraceContext object containing span() and set_output() methods.

        Example
        -------
        ```python
            # Just an psuedocode example
            async with tracer.trace("user-query", user_id="user123") as trace:
                async with trace.span("process", "function") as span:
                    result = await process()
                    span.set_output(output_data={"result": result})
                trace.set_output("Query processed successfully")
        ```
        """
        trace_id = await self.create_trace(
            name=name,
            metadata=metadata,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
        )
        
        trace_context = TraceContext(client=self, trace_id=trace_id)
        
        try:
            yield trace_context  # the step where the actual operation is executed
        
        except Exception as e:
            trace_context._output = f"Error: {str(e)}"
            raise
        
        finally:
            if trace_id:
                await self.complete_trace(trace_id, output=trace_context._output)

    async def close(self) -> None:
        """Close the HTTP client; call it when done with the tracer."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# ========================================================
# Synchronous Wrapper (for non-async code)               
# ========================================================

class SyncTracerClient:
    """Synchronous wrapper around TracerClient for non-async applications.

    Thread Safety:
        This client is NOT thread-safe. For multi-threaded applications:
        - Create one client per thread, OR
        - Use TracerClient (async) with asyncio

    Typical Use Cases for which this client is recommended:
        - CLI scripts
        - Jupyter notebooks
        - Simple sync applications
        - Testing

    Example
    -------
    1. A solo thread:
    ```python
        tracer = SyncTracerClient()

        with tracer.trace("operation") as trace:
            with trace.span("step", "function") as span:
                result = do_work()
                span.set_output(output_data={"result": result})
            trace.set_output("Operation completed successfully")
    ```
    """

    def __init__(self, **kwargs):
        """Initialize with same arguments as TracerClient."""
        self._async_client = TracerClient(**kwargs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop for running async code."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop
    
    def _run(self, coro):
        """Run coroutine synchronously in current thread's event loop."""
        return self._get_loop().run_until_complete(coro)
    
    def trace(self, name: str, **kwargs):
        """Synchronous trace context manager."""
        # The client is expecting a dict that it will unpack there,
        # hence we simply pass kwargs instead of **kwargs.
        return SyncTraceContext(self, name, kwargs)
    
    def close(self):
        """Close the HTTP client."""
        self._run(self._async_client.close())

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SyncTraceContext:
    """Synchronous trace context manager."""
    
    def __init__(self, client: SyncTracerClient, name: str, kwargs: dict):
        self._client = client
        self._name = name
        self._kwargs = kwargs
        self._trace_context: Optional[TraceContext] = None
        self._async_cm = None
    
    def __enter__(self):
        self._async_cm = self._client._async_client.trace(
            self._name, **self._kwargs
        )
        self._trace_context = self._client._run(self._async_cm.__aenter__())
        return SyncTraceContextWrapper(self._client, self._trace_context)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._client._run(self._async_cm.__aexit__(exc_type, exc_val, exc_tb))
    

class SyncTraceContextWrapper:
    """Wrapper for TraceContext to provide sync interface."""

    def __init__(self, client: SyncTracerClient, trace_context: TraceContext):
        self._client = client
        self._trace_context = trace_context
        self.trace_id = trace_context.trace_id
    
    def set_output(self, output: str):
        self._trace_context.set_output(output)
    
    def span(self, name: str, span_type: str, **kwargs):
        # Here SyncSpanContext is also expecting a dict of kwargs, 
        # hence we pass kwargs instead of **kwargs.
        return SyncSpanContext(self._client, self._trace_context, name, span_type, kwargs)
    

class SyncSpanContext:
    """Synchronous span context manager."""

    def __init__(
        self,
        client: SyncTracerClient,
        trace_context: TraceContext,
        name: str,
        span_type: str,
        kwargs: dict,
    ):
        self._client = client
        self._trace_context = trace_context
        self._name = name
        self._span_type = span_type
        self._kwargs = kwargs
        self._span_context: Optional[SpanContext] = None
        self._async_cm = None
    
    def __enter__(self):
        self._async_cm = self._trace_context.span(
            self._name, self._span_type, **self._kwargs
        )
        self._span_context = self._client._run(self._async_cm.__aenter__())
        return SyncSpanContextWrapper(self._client, self._span_context)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._client._run(self._async_cm.__aexit__(exc_type, exc_val, exc_tb))


class SyncSpanContextWrapper:
    """Wrapper for SpanContext to provide sync interface."""

    def __init__(self, client: SyncTracerClient, span_context: SpanContext):
        self._client = client
        self._span_context = span_context
        self.span_id = span_context.span_id
        self.trace_id = span_context.trace_id
    
    def set_output(
        self,
        output_data=None,
        tokens_input=None,
        tokens_output=None,
        cost_usd=None,
    ):
        self._span_context.set_output(output_data, tokens_input, tokens_output, cost_usd)
    
    def set_error(self, error: str):
        self._span_context.set_error(error)
    
    def span(self, name: str, span_type: str, **kwargs):
        return SyncNestedSpanContext(
            self._client,
            self._span_context,
            name,
            span_type,
            kwargs,
        )


class SyncNestedSpanContext:
    """Synchronous nested span context manager."""

    def __init__(
        self,
        client: SyncTracerClient,
        parent_span: SpanContext,
        name: str,
        span_type: str,
        kwargs: dict,
    ):
        self._client = client
        self._parent_span = parent_span
        self._name = name
        self._span_type = span_type
        self._kwargs = kwargs
        self._async_cm = None
    
    def __enter__(self):
        self._async_cm = self._parent_span.span(
            self._name,
            self._span_type,
            **self._kwargs
        )
        span_context = self._client._run(self._async_cm.__aenter__())
        return SyncSpanContextWrapper(self._client, span_context)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._client._run(self._async_cm.__aexit__(exc_type, exc_val, exc_tb))
