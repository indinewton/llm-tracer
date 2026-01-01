"""
Simple in-memory rate limiter.

To prevent abuse, the service is rate-limited to 60 requests per minute per project.
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException, status


class RateLimiter:
    """In memory rate limiter using sliding window algorithm"""

    def __init__(
        self,
        requests_per_minute: int = 60,
        window_seconds: int = 60,
        ):
        self.rpm = requests_per_minute
        self.window = window_seconds
        self.requests = defaultdict(list)  #  client_ip -> list of request timestamps

    async def check_rate_limit(self, request: Request):
        """Check if request exceeds rate limit."""
        client_ip = request.client.host
        current_time = time.time()  # float type time value in seconds 

        # Remove old requests (older than 1 minute)
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if current_time - req_time < self.window  # This is a time window, different from rpm=60!
        ]

        if len(self.requests[client_ip]) >= self.rpm:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max allowed {self.rpm} requests per {self.window} seconds.",
            )

        self.requests[client_ip].append(current_time)
