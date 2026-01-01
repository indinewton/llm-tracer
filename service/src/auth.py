"""API key authentication middleware"""

import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """Validate API key from request header."""
    if not os.getenv("API_KEY_REQUIRED", "false").lower() == "true":
        # Return default project key when auth is disabled
        return os.getenv("DEFAULT_PROJECT_KEY", "project-public")

    valid_keys = os.getenv("API_KEYS", "").split(",")

    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or missing API key"
        )
    
    return api_key


def extract_project_id(api_key: str) -> str:
    """Extract project ID from API key of format: project-{project_id}"""
    if api_key.startswith("project-"):
        project_id = api_key.replace("project-", "", 1)
        if project_id:  # Ensure not empty after extraction
            return project_id

    # No side-effect is planned for this method, so we raise an exception
    raise HTTPException(
        status_code=400,
        detail="Invalid API key format. Expected: project-{project_id}"
    )
