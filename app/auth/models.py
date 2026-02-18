"""
Authentication models and user storage.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timezone


class User(BaseModel):
    """User model"""
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    disabled: bool = False
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserInDB(User):
    """User model with hashed password"""
    pass


class UserCreate(BaseModel):
    """User creation request"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request model"""
    username: str
    password: str


class Token(BaseModel):
    """Token response model"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token data extracted from JWT"""
    username: Optional[str] = None
    exp: Optional[datetime] = None


class UserResponse(BaseModel):
    """User response model (without password)"""
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    disabled: bool = False
    created_at: datetime


# In-memory user database (replace with real database in production)
# Password for demo user is: "password123"
fake_users_db = {
    "testuser": {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "disabled": False,
        "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
        "created_at": datetime.now(timezone.utc)
    }
}


def get_user(username: str) -> Optional[UserInDB]:
    """Get user from database by username"""
    if username in fake_users_db:
        user_dict = fake_users_db[username]
        return UserInDB(**user_dict)
    return None


def create_user(user_data: UserCreate, hashed_password: str) -> UserInDB:
    """Create a new user in the database"""
    user_dict = {
        "username": user_data.username,
        "email": user_data.email,
        "full_name": user_data.full_name,
        "disabled": False,
        "hashed_password": hashed_password,
        "created_at": datetime.now(timezone.utc)
    }
    fake_users_db[user_data.username] = user_dict
    return UserInDB(**user_dict)
