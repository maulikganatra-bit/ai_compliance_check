"""Retry handler with exponential backoff for OpenAI API calls.

This module provides a decorator that automatically retries failed API calls
with exponential backoff and jitter.

Exponential Backoff Strategy:
- Attempt 1: Wait 1s (BASE_DELAY)
- Attempt 2: Wait 2s (BASE_DELAY * 2)
- Attempt 3: Wait 4s (BASE_DELAY * 4)
- Each wait includes random jitter (0-1s) to prevent thundering herd

Handles these OpenAI errors:
- RateLimitError (429): Hit rate limits, wait and retry
- APITimeoutError: Request timed out, retry
- APIError (500-504): Server errors, retry
- Other errors: Don't retry (likely client errors)

Usage:
    @retry_with_backoff(max_retries=3)
    async def call_openai_api():
        response = await client.responses.create(...)
        return response
"""
import asyncio
import random
from functools import wraps
from typing import Callable, Any
from openai import RateLimitError, APIError, APITimeoutError
from app.core.logger import rules_logger
from app.core.config import MAX_RETRIES, BASE_RETRY_DELAY, MAX_RETRY_DELAY, JITTER_RANGE


def retry_with_backoff(max_retries: int = MAX_RETRIES, base_delay: float = BASE_RETRY_DELAY):
    """Decorator to retry async functions with exponential backoff.
    
    Implements retry logic with exponential backoff and random jitter.
    Automatically retries on transient errors (rate limits, timeouts, server errors).
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds, doubles each retry (default: 1.0)
    
    Returns:
        Decorator function that wraps async functions
        
    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        async def my_api_call():
            return await client.api_call()
            
        # If it fails:
        # - Attempt 1 fails → wait ~1-2s → retry
        # - Attempt 2 fails → wait ~2-3s → retry
        # - Attempt 3 fails → wait ~4-5s → retry
        # - Attempt 4 fails → raise exception
    
    Handles:
        - RateLimitError (429): OpenAI rate limit hit
        - APITimeoutError: Request timed out
        - APIError (500-504): Server errors (retryable)
        - Other exceptions: Not retried (client errors)
    """
    def decorator(func: Callable) -> Callable:
        """Inner decorator function."""
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            """Wrapper that implements retry logic."""
            last_exception = None
            
            # Try up to max_retries + 1 times (includes initial attempt)
            for attempt in range(max_retries + 1):
                try:
                    # Execute the wrapped function
                    return await func(*args, **kwargs)
                    
                except RateLimitError as e:
                    # OpenAI rate limit hit (429 error)
                    last_exception = e
                    if attempt == max_retries:
                        # Exhausted all retries
                        rules_logger.error(f"Rate limit error after {max_retries} retries: {str(e)}")
                        raise
                    
                    # Calculate exponential backoff delay
                    # Attempt 0: 1.0 * (2^0) = 1.0s
                    # Attempt 1: 1.0 * (2^1) = 2.0s
                    # Attempt 2: 1.0 * (2^2) = 4.0s
                    # Cap at MAX_RETRY_DELAY (16s)
                    delay = min(base_delay * (2 ** attempt), MAX_RETRY_DELAY)
                    
                    # Add random jitter to prevent thundering herd
                    # Jitter spreads out retries from multiple requests
                    jitter = random.uniform(0, JITTER_RANGE)
                    total_delay = delay + jitter
                    
                    rules_logger.warning(
                        f"Rate limit hit. Retry {attempt + 1}/{max_retries} after {total_delay:.2f}s"
                    )
                    await asyncio.sleep(total_delay)
                    
                except APITimeoutError as e:
                    # Request timed out (exceeded API_TIMEOUT)
                    last_exception = e
                    if attempt == max_retries:
                        rules_logger.error(f"Timeout error after {max_retries} retries: {str(e)}")
                        raise
                    
                    # Same exponential backoff logic
                    delay = min(base_delay * (2 ** attempt), MAX_RETRY_DELAY)
                    jitter = random.uniform(0, JITTER_RANGE)
                    total_delay = delay + jitter
                    
                    rules_logger.warning(
                        f"Timeout error. Retry {attempt + 1}/{max_retries} after {total_delay:.2f}s"
                    )
                    await asyncio.sleep(total_delay)
                    
                except APIError as e:
                    # General API error - only retry on server errors
                    last_exception = e
                    
                    # Check if this is a retryable error
                    should_retry = False
                    status_code = getattr(e, 'status_code', None)
                    
                    if status_code:
                        # Retry on server errors (5xx)
                        should_retry = status_code in [500, 502, 503, 504]
                        error_type = f"API error {status_code}"
                    else:
                        # No status code - could be connection error, retry it
                        should_retry = True
                        error_type = "API error (no status code)"
                    
                    if should_retry:
                        if attempt == max_retries:
                            rules_logger.error(f"{error_type} after {max_retries} retries: {str(e)}")
                            raise
                        
                        delay = min(base_delay * (2 ** attempt), MAX_RETRY_DELAY)
                        jitter = random.uniform(0, JITTER_RANGE)
                        total_delay = delay + jitter
                        
                        rules_logger.warning(
                            f"{error_type}. Retry {attempt + 1}/{max_retries} after {total_delay:.2f}s"
                        )
                        await asyncio.sleep(total_delay)
                    else:
                        # Don't retry on client errors (400, 401, 403, 404, etc.)
                        rules_logger.error(f"Non-retryable API error {status_code}: {str(e)}")
                        raise
                
                except (ConnectionError, TimeoutError, OSError) as e:
                    # Network-level errors - these are transient, should retry
                    last_exception = e
                    if attempt == max_retries:
                        rules_logger.error(f"Network error after {max_retries} retries: {str(e)}")
                        raise
                    
                    delay = min(base_delay * (2 ** attempt), MAX_RETRY_DELAY)
                    jitter = random.uniform(0, JITTER_RANGE)
                    total_delay = delay + jitter
                    
                    rules_logger.warning(
                        f"Network error ({type(e).__name__}). Retry {attempt + 1}/{max_retries} after {total_delay:.2f}s"
                    )
                    await asyncio.sleep(total_delay)
                        
                except Exception as e:
                    # Unexpected error - don't retry (likely programming error)
                    rules_logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
                    raise
                
        return wrapper
    return decorator
