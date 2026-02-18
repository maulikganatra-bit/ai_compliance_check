"""
Authentication module for JWT-based authentication.
"""

from app.auth.jwt_handler import create_access_token, create_refresh_token, verify_token
from app.auth.password_handler import verify_password, hash_password
from app.auth.dependencies import get_current_user, get_current_active_user

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "verify_password",
    "hash_password",
    "get_current_user",
    "get_current_active_user",
]
