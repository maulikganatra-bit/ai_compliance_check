"""Request ID middleware for request tracing and logging.

This middleware:
1. Generates a unique UUID for each incoming request
2. Stores it in a context variable (propagates through async calls)
3. Adds it to request state for route handlers
4. Returns it in response headers for client-side tracking
5. Enables per-request log files (logs/request_{uuid}.log)
"""

import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Context variable to store request ID across async operations
# ContextVar ensures thread-safety in async environments
request_id_ctx_var: ContextVar[str] = ContextVar('request_id', default=None)

def get_request_id() -> str:
    """Get the current request ID from context variable.
    
    Returns:
        Request UUID string, or None if not set
    """
    return request_id_ctx_var.get()

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to generate and attach unique request ID to each request.
    
    Flow:
    1. Request arrives → Generate UUID
    2. Store in context variable (available in all async functions)
    3. Store in request.state (available in route handlers)
    4. Process request
    5. Add UUID to response header X-Request-ID
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process each request and inject request ID.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler in chain
            
        Returns:
            Response with X-Request-ID header added
        """
        # Generate unique request ID (UUID4 format)
        request_id = str(uuid.uuid4())
        
        # Store in context variable - propagates through all async calls
        # Used by logger to add request_id to all log entries
        request_id_ctx_var.set(request_id)
        
        # Add to request state for access in route handlers
        # Example: request.state.request_id in check_compliance()
        request.state.request_id = request_id
        
        # Process request through remaining middleware and route handler
        response = await call_next(request)
        
        # Add request ID to response headers for client tracking
        # Client can use this UUID to correlate requests with server logs
        response.headers["X-Request-ID"] = request_id
        
        return response
