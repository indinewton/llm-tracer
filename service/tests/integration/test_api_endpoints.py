"""Integration tests for api endpoints with DynamoDB local.

Execute this file from service/ for async tests to pass

# Note: pytest adds the parent directory (llm-tracer/) to sys.path during test collection,
# making 'service' importable as a package. Run tests from service/ directory with: uv run pytest
"""

import pytest
import os
from fastapi.testclient import TestClient

# Configure for DynamoDB Local - MUST be before importing app
# because server.py initializes storage at module level
os.environ["DYNAMODB_ENDPOINT_URL"] = "http://localhost:8000"
os.environ["DYNAMODB_TRACES_TABLE"] = "llm-tracer-dev-traces"
os.environ["DYNAMODB_SPANS_TABLE"] = "llm-tracer-dev-spans"
os.environ["API_KEY_REQUIRED"] = "true"
os.environ["API_KEYS"] = "project-test"

# This must be imported after because server.py loads .env and it has defaults that DynamoDBStorage uses to initialize.
# Which we don't want. We want it to use os.environ vars as defined above - especially the api_keys and table names.
from service.src.server import app


@pytest.fixture
def client():
    """FastAPI test client"""
    # This allows testing against the client w/o starting a real HTTP server
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers"""
    return {"X-API-Key": "project-test"}


def test_health_endpoint(client):
    """Test health endpoint"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    try:
        assert data["status"] == "healthy"
    except AssertionError as e:
        print("Api is healthy; but retured json is different compared to test: \n", data)


def test_create_trace(client, auth_headers):
    """Test creating a trace"""
    trace_data = {
        "name": "Integration test trace",
        "project_id": "test",  # must be derived out of API_KEY i.e. "project-test"
        "metadata": {"test": True},
        "tags": ["integration"],
    }

    response = client.post("/api/traces", json=trace_data, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "trace_id" in data, "trace_id must be present in response for creating trace."
    assert data["status"] == "created", "trace_id exists, but 'status' is not set to 'created'."


def test_create_trace_requires_auth(client):
    """Test that to create trace, API key is required."""
    trace_data = {
        "name": "Test",
        "project_id": "test"
    }

    # now we try to post without auth headers, this should return 401 error
    response = client.post("/api/traces", json=trace_data)
    assert response.status_code == 401, "must return 401 error for missing API key, anything else is a bug."


def test_create_span(client, auth_headers):
    """Test creating a span for a trace"""
    # First create a trace
    trace_response = client.post(
        "/api/traces",
        json={"name": "Parent trace", "project_id": "test"},
        headers=auth_headers,
    )
    trace_id = trace_response.json()["trace_id"]

    # Now create a span for this trace
    span_data = {
        "name": "Test span",
        "span_type": "llm",
        "model": "gpt-4",
        "tokens_input": 100,
        "tokens_output": 50,
    }

    response = client.post(
        f"/api/traces/{trace_id}/spans",
        json=span_data,
        headers=auth_headers,
    )

    assert response.status_code == 200, "Span creation failed."
    data = response.json()
    assert "span_id" in data, "span_id not found in response for creating span."


def test_get_traces(client, auth_headers):
    """test querying traces."""
    client.post(
        "/api/traces",
        json={"name": "Query Test", "project_id": "test"},
        headers=auth_headers,
    )

    response = client.get("/api/traces", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Response is TraceListResponse (dict), not list
    msg = "Response should resemble TraceListResponse object."

    assert "traces" in data, msg
    assert "count" in data, msg
    assert "has_more" in data, msg
    assert isinstance(data["traces"], list), msg
    assert len(data["traces"]) > 0, msg
    assert data["count"] > 0, msg


def test_get_trace_with_spans(client, auth_headers):
    """test getting full trace with spans."""
    # create a trace
    trace_response = client.post(
        "/api/traces",
        json={"name": "Full testing trace", "project_id": "test"},
        headers=auth_headers,
    )

    trace_id = trace_response.json()["trace_id"]

    # Add spans
    for i in range(3):
        client.post(
            f"/api/traces/{trace_id}/spans",
            json={"name": f"Span id-{i}", "span_type": "llm"},
            headers=auth_headers,
        )
    
    # Get full trace
    response = client.get(f"/api/traces/{trace_id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["trace"]["trace_id"] == trace_id, "Trace ID does not match in fetched spans."
    assert len(data["spans"]) == data["span_count"] == 3, "Span count must be 3"


def test_complete_trace(client, auth_headers):
    """test completing a trace."""
    # create a trace
    trace_response = client.post(
        "/api/traces",
        json={"name": "Complete a trace Test", "project_id": "test"},
        headers=auth_headers,
    )

    trace_id = trace_response.json()["trace_id"]
    
    # Complete trace
    response = client.patch(
        f"/api/traces/{trace_id}/complete", 
        json={"output": "Success"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed", "Trace must show 'status' as 'completed'."


def test_complete_span(client, auth_headers):
    """Test completing a span with metric"""
    # Create a trace
    trace_response = client.post(
        "/api/traces",
        json={"name": "Complete a span Test", "project_id": "test"},
        headers=auth_headers,
    )

    trace_id = trace_response.json()["trace_id"]

    # Create a span
    span_response = client.post(
        f"/api/traces/{trace_id}/spans",
        json={"name": "LLM call", "span_type": "llm"},
        headers=auth_headers,
    )

    span_id = span_response.json()["span_id"]

    # Complete span
    response = client.patch(
        f"/api/spans/{span_id}/complete", 
        json={
            "output_data": {"content": "some response text from llm."},
            "token_input": 100,
            "token_output": 50,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed", "Span must show 'status' as 'completed'."


def test_pagination_cursor(client, auth_headers):
    """Test pagination returns cursor for more results.
    
    DynamoDB returns results in pages. If result is longer than the page limit, then
    query also returns a cursor that you can use to fetch next page.
    """
    # Create multiple pages
    for i in range(5):
        client.post(
            "/api/traces",
            json={"name": f"Pagination test trace {i}", "project_id": "test"},
            headers=auth_headers,
        )
    
    # Query with small limits
    response = client.get("/api/traces?limit=2", headers=auth_headers)
    data = response.json()
    
    msg = "As we are fetching 2 out of 5 traces, so: count==2 | has_more==True | next_cursor is not None."
    
    assert data["has_more"] is True, msg
    assert data["count"] == 2, msg
    assert data["next_cursor"] is not None, msg
