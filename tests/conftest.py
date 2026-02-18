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
from unittest.mock import AsyncMock, MagicMock, patch


# Set minimal dummy env vars before importing app modules to avoid initialization errors
# Use setdefault so an existing environment value is not overridden on developer machines / CI
os.environ.setdefault("OPENAI_API_KEY", "test_openai_api_key_for_pytest")
os.environ.setdefault("SERVICE_API_KEY", "test_service_api_key")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-lf-test-key-for-pytest")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-test-key-for-pytest")
os.environ.setdefault("LANGFUSE_HOST", "https://cloud.langfuse.com")

# Mock Langfuse client at module level before importing app
import sys
from unittest.mock import AsyncMock

sys.modules['langfuse'] = MagicMock()

# Mock OpenAI client at module level before importing app

# Create a mock response object
def create_mock_response():
    """Create a mock OpenAI response object."""
    response = MagicMock()
    response.output_text = '''```json
{
    "result": {
        "public_remarks": ["Violation in public remarks"],
        "private_agent_remarks": ["Violation in private remarks"]
    }
}
```'''
    response.usage = MagicMock()
    response.usage.total_tokens = 150
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

# Create a mock AsyncOpenAI class
class MockAsyncOpenAI:
    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        self.responses = MagicMock()
        # Create an async mock for the create method that returns the mock response
        self.responses.create = AsyncMock(side_effect=lambda **kwargs: create_mock_response())

# Create real exception classes so they can be used in except clauses
class _MockAPIError(Exception):
    def __init__(self, message="API error", request=None, body=None):
        super().__init__(message)
        self.request = request
        self.body = body
        self.status_code = None

class _MockRateLimitError(_MockAPIError):
    def __init__(self, message="Rate limit exceeded", request=None, body=None, response=None):
        super().__init__(message, request, body)
        self.status_code = 429

class _MockAPITimeoutError(Exception):
    def __init__(self, request=None):
        super().__init__("Request timed out")
        self.request = request

# Patch the openai module before importing app
_mock_openai = MagicMock()
_mock_openai.AsyncOpenAI = MockAsyncOpenAI
_mock_openai.APIError = _MockAPIError
_mock_openai.RateLimitError = _MockRateLimitError
_mock_openai.APITimeoutError = _MockAPITimeoutError
sys.modules['openai'] = _mock_openai

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import SERVICE_API_KEY
from app.core.rate_limiter import reset_rate_limiter


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for direct rule testing."""
    response = MagicMock()
    response.output_text = '''```json
{
    "result": {
        "public_remarks": ["Violation in public remarks"],
        "private_agent_remarks": ["Violation in private remarks"]
    }
}
```'''
    response.usage = MagicMock()
    response.usage.total_tokens = 150
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
    """Mock AsyncOpenAI client for direct rule testing."""
    client = MagicMock()
    client.responses.create = AsyncMock(return_value=mock_openai_response)
    return client


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


@pytest.fixture(autouse=True)
def _mock_external_services():
    """Ensure no real API calls are made to any external service during tests.

    This fixture patches:
    - LANGFUSE_CLIENT everywhere (config + prompt_cache) → prevents Langfuse API calls
    - httpx.AsyncClient in app.main → prevents real HTTP connection pool creation
    """
    mock_langfuse = MagicMock()
    mock_httpx_client = MagicMock()
    # Give the mock httpx client an async aclose() so lifespan shutdown works
    mock_httpx_client.aclose = AsyncMock()
    with patch("app.core.config.LANGFUSE_CLIENT", mock_langfuse), \
         patch("app.core.prompt_cache.LANGFUSE_CLIENT", mock_langfuse), \
         patch("app.main.httpx.AsyncClient", return_value=mock_httpx_client):
        yield


@pytest.fixture
def client():
    """FastAPI test client fixture with mocked OpenAI client.
    
    Provides a test client for making requests to the API.
    All OpenAI API calls are automatically mocked via module-level patching.
    
    Returns:
        TestClient: FastAPI test client
        
    Example:
        def test_health_check(client):
            response = client.get("/")
            assert response.status_code == 200
    """
    # Provide a default client that includes the service API key header
    # so tests that exercise protected endpoints don't need to set it manually.
    headers = {"X-API-Key": SERVICE_API_KEY}
    
    with TestClient(app, headers=headers) as test_client:
        yield test_client


@pytest.fixture
def client_no_auth():
    """Test client without any authentication headers.

    Use this fixture for tests that need to verify behavior when no
    authentication is provided (e.g., missing API key / JWT).
    All OpenAI API calls are mocked via module-level patching.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_prompt_data():
    """Mock prompt_data dict matching the structure expected by rule functions.

    Rule functions do ``prompt_data['prompt']`` and ``prompt_data.get('config', {})``.
    The prompt template is a minimal Jinja2 template that renders without error.
    """
    return {
        "prompt": (
            "Check the following remarks for violations:\n"
            "Public: {{ public_remarks }}\n"
            "Private: {{ private_agent_remarks }}\n"
            "Directions: {{ directions }}\n"
            "Showing: {{ showing_instructions }}\n"
            "Confidential: {{ confidential_remarks }}\n"
            "Supplement: {{ supplement_remarks }}\n"
            "Concessions: {{ concessions }}\n"
            "Sale Factors: {{ sale_factors }}"
        ),
        "config": {
            "model": "gpt-4o",
            "temperature": "0.0",
            "max_output_tokens": "6095",
            "top_p": "1.0",
        },
        "version": "test-v1",
    }


@pytest.fixture
def sample_data_item():
    """Sample DataItem for testing.
    
    Returns:
        dict: Valid DataItem dictionary
    """
    return {
        "mlsnum": "ML12345",
        "mlsId": "TESTMLS",
        "Remarks": "Beautiful 3BR/2BA home with spacious backyard.",
        "PrivateRemarks": "Seller motivated. Great neighborhood."
    }


@pytest.fixture
def sample_compliance_request(sample_data_item):
    """Sample ComplianceRequest for testing.
    
    Returns:
        dict: Valid ComplianceRequest dictionary
    """
    return {
        "AIViolationID": [
            {"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"}
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
            {"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"},
            {"ID": "COMP", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"}
        ],
        "Data": [
            {
                "mlsnum": f"ML{i:05d}",
                "mlsId": "TESTMLS",
                "Remarks": f"Test remarks {i}",
                "PrivateRemarks": f"Private remarks {i}"
            }
            for i in range(5)
        ]
    }

