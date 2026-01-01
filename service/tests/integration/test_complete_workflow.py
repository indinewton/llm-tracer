"""Integration tests for complete trace/span workflows.

These tests verify end-to-end workflows using the FastAPI TestClient.
They complement test_api_endpoints.py by testing realistic usage patterns.

Execute pytest <this file> from root dir where service/ is a module.
"""

import pytest
import time
from fastapi.testclient import TestClient

from service.src.server import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers matching project_id 'test'."""
    return {"X-API-Key": "project-test"}


class TestLLMCallWorkflow:
    """Test complete LLM call workflow: trace → span → complete → verify."""

    def test_complete_llm_call_workflow(self, client, auth_headers):
        """Full workflow: create trace, add span, complete both, verify results."""
        # Step 1: Create trace for LLM call
        trace_response = client.post(
            "/api/traces",
            json={
                "name": "LLM Call Workflow Test",
                "project_id": "test",
                "metadata": {"model": "gpt-4", "temperature": 0.7},
                "tags": ["workflow-test", "llm"],
            },
            headers=auth_headers,
        )

        assert trace_response.status_code == 200
        trace_id = trace_response.json()["trace_id"]

        # Step 2: Create LLM span
        span_response = client.post(
            f"/api/traces/{trace_id}/spans",
            json={
                "name": "GPT-4 Completion",
                "span_type": "llm",
                "input_data": {"prompt": "What is the capital of France?"},
                "model": "gpt-4",
            },
            headers=auth_headers,
        )

        assert span_response.status_code == 200
        span_id = span_response.json()["span_id"]

        # Step 3: Simulate processing time
        time.sleep(0.05)

        # Step 4: Complete span with output metrics
        complete_span_response = client.patch(
            f"/api/spans/{span_id}/complete",
            json={
                "output_data": {"content": "The capital of France is Paris."},
                "tokens_input": 12,
                "tokens_output": 8,
            },
            headers=auth_headers,
        )

        assert complete_span_response.status_code == 200

        # Step 5: Complete trace
        complete_trace_response = client.patch(
            f"/api/traces/{trace_id}/complete",
            json={"output": "LLM call completed successfully"},
            headers=auth_headers,
        )

        assert complete_trace_response.status_code == 200

        # Step 6: Verify full trace retrieval
        get_response = client.get(f"/api/traces/{trace_id}", headers=auth_headers)

        assert get_response.status_code == 200
        data = get_response.json()

        # Verify trace fields
        trace = data["trace"]
        assert trace["trace_id"] == trace_id
        assert trace["end_time"] is not None, "Trace should have end_time after completion"
        assert trace["duration_ms"] is not None, "Trace should have duration_ms"
        assert trace["duration_ms"] >= 0

        # Verify span fields
        assert len(data["spans"]) == 1
        span = data["spans"][0]
        assert span["span_id"] == span_id
        assert span["end_time"] is not None, "Span should have end_time after completion"
        assert span["tokens_input"] == 12
        assert span["tokens_output"] == 8


class TestNestedSpansWorkflow:
    """Test workflows with nested spans (parent-child relationships)."""

    def test_nested_spans_workflow(self, client, auth_headers):
        """Workflow with parent span containing child spans."""
        # Create a trace
        trace_response = client.post(
            "/api/traces",
            json={
                "name": "Agent Workflow Test",
                "project_id": "test"
            },
            headers=auth_headers,
        )
        trace_id = trace_response.json()["trace_id"]

        # Creating parent span (typically an agent orchestrator)
        parent_response = client.post(
            f"/api/traces/{trace_id}/spans",
            json={
                "name": "Agent Planning",
                "span_type": "agent"
            },
            headers=auth_headers,
        )
        parent_span_id = parent_response.json()["span_id"]

        # Create multiple child spans (individual tasks) - these could be also retries of previous tasks.
        child_ids = []
        tasks = ["Fetch Data", "Analyze", "Generate Report"]
        for task in tasks:
            child_response = client.post(
                f"/api/traces/{trace_id}/spans",
                json={
                    "name": task,
                    "span_type": "function",
                    "parent_span_id": parent_span_id,
                },
                headers=auth_headers,
            )
            child_ids.append(child_response.json()["span_id"])

        # All child spans must be completed before the parent span
        for span_id in child_ids:
            response = client.patch(
                f"/api/spans/{span_id}/complete",
                json={},
                headers=auth_headers,
            )
            assert response.status_code == 200

        # Now complete the parent span
        response = client.patch(
            f"/api/spans/{parent_span_id}/complete",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Finally complete the trace
        response = client.patch(
            f"/api/traces/{trace_id}/complete",
            json={"output": "Agent workflow completed"},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Verify the completed trace retrieval
        get_response = client.get(f"/api/traces/{trace_id}", headers=auth_headers)
        data = get_response.json()

        # Should have 4 spans: 1 parent + 3 children
        assert data["span_count"] == 4, f"Expected 4 spans, got {data['span_count']}"

        # Verify parent-child relationships; children spans are just entries with parent_span_id not None.
        children = [s for s in data["spans"] if s.get("parent_span_id")]
        assert len(children) == 3, "Should have 3 child spans"
        assert all(
            s["parent_span_id"] == parent_span_id for s in children
        ), "All children should reference parent span"


class TestMultiSpanWorkflow:
    """Test workflows with multiple sequential spans."""

    def test_multi_span_sequential_workflow(self, client, auth_headers):
        """Workflow with multiple sequential spans (RAG pattern)."""
        # Create a trace
        trace_response = client.post(
            "/api/traces",
            json={
                "name": "RAG Pipeline Test",
                "project_id": "test"
            },
            headers=auth_headers,
        )
        trace_id = trace_response.json()["trace_id"]

        # Span 1: Embedding generation; span_type is set to embedding.
        embed_response = client.post(
            f"/api/traces/{trace_id}/spans",
            json={
                "name": "Generating Embedding",
                "span_type": "embedding",
                "input_data": {"text": "user query"},
                "model": "text-embedding-3-small",
            },
            headers=auth_headers,
        )
        embed_span_id = embed_response.json()["span_id"]

        # Complete the embedding span
        client.patch(
            f"/api/spans/{embed_span_id}/complete",
            json={"output_data": {"embedding_dim": 1536}},
            headers=auth_headers,
        )

        # Span 2: Vector retrieval
        retrieval_response = client.post(
            f"/api/traces/{trace_id}/spans",
            json={
                "name": "Vector Search",
                "span_type": "retrieval",
                "input_data": {"top_k": 5},
            },
            headers=auth_headers,
        )
        retrieval_span_id = retrieval_response.json()["span_id"]

        # Complete the retrieval span
        client.patch(
            f"/api/spans/{retrieval_span_id}/complete",
            json={"output_data": {"results_count": 5}},
            headers=auth_headers,
        )

        # Span 3: LLM generation
        llm_response = client.post(
            f"/api/traces/{trace_id}/spans",
            json={
                "name": "LLM Generation",
                "span_type": "llm",
                "model": "gpt-4",
            },
            headers=auth_headers,
        )
        llm_span_id = llm_response.json()["span_id"]

        # Complete the LLM generation span
        client.patch(
            f"/api/spans/{llm_span_id}/complete",
            json={
                "output_data": {"response": "Generated answer"},
                "tokens_input": 500,
                "tokens_output": 150,
            },
            headers=auth_headers,
        )

        # FINALLY: After all the spans or tasks are completed, complete the open trace
        client.patch(
            f"/api/traces/{trace_id}/complete",
            json={"output": "RAG pipeline completed"},
            headers=auth_headers,
        )

        # Verify
        get_response = client.get(f"/api/traces/{trace_id}", headers=auth_headers)
        data = get_response.json()

        assert data["span_count"] == 3

        # Verify span types are preserved through set equality matching.
        span_types = {s["span_type"] for s in data["spans"]}  # this creates an unordered set
        assert span_types == {"embedding", "retrieval", "llm"} 
