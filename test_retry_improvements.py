"""Quick test to demonstrate retry handler improvements."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
from openai import APIError
from app.core.retry_handler import retry_with_backoff


@retry_with_backoff(max_retries=3, base_delay=0.1)
async def test_function_with_retries():
    """Test function that will be called by retry handler."""
    return "success"


async def test_api_error_without_status_code():
    """Test that APIError without status_code is now retried."""
    print("\n1. Testing APIError without status_code (should retry)...")
    
    call_count = 0
    
    @retry_with_backoff(max_retries=2, base_delay=0.1)
    async def failing_function():
        nonlocal call_count
        call_count += 1
        print(f"   Attempt {call_count}")
        
        if call_count < 3:
            # Raise APIError without status_code
            error = APIError("Connection error", request=MagicMock(), body=None)
            # Note: No status_code attribute
            raise error
        return "success"
    
    result = await failing_function()
    print(f"   ✅ Result: {result} (after {call_count} attempts)")
    assert call_count == 3, "Should have retried"


async def test_network_errors_are_retried():
    """Test that network errors are now retried."""
    print("\n2. Testing ConnectionError (should retry)...")
    
    call_count = 0
    
    @retry_with_backoff(max_retries=2, base_delay=0.1)
    async def network_failing_function():
        nonlocal call_count
        call_count += 1
        print(f"   Attempt {call_count}")
        
        if call_count < 3:
            raise ConnectionError("Network unreachable")
        return "success"
    
    result = await network_failing_function()
    print(f"   ✅ Result: {result} (after {call_count} attempts)")
    assert call_count == 3, "Should have retried"


async def test_client_errors_not_retried():
    """Test that 4xx client errors are still not retried."""
    print("\n3. Testing 400 client error (should NOT retry)...")
    
    call_count = 0
    
    @retry_with_backoff(max_retries=2, base_delay=0.1)
    async def client_error_function():
        nonlocal call_count
        call_count += 1
        print(f"   Attempt {call_count}")
        
        error = APIError("Bad request", request=MagicMock(), body=None)
        error.status_code = 400
        raise error
    
    try:
        await client_error_function()
        assert False, "Should have raised"
    except APIError:
        print(f"   ✅ Failed immediately (attempt {call_count}) - correct behavior")
        assert call_count == 1, "Should NOT have retried"


async def test_server_errors_are_retried():
    """Test that 5xx server errors are retried."""
    print("\n4. Testing 503 server error (should retry)...")
    
    call_count = 0
    
    @retry_with_backoff(max_retries=2, base_delay=0.1)
    async def server_error_function():
        nonlocal call_count
        call_count += 1
        print(f"   Attempt {call_count}")
        
        if call_count < 3:
            error = APIError("Service unavailable", request=MagicMock(), body=None)
            error.status_code = 503
            raise error
        return "success"
    
    result = await server_error_function()
    print(f"   ✅ Result: {result} (after {call_count} attempts)")
    assert call_count == 3, "Should have retried"


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Retry Handler Improvements")
    print("=" * 60)
    
    await test_api_error_without_status_code()
    await test_network_errors_are_retried()
    await test_client_errors_not_retried()
    await test_server_errors_are_retried()
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
