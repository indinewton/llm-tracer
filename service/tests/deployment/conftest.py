"""Fixtures for deployment tests."""

import os
import pytest
import boto3


@pytest.fixture(scope="session")
def deployment_config():
    """Get Deployment configuration from environment."""
    config = {
        "api_base_url": os.environ.get("API_BASE_URL"),
        "api_key": os.environ.get("API_KEY"),
        "traces_table": os.environ.get("DYNAMODB_TRACES_TABLE"),
        "spans_table": os.environ.get("DYNAMODB_SPANS_TABLE"),
        "aws_region": os.environ.get("AWS_REGION", "eu-central-1"),
        "environment": os.environ.get("DEPLOYMENT_ENV", "dev"),
    }

    # Validate required config
    missing = [k for k, v in config.items() if v is None and k != "environment"]
    if missing:
        pytest.skip(f"Missing required environment variables: {missing}")
    
    return config


@pytest.fixture(scope="session")
def dynamodb_client(deployment_config):
    """Create dynamoDB client for deployment tests"""
    return boto3.client(
        "dynamodb",
        region_name=deployment_config["aws_region"]
    )


@pytest.fixture(scope="session")
def http_client(deployment_config):
    """Create http client for API tests"""
    import httpx
    return httpx.Client(
        base_url=deployment_config["api_base_url"],
        headers={"X-API-Key": deployment_config["api_key"]},
        timeout=10.0,
    )
