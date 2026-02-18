"""
Authentication routes for login, registration, and token management.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from typing import Optional
from datetime import timedelta

from app.auth.models import (
    User,
    UserCreate,
    UserResponse,
    LoginRequest,
    Token,
    get_user,
    create_user,
)
from app.auth.password_handler import verify_password, hash_password
from app.auth.jwt_handler import create_access_token, create_refresh_token, verify_token
from app.auth.dependencies import get_current_active_user
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """
    Register a new user.
    
    Args:
        user_data: User registration data
        
    Returns:
        UserResponse: Created user information (without password)
        
    Raises:
        HTTPException: If username already exists
    """
    # Check if user already exists
    existing_user = get_user(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Hash password and create user
    hashed_password = hash_password(user_data.password)
    new_user = create_user(user_data, hashed_password)
    
    return UserResponse(
        username=new_user.username,
        email=new_user.email,
        full_name=new_user.full_name,
        disabled=new_user.disabled,
        created_at=new_user.created_at
    )


@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, response: Response):
    """
    Login and get access and refresh tokens.
    
    Args:
        login_data: Login credentials (username and password)
        response: FastAPI response object to set cookies
        
    Returns:
        Token: Access and refresh tokens
        
    Raises:
        HTTPException: If credentials are invalid
    """
    # Authenticate user
    user = get_user(login_data.username)
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create tokens
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    refresh_token = create_refresh_token(
        data={"sub": user.username},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    
    # Set refresh token in httpOnly cookie for security
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,  # Prevents JavaScript access (XSS protection)
        secure=True,    # Requires HTTPS in production
        samesite="lax", # CSRF protection
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60  # Convert days to seconds
    )
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


class RefreshTokenRequest(BaseModel):
    """Refresh token request model"""
    refresh_token: str


@router.post("/refresh", response_model=Token)
async def refresh_tokens(request: RefreshTokenRequest, response: Response):
    """
    Refresh access token using refresh token.
    
    Args:
        request: Request body containing refresh token
        response: FastAPI response object to set new cookies
        
    Returns:
        Token: New access and refresh tokens
        
    Raises:
        HTTPException: If refresh token is invalid or expired
    """
    # TODO: In production, get refresh_token from httpOnly cookie
    # For now, accept from request body
    
    refresh_token = request.refresh_token
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required"
        )
    
    # Verify refresh token
    payload = verify_token(refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Get username from token
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Verify user still exists and is active
    user = get_user(username)
    if not user or user.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    new_access_token = create_access_token(
        data={"sub": username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    new_refresh_token = create_refresh_token(
        data={"sub": username},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    
    # Set new refresh token in cookie
    if response:
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        )
    
    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer"
    )


@router.post("/logout")
async def logout(response: Response):
    """
    Logout by clearing refresh token cookie.
    
    Args:
        response: FastAPI response object to clear cookies
        
    Returns:
        dict: Success message
    """
    # Clear refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=True,
        samesite="lax"
    )
    
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current authenticated user information.
    
    Args:
        current_user: Current authenticated user (from dependency)
        
    Returns:
        UserResponse: Current user information
    """
    return UserResponse(
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        disabled=current_user.disabled,
        created_at=current_user.created_at
    )
