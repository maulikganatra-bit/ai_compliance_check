"""
FastAPI dependencies for authentication.
"""

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Union
from app.auth.jwt_handler import verify_token
from app.auth.models import User, get_user, TokenData
from app.auth.api_key_auth import api_key_header, verify_api_key
from app.core.logger import app_logger

# Security scheme for JWT tokens
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Get the current authenticated user from the JWT token.
    
    Args:
        credentials: HTTP Authorization credentials with Bearer token
        
    Returns:
        User: The authenticated user
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Extract token from credentials
    # If no credentials provided, raise unauthorized
    if credentials is None:
        raise credentials_exception

    token = credentials.credentials
    
    # Verify and decode token
    payload = verify_token(token, token_type="access")
    if payload is None:
        raise credentials_exception
    
    # Extract username from token
    username: Optional[str] = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    # Get user from database
    user = get_user(username)
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get the current active user (not disabled).
    
    Args:
        current_user: The current authenticated user
        
    Returns:
        User: The active user
        
    Raises:
        HTTPException: If user is disabled
    """
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def verify_authentication(
    api_key: Optional[str] = Security(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Union[str, User]]:
    """
    Combined authentication: accepts either API Key OR JWT token.
    
    This dependency allows both:
    - API Key authentication (for automated services like SQL jobs)
    - JWT token authentication (for frontend users)
    
    Args:
        api_key: Optional API key from X-API-Key header
        credentials: Optional JWT token from Authorization header
        
    Returns:
        Dict containing authentication info:
        - For API key: {"auth_type": "api_key", "client": "service", ...}
        - For JWT: {"auth_type": "jwt", "user": User object}
        
    Raises:
        HTTPException: If neither authentication method is provided or both are invalid
    """
    # Try API Key authentication first
    if api_key:
        try:
            api_key_info = await verify_api_key(api_key)
            app_logger.info("Request authenticated via API Key")
            return api_key_info
        except HTTPException:
            # API key provided but invalid
            raise
    
    # Try JWT token authentication
    if credentials:
        try:
            # Extract token from credentials
            token = credentials.credentials
            
            # Verify and decode token
            payload = verify_token(token, token_type="access")
            if payload is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired JWT token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Extract username from token
            username: Optional[str] = payload.get("sub")
            if username is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Get user from database
            user = get_user(username)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Check if user is active
            if user.disabled:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Inactive user"
                )
            
            app_logger.info(f"Request authenticated via JWT for user: {username}")
            return {
                "auth_type": "jwt",
                "user": user,
                "username": username
            }
        except HTTPException:
            # JWT provided but invalid
            raise
    
    # Neither authentication method provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide either X-API-Key header or Authorization Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
