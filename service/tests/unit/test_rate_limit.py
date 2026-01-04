"""Unit tests for rate limiting.

Execute this file from service/ for async tests to pass

# Note: pytest adds the parent directory (llm-tracer/) to sys.path during test collection,
# making 'service' importable as a package. Run tests from service/ directory with: uv run pytest
"""

import pytest
import time
from fastapi import Request, HTTPException

from service.src.rate_limit import RateLimiter


@pytest.fixture
def rate_limiter():
    """Create rate limiter with low threshold only for testing."""
    return RateLimiter(requests_per_minute=5, window_seconds=10)


@pytest.fixture
def mock_request():
    """Create Mock request"""
    class MockClient:
        host = "127.0.0.1"
    
    class MockRequest:
        client = MockClient()
    
    return MockRequest()


@pytest.mark.asyncio
async def test_rate_limit_allows_requests_under_threshold(
    rate_limiter,
    mock_request,
):
    """Test that rate limiter allows requests under threshold."""
    for _ in range(5):
        # Should not raise exception
        await rate_limiter.check_rate_limit(mock_request)


@pytest.mark.asyncio
async def test_rate_limit_blocking_and_resetting(
    rate_limiter,
    mock_request,
):
    """Test that rate limiter blocks requests over threshold and resets after window."""
    # Use up quota
    for _ in range(5):
        await rate_limiter.check_rate_limit(mock_request)
    
    # Next one should be blocked
    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter.check_rate_limit(mock_request)
    
    assert exc_info.value.status_code == 429

    # Wait for window to pass
    time.sleep(11)
    
    # Next one should be allowed
    await rate_limiter.check_rate_limit(mock_request)
