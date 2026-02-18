"""
API Key authentication for service-to-service communication.

This module provides API key authentication for automated jobs,
scheduled tasks, and server-to-server communication (e.g., SQL stored procedures).
"""

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from typing import Optional, Dict
from app.core.config import SERVICE_API_KEY
from app.core.logger import app_logger

# API Key header name
API_KEY_NAME = "X-API-Key"

# Create API key header security scheme
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> Dict[str, str]:
    """
    Verify API key for service authentication.
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        Dict with authentication info (type='service', client='sql_scheduler')
        
    Raises:
        HTTPException: If API key is invalid or missing
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API Key. Include X-API-Key header."
        )
    
    # Verify API key matches configured service key
    if api_key != SERVICE_API_KEY:
        app_logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key"
        )
    
    app_logger.info("API key authentication successful")
    return {
        "auth_type": "api_key",
        "client": "service",
        "description": "Automated service (e.g., SQL scheduled job)"
    }
