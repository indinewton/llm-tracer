"""Shared pytest fixtures for service tests."""

import pytest
import os
import boto3
from moto import mock_aws
from datetime import datetime, UTC

from service.scripts.dynamodb_schemas import (
    get_create_table_kwargs,
    TRACES_SCHEMA,
    SPANS_SCHEMA,
)

# Default region for tests (can be overridden via AWS_REGION env var)
TEST_AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")


@pytest.fixture(scope="session")
def aws_credentials():
    """Mosck AWS credentials for testing"""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = TEST_AWS_REGION


@pytest.fixture
def dynamodb_tables(aws_credentials, monkeypatch):
    """Create mock DynamoDB tables"""
    monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=TEST_AWS_REGION)

        # Create traces table
        traces_table = dynamodb.create_table(
            **get_create_table_kwargs("test-traces", TRACES_SCHEMA)
        )

        # Create spans table
        spans_table = dynamodb.create_table(
            **get_create_table_kwargs("test-spans", SPANS_SCHEMA)
        )

        yield {
            "traces": traces_table,
            "spans": spans_table,
        }


@pytest.fixture
def sample_trace():
    """Sample trace data for testing"""
    return {
        "trace_id": "test-trace-123",
        "name": "Test Trace",
        "project_id": "test-project",
        "start_time": datetime.now(UTC).isoformat(),
        "tags": ["test", "sample"],
        "metadata": {"key": "value"},
    }


@pytest.fixture
def sample_span():
    """Sample span data for testing"""
    return {
        "span_id": "test-span-123",
        "trace_id": "test-trace-123",
        "name": "Test Span",
        "span_type": "llm",
        "start_time": datetime.now(UTC).isoformat(),
        "model": "gpt-4",
        "tokens_input": 100,
        "tokens_output": 50,
        "cost_usd": 0.002,
    }