# LLM Tracer Client

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LLM Tracer Client                              │
│                                                                             │
│  Design Principles:                                                         │
│  • Non-blocking: Never interrupts main application flow                     │
│  • Graceful degradation: Failures logged as warnings, never raised          │
│  • Context managers: Automatic lifecycle management                         │
│  • Production-ready: Nested spans, cost tracking, error capture             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          ASYNC CLIENT (Recommended)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   TracerClient                                                              │
│   ├── trace(name, metadata?, tags?, user_id?, session_id?)                  │
│   │   └── yields: TraceContext                                              │
│   ├── create_trace(...)  → trace_id       # Low-level API                   │
│   ├── create_span(...)   → span_id        # Low-level API                   │
│   ├── complete_trace(trace_id, output?)   # Auto-called by context          │
│   ├── complete_span(span_id, ...)         # Auto-called by context          │
│   └── close()                             # Cleanup HTTP client             │
│                                                                             │
│   TraceContext (yielded by tracer.trace())                                  │
│   ├── trace_id: str                                                         │
│   ├── set_output(output: str)                                               │
│   └── span(name, span_type, input_data?, metadata?, model?)                 │
│       └── yields: SpanContext                                               │
│                                                                             │
│   SpanContext (yielded by trace.span() or span.span())                      │
│   ├── span_id: str                                                          │
│   ├── trace_id: str                                                         │
│   ├── set_output(output_data?, tokens_input?, tokens_output?, cost_usd?)    │
│   ├── set_error(error: str)                                                 │
│   └── span(...)  → nested child span                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                     SYNC CLIENT (for scripts/notebooks)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   SyncTracerClient                                                          │
│   ├── trace(name, **kwargs)  → SyncTraceContextWrapper                      │
│   └── close()                                                               │
│                                                                             │
│   ⚠️  NOT thread-safe: Create one client per thread                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              SPAN TYPES                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   llm        │ LLM API calls (OpenAI, Anthropic, etc.)                      │
│   tool       │ External tool/API calls                                      │
│   agent      │ Agent orchestration steps                                    │
│   function   │ Generic function execution                                   │
│   retrieval  │ RAG/vector database queries                                  │
│   embedding  │ Embedding generation                                         │
│   chain      │ Chain/pipeline steps                                         │
│   other      │ Anything else                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            CONFIGURATION                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Environment Variables:                                                    │
│   ┌────────────────────┬─────────────────────────┬────────────────────────┐ │
│   │ Variable           │ Default                 │ Description            │ │
│   ├────────────────────┼─────────────────────────┼────────────────────────┤ │
│   │ TRACER_URL         │ http://localhost:8001   │ Tracing service URL    │ │
│   │ TRACER_API_KEY     │ (required)              │ Format: project-{id}   │ │
│   │ TRACER_PROJECT_ID  │ (from API key)          │ Project identifier     │ │
│   │ TRACING_ENABLED    │ true                    │ Set "false" to disable │ │
│   └────────────────────┴─────────────────────────┴────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Your App    │────▶│ TracerClient │────▶│   Service    │
│              │     │              │     │  (FastAPI)   │
│  async with  │     │  HTTP POST   │     │              │
│  tracer.     │     │  /api/traces │     │  DynamoDB    │
│  trace()     │     │  /api/spans  │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       │                    │                    │
       ▼                    ▼                    ▼
   ┌───────┐          ┌───────────┐        ┌─────────┐
   │ Trace │─────────▶│ Complete  │───────▶│  Store  │
   │ Start │          │  + Metrics│        │  + TTL  │
   └───────┘          └───────────┘        └─────────┘
```

## Usage Patterns

### Pattern 1: Simple Trace with Single Span

```python
async with tracer.trace("user-request") as trace:
    async with trace.span("llm-call", "llm", model="gpt-4") as span:
        response = await llm.complete(prompt)
        span.set_output(
            output_data={"content": response.text},
            tokens_input=response.usage.prompt_tokens,
            tokens_output=response.usage.completion_tokens,
            cost_usd=0.003
        )
    trace.set_output("Request completed")
```

### Pattern 2: Nested Spans (Agent with Tools)

```python
async with tracer.trace("agent-task", user_id="user123") as trace:
    async with trace.span("agent-loop", "agent") as agent_span:

        async with agent_span.span("search-tool", "tool") as tool_span:
            results = await search(query)
            tool_span.set_output(output_data={"hits": len(results)})

        async with agent_span.span("synthesize", "llm", model="claude-3") as llm_span:
            answer = await llm.complete(results)
            llm_span.set_output(
                output_data={"answer": answer},
                tokens_input=1500,
                tokens_output=500
            )
```

### Pattern 3: Error Handling

```python
async with tracer.trace("risky-operation") as trace:
    async with trace.span("external-api", "tool") as span:
        try:
            result = await external_api.call()
            span.set_output(output_data={"status": "success"})
        except Exception as e:
            span.set_error(str(e))  # Captured, trace continues
            raise                    # Re-raise if needed
```

### Pattern 4: Sync Client (Scripts/Notebooks)

```python
tracer = SyncTracerClient()

with tracer.trace("batch-job") as trace:
    with trace.span("process", "function") as span:
        result = process_data()
        span.set_output(output_data={"records": len(result)})

tracer.close()
```

---

## Complete Examples

### TracerClient (Async) - Long-Lived

Best for: **Web APIs, Agentic orchestration, Background workers**

The client is created once at application startup and reused across all requests.
This is the recommended pattern for production applications.

```python
"""FastAPI application with long-lived tracer client."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from openai import AsyncOpenAI

from llm_tracer import TracerClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tracer on startup, close on shutdown."""
    app.state.tracer = TracerClient(
        base_url="https://tracing.myapp.com",
        api_key="project-production",
    )
    yield
    await app.state.tracer.close()


app = FastAPI(lifespan=lifespan)
openai = AsyncOpenAI()


@app.post("/chat")
async def chat(request: Request):
    tracer = request.app.state.tracer
    body = await request.json()

    async with tracer.trace("chat-request", user_id=body.get("user_id")) as trace:

        async with trace.span("gpt-4-call", "llm", model="gpt-4") as span:
            response = await openai.chat.completions.create(
                model="gpt-4",
                messages=body["messages"],
            )
            span.set_output(
                output_data={"content": response.choices[0].message.content},
                tokens_input=response.usage.prompt_tokens,
                tokens_output=response.usage.completion_tokens,
            )

        trace.set_output("Chat completed")

    return {"response": response.choices[0].message.content}
```

---

### TracerClient (Async) - Scoped

Best for: **Batch scripts, One-off jobs, Testing**

The client is created and closed within a context manager scope.
Useful when you have a finite task and want automatic cleanup.

```python
"""Batch processing script with scoped tracer client."""

import asyncio
from llm_tracer import TracerClient
from openai import AsyncOpenAI


async def process_batch(prompts: list[str]):
    openai = AsyncOpenAI()

    async with TracerClient(api_key="project-batch") as tracer:

        for i, prompt in enumerate(prompts):
            async with tracer.trace(f"batch-item-{i}") as trace:

                async with trace.span("embedding", "embedding") as span:
                    embed_response = await openai.embeddings.create(
                        model="text-embedding-3-small",
                        input=prompt,
                    )
                    span.set_output(output_data={"dimensions": 1536})

                async with trace.span("completion", "llm", model="gpt-4") as span:
                    response = await openai.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": prompt}],
                    )
                    span.set_output(
                        output_data={"content": response.choices[0].message.content},
                        tokens_input=response.usage.prompt_tokens,
                        tokens_output=response.usage.completion_tokens,
                    )

                trace.set_output(f"Processed prompt {i}")

    # Client automatically closed here


if __name__ == "__main__":
    prompts = [
        "Explain quantum computing",
        "What is machine learning?",
        "How do neural networks work?",
    ]
    asyncio.run(process_batch(prompts))
```

---

### SyncTracerClient - Long-Lived

Best for: **Jupyter notebooks, Interactive sessions, CLI tools**

Create the client once and reuse across multiple cells or operations.
Remember to call `close()` when done.

```python
"""Jupyter notebook with long-lived sync client."""

from llm_tracer import SyncTracerClient
import openai

# Cell 1: Initialize (run once)
tracer = SyncTracerClient(api_key="project-notebook")

# Cell 2: First experiment
with tracer.trace("experiment-v1", tags=["baseline"]) as trace:
    with trace.span("gpt-4-turbo", "llm", model="gpt-4-turbo") as span:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": "Explain transformers"}],
        )
        span.set_output(
            output_data={"content": response.choices[0].message.content},
            tokens_input=response.usage.prompt_tokens,
            tokens_output=response.usage.completion_tokens,
        )
    trace.set_output("Baseline complete")

# Cell 3: Second experiment (reuses same client)
with tracer.trace("experiment-v2", tags=["with-system-prompt"]) as trace:
    with trace.span("gpt-4-turbo", "llm", model="gpt-4-turbo") as span:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are a ML expert."},
                {"role": "user", "content": "Explain transformers"},
            ],
        )
        span.set_output(
            output_data={"content": response.choices[0].message.content},
            tokens_input=response.usage.prompt_tokens,
            tokens_output=response.usage.completion_tokens,
        )
    trace.set_output("With system prompt complete")

# Cell N: Cleanup (run when done)
tracer.close()
```

---

### SyncTracerClient - Scoped

Best for: **Simple scripts, Unit tests, Quick experiments**

The client is created and closed within a context manager scope.

```python
"""Simple CLI script with scoped sync client."""

from llm_tracer import SyncTracerClient
import openai


def analyze_text(text: str) -> dict:
    with SyncTracerClient(api_key="project-cli") as tracer:

        with tracer.trace("text-analysis") as trace:

            # Step 1: Get embedding
            with trace.span("embed", "embedding") as span:
                embed_resp = openai.embeddings.create(
                    model="text-embedding-3-small",
                    input=text,
                )
                embedding = embed_resp.data[0].embedding
                span.set_output(output_data={"dimensions": len(embedding)})

            # Step 2: Analyze sentiment
            with trace.span("sentiment", "llm", model="gpt-4") as span:
                response = openai.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "Analyze sentiment. Reply: positive/negative/neutral"},
                        {"role": "user", "content": text},
                    ],
                )
                sentiment = response.choices[0].message.content
                span.set_output(
                    output_data={"sentiment": sentiment},
                    tokens_input=response.usage.prompt_tokens,
                    tokens_output=response.usage.completion_tokens,
                )

            trace.set_output(f"Analysis complete: {sentiment}")

        return {"embedding": embedding, "sentiment": sentiment}

    # Client automatically closed here


if __name__ == "__main__":
    result = analyze_text("I love this product! It works great.")
    print(result["sentiment"])
```

---

## Client Lifecycle Summary

| Pattern | Client Creation | Client Cleanup | Best For |
|---------|-----------------|----------------|----------|
| **Async Long-lived** | App startup | App shutdown | Web APIs, Agents |
| **Async Scoped** | `async with TracerClient()` | Automatic | Batch scripts |
| **Sync Long-lived** | Top of notebook/script | Manual `close()` | Jupyter, CLI |
| **Sync Scoped** | `with SyncTracerClient()` | Automatic | Simple scripts |
