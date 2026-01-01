import os
import httpx
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True), override=True)

TRACER_URL = os.getenv("TRACER_URL")
print(TRACER_URL)
API_KEY = os.getenv("API_KEY")

headers = {"X-API-Key": API_KEY}

# Create a trace
response = httpx.post(
    f"{TRACER_URL}/api/traces",
    headers=headers,
    json={
        "name": "my-agent-run",
        "project_id": "dev",  # Must match API key: project-{project_id} or leave it empty
        "metadata": {"user": "test-user"}
    }
)

trace_id = response.json()["trace_id"]
print(trace_id)

# Add a span (e.g. LLM Call)
response = httpx.post(
    f"{TRACER_URL}/api/traces/{trace_id}/spans",
    headers=headers,
    json={
        "name": "openai-completion",
        "span_type": "llm",
        "model": "gpt-4",
        "input_data": {"prompt": "Hello world"}
    }
)
span_id = response.json()["span_id"]
print(span_id)

# Complete the span
httpx.patch(
    f"{TRACER_URL}/api/spans/{span_id}/complete",
    headers=headers,
    json={
        "output_data": {"response": "Hi there!"},
        "tokens_input": 10,
        "tokens_output": 5
    }
)
# Should print to console: <Response [200 OK]>

# Complete the trace
httpx.patch(
    f"{TRACER_URL}/api/traces/{trace_id}/complete",
    headers=headers,
    json={"output": "Agent completed successfully"}
)
# Should print to console: <Response [200 OK]>

# CONGRATULATIONS! You have successfully deployed LLM Tracer and tested it.