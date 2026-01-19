import os
import httpx
from typing import Optional, Dict, Any

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

API_URL = os.getenv("TRACER_API_URL", "http://localhost:8001")
API_KEY = os.getenv("TRACER_API_KEY", "")

# Default timeouts for API requests (seconds)
DEFAULT_TIMEOUT = 30.0
HEALTH_TIMEOUT = 5.0


def _get_headers() -> Dict[str, str]:
    """Get default headers for API requests."""
    return {"X-API-Key": API_KEY}


async def get_stats() -> Dict[str, Any]:
    """Fetch agg statistics.
    
    Returns
    -------
    Dict[str, Any]
        Statistics including total_traces, total_spans, total_tokens, total_cost.

    Raises
    ------
    httpx.HTTPStatusError
        If the API returns an error status code.
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{API_URL}/api/stats",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def get_traces(
    limit: int = 50,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch paginated traces.
    
    Parameters
    ----------
    limit : int
        Maximum number of traces to fetch.
    cursor : Optional[str]
        Cursor for pagination, to navigate to next page.
    
    Returns
    -------
    Dict[str, Any]
        Response containing traces, next_cursor, and has_more.
    """
    params: Dict[str, Any] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{API_URL}/api/traces",
            headers=_get_headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()


async def get_trace_detail(trace_id: str) -> Dict[str, Any]:
    """Fetch a single trace with all spans.
    
    Parameters
    ----------
    trace_id : str
        ID of the trace to fetch.
    
    Returns
    -------
    Dict[str, Any]
        Response containing trace and spans.
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{API_URL}/api/traces/{trace_id}",
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def check_health() -> bool:
    """Check if tracer service is healthy."""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(f"{API_URL}/health")  # /health is a public endpoint, w/o headers
            return resp.status_code == 200

    except (httpx.RequestError, httpx.TimeoutException):
        return False
