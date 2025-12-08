"""Pytest configuration and shared fixtures for testing.

This module provides:
- Pytest fixtures for test setup/teardown
- Mock OpenAI client for testing without API calls
- Sample test data
- FastAPI test client configuration
"""

import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Set dummy API key before importing app modules to avoid initialization errors
os.environ["OPENAI_API_KEY"] = "test_api_key_for_pytest"

from app.main import app
from app.core.rate_limiter import reset_rate_limiter


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests.
    
    Pytest-asyncio requires this fixture for session-scoped async fixtures.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_limiter():
    """Reset rate limiter before each test.
    
    Ensures clean state between tests.
    """
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def client():
    """FastAPI test client fixture.
    
    Provides a test client for making requests to the API.
    
    Returns:
        TestClient: FastAPI test client
        
    Example:
        def test_health_check(client):
            response = client.get("/")
            assert response.status_code == 200
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_data_item():
    """Sample DataItem for testing.
    
    Returns:
        dict: Valid DataItem dictionary
    """
    return {
        "mlsnum": "ML12345",
        "mls_id": "TESTMLS",
        "Remarks": "Beautiful 3BR/2BA home with spacious backyard.",
        "PrivateRemarks": "Seller motivated. Great neighborhood.",
        "Directions": "Take Main St north, turn right on Oak Ave"
    }


@pytest.fixture
def sample_compliance_request(sample_data_item):
    """Sample ComplianceRequest for testing.
    
    Returns:
        dict: Valid ComplianceRequest dictionary
    """
    return {
        "AIViolationID": [
            {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}
        ],
        "Data": [sample_data_item]
    }


@pytest.fixture
def sample_batch_request():
    """Sample batch request with multiple records.
    
    Returns:
        dict: ComplianceRequest with 5 records
    """
    return {
        "AIViolationID": [
            {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"},
            {"ID": "COMP", "CheckColumns": "Remarks,PrivateRemarks"}
        ],
        "Data": [
            {
                "mlsnum": f"ML{i:05d}",
                "mls_id": "TESTMLS",
                "Remarks": f"Test remarks {i}",
                "PrivateRemarks": f"Private remarks {i}",
                "Directions": ""
            }
            for i in range(5)
        ]
    }


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response.
    
    Returns:
        MagicMock: Mocked OpenAI response with headers and usage
    """
    response = MagicMock()
    response.output_text = '''```json
{
    "result": {
        "public_remarks": [],
        "private_agent_remarks": []
    }
}
```'''
    
    # Mock usage
    response.usage = MagicMock()
    response.usage.total_tokens = 150
    
    # Mock rate limit headers
    response.http_response = MagicMock()
    response.http_response.headers = {
        'x-ratelimit-limit-tokens': '10000000',
        'x-ratelimit-remaining-tokens': '9999850',
        'x-ratelimit-reset-tokens': '6m0s',
        'x-ratelimit-limit-requests': '10000',
        'x-ratelimit-remaining-requests': '9999',
        'x-ratelimit-reset-requests': '1s'
    }
    
    return response


@pytest.fixture
def mock_openai_client(mock_openai_response):
    """Mock AsyncOpenAI client.
    
    Returns:
        AsyncMock: Mocked OpenAI client that returns mock responses
        
    Example:
        @pytest.mark.asyncio
        async def test_rule(mock_openai_client):
            # Client will return mock_openai_response
            response = await mock_openai_client.responses.create(...)
    """
    client = AsyncMock()
    client.responses.create = AsyncMock(return_value=mock_openai_response)
    return client
