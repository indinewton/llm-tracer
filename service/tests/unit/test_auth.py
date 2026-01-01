"""Unit tests for authentication.

Execute pytest <this file> from root dir where service/ is a module.
"""

import pytest
from fastapi import HTTPException

from service.src.auth import extract_project_id

def test_extract_project_id_valid():
    """Test extracting project id from valid API key."""
    api_key = "project-my-project-123"
    result = extract_project_id(api_key)
    assert result == "my-project-123"


def test_extract_project_id_invalid():
    """Test extracting project id from invalid API key."""
    api_key = "invalid-api-key"
    with pytest.raises(HTTPException) as exc_info:
        extract_project_id(api_key)
    
    assert exc_info.value.status_code == 400
    
    api_key = "project-"
    with pytest.raises(HTTPException) as exc_info:
        extract_project_id(api_key)
    
    assert exc_info.value.status_code == 400
