
"""Main FastAPI application entry point.

This module initializes the FastAPI application with:
- Lifespan context manager for startup/shutdown handling
- Request ID middleware for request tracking
- HTTP/2 connection pooling for OpenAI API calls
- Dynamic rate limiting initialization
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router
from app.core.logger import app_logger
from app.core.middleware import RequestIDMiddleware
from app.core.rate_limiter import get_rate_limiter
from app.core.config import MAX_CONNECTIONS, MAX_KEEPALIVE_CONNECTIONS, API_TIMEOUT
import httpx
from openai import AsyncOpenAI

# Global OpenAI client with connection pooling
# This client is shared across all requests for efficient connection reuse
openai_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager - handles startup and shutdown events.
    
    Startup phase:
    1. Initialize rate limiter for tracking OpenAI API limits
    2. Create HTTP/2 connection pool (200 max connections, 50 keepalive)
    3. Initialize AsyncOpenAI client with connection pool
    4. Inject client into rule functions
    
    Shutdown phase:
    1. Close all HTTP connections gracefully
    2. Log final rate limiter statistics
    """
    # === STARTUP PHASE ===
    app_logger.info("FastAPI application starting up")
    
    # Initialize rate limiter - tracks token/request budgets from OpenAI headers
    rate_limiter = get_rate_limiter()
    app_logger.info(f"Rate limiter initialized")
    
    # Initialize OpenAI client with connection pooling for high performance
    # Connection pool allows reusing TCP connections across requests
    # Benefits: Reduces latency (no TCP handshake), handles high concurrency
    global openai_client
    httpx_client = httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=MAX_CONNECTIONS,  # Max 200 concurrent connections
            max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS  # Keep 50 connections alive
        ),
        timeout=API_TIMEOUT  # 30 second timeout per request
    )
    openai_client = AsyncOpenAI(
        http_client=httpx_client,
        max_retries=0  # Disable built-in retries (we handle retries with exponential backoff)
    )
    app_logger.info(
        f"OpenAI client initialized with connection pool "
        f"(max_connections={MAX_CONNECTIONS}, keepalive={MAX_KEEPALIVE_CONNECTIONS})"
    )
    
    # Store client in app state for access in routes
    app.state.openai_client = openai_client
    
    # Update the global client in base.py
    from app.rules import base
    base.set_client(openai_client)
    
    yield
    
    # Shutdown: runs when the application is shutting down
    app_logger.info("FastAPI application shutting down")
    
    # Close HTTP client
    if openai_client and hasattr(openai_client, 'http_client') and openai_client.http_client:
        await openai_client.http_client.aclose()
        app_logger.info("OpenAI HTTP client closed")
    
    # Log final rate limiter statistics
    limiter_stats = rate_limiter.get_stats()
    app_logger.info(f"Final rate limiter stats: {limiter_stats}")

# Create FastAPI application instance
app = FastAPI(
    title="AI Compliance Checker API",
    description="Async multi-rule compliance checker with request ID tracking",
    version="3.0.0",
    lifespan=lifespan  # Attach lifespan manager for startup/shutdown
)

# Add request ID middleware - injects unique UUID into each request
# This enables request tracing across logs and creates per-request log files
app.add_middleware(RequestIDMiddleware)

# Include API routes from routes.py
app.include_router(router)

# Health check endpoint - verifies API is running
@app.get("/")
async def root():
    """Simple health check endpoint."""
    app_logger.debug("Health check endpoint called")
    return {"status": "ok", "message": "AI Compliance Checker API is running!"}
