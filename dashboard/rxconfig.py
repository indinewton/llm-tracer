"""Configuration file for the Reflex app."""

import os
import reflex as rx
from reflex.config import LogLevel

config = rx.Config(
    app_name="dashboard",

    # Plugins
    plugins=[
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.SitemapPlugin(),  # Explicitly added to suppress default warning
    ],

    # Ports - make sure not to use 8000 and 8001 as
    # they are used by dynamodb LLM tracer client
    frontend_port=3000,  # Reflex frontend (next.js)
    backend_port=8002,   # Reflex backend (fastapi)
    backend_host="0.0.0.0",

    # API URL for frontend to connect to Reflex backend
    # This is NOT your tracer API - this is Reflex's internal backend
    api_url=os.environ.get(
        "REFLEX_API_URL",
        "http://localhost:8002",  # Must match backend_port
    ),

    # Environment file
    env_file=".env",

    # Logging - must use LogLevel enum
    loglevel=LogLevel.DEBUG,

    # Disable telemetry (optional)
    telemetry_enabled=False,
)
