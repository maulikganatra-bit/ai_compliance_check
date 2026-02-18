"""
Tests for authentication endpoints and JWT functionality.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.models import fake_users_db
from app.auth.password_handler import hash_password
from datetime import datetime, timezone


@pytest.fixture
def auth_client():
    """Test client for auth tests (no default API key header)."""
    with TestClient(app) as tc:
        yield tc


@pytest.fixture(autouse=True)
def reset_users_db():
    """Reset users database before each test"""
    fake_users_db.clear()
    # Add test user with known password
    fake_users_db["testuser"] = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "disabled": False,
        "hashed_password": hash_password("password123"),
                "created_at": datetime.now(timezone.utc)
    }
    yield
    fake_users_db.clear()


class TestUserRegistration:
    """Test user registration endpoint"""

    def test_register_new_user(self, auth_client):
        """Test successful user registration"""
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123",
                "full_name": "New User"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert "hashed_password" not in data
        assert "password" not in data

    def test_register_duplicate_username(self, auth_client):
        """Test registration with existing username fails"""
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "testuser",  # Already exists
                "email": "another@example.com",
                "password": "password123"
            }
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    def test_register_invalid_email(self, auth_client):
        """Test registration with invalid email fails"""
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "newuser",
                "email": "not_an_email",
                "password": "password123"
            }
        )
        assert response.status_code == 422  # Validation error

    def test_register_short_password(self, auth_client):
        """Test registration with short password fails"""
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "short"  # Less than 8 characters
            }
        )
        assert response.status_code == 422  # Validation error


class TestLogin:
    """Test login endpoint"""

    def test_login_success(self, auth_client):
        """Test successful login"""
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

        # Verify refresh token cookie is set
        assert "refresh_token" in response.cookies

    def test_login_wrong_password(self, auth_client):
        """Test login with wrong password fails"""
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()

    def test_login_nonexistent_user(self, auth_client):
        """Test login with non-existent user fails"""
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "nonexistent",
                "password": "password123"
            }
        )
        assert response.status_code == 401

    def test_login_disabled_user(self, auth_client):
        """Test login with disabled user fails"""
        fake_users_db["testuser"]["disabled"] = True
        response = auth_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        assert response.status_code == 400
        assert "inactive" in response.json()["detail"].lower()


class TestTokenRefresh:
    """Test token refresh endpoint"""

    def test_refresh_token_success(self, auth_client):
        """Test successful token refresh"""
        # First login to get tokens
        login_response = auth_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        refresh_token = login_response.json()["refresh_token"]

        # Refresh tokens
        response = auth_client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_token_invalid(self, auth_client):
        """Test refresh with invalid token fails"""
        response = auth_client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid_token"}
        )
        assert response.status_code == 401

    def test_refresh_token_missing(self, auth_client):
        """Test refresh without token fails"""
        response = auth_client.post("/auth/refresh", json={})
        assert response.status_code == 422  # Missing required field


class TestProtectedEndpoints:
    """Test authentication on protected endpoints"""

    def test_get_current_user_success(self, auth_client):
        """Test getting current user with valid token"""
        # Login first
        login_response = auth_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        access_token = login_response.json()["access_token"]

        # Get current user info
        response = auth_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "password" not in data
        assert "hashed_password" not in data

    def test_get_current_user_no_token(self, auth_client):
        """Test accessing protected endpoint without token fails"""
        response = auth_client.get("/auth/me")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    def test_get_current_user_invalid_token(self, auth_client):
        """Test accessing protected endpoint with invalid token fails"""
        response = auth_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401

    def test_check_compliance_requires_auth(self, auth_client):
        """Test compliance endpoint requires authentication"""
        response = auth_client.post(
            "/check_compliance",
            json={
                "Data": [{"mlsnum": "123", "mlsId": "MLS1"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    def test_check_compliance_with_auth(self, auth_client):
        """Test compliance endpoint works with valid authentication"""
        # Login first
        login_response = auth_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        access_token = login_response.json()["access_token"]

        # Note: This will fail because we don't have OpenAI setup in tests,
        # but it should NOT fail with 401/403 (auth error)
        response = auth_client.post(
            "/check_compliance",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                    "Data": [{"mlsnum": "123", "mlsId": "MLS1", "Remarks": "Test"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        # Should not be auth error (401/403)
        assert response.status_code not in [401, 403]


class TestLogout:
    """Test logout endpoint"""

    def test_logout_success(self, auth_client):
        """Test successful logout"""
        response = auth_client.post("/auth/logout")
        assert response.status_code == 200
        assert "logged out" in response.json()["message"].lower()

        # Verify refresh token cookie is deleted
        # (In real scenario, would check cookie is expired)


class TestJWTSecurity:
    """Test JWT security features"""

    def test_access_token_contains_correct_type(self):
        """Test access token has correct type claim"""
        from app.auth.jwt_handler import create_access_token, verify_token

        token = create_access_token(data={"sub": "testuser"})
        payload = verify_token(token, token_type="access")

        assert payload is not None
        assert payload["type"] == "access"

    def test_refresh_token_contains_correct_type(self):
        """Test refresh token has correct type claim"""
        from app.auth.jwt_handler import create_refresh_token, verify_token

        token = create_refresh_token(data={"sub": "testuser"})
        payload = verify_token(token, token_type="refresh")

        assert payload is not None
        assert payload["type"] == "refresh"

    def test_cannot_use_refresh_token_as_access_token(self, auth_client):
        """Test refresh token cannot be used for authentication"""
        # Get refresh token
        login_response = auth_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        refresh_token = login_response.json()["refresh_token"]

        # Try to use refresh token for protected endpoint
        response = auth_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {refresh_token}"}
        )
        assert response.status_code == 401  # Should fail

    def test_password_hashing(self):
        """Test passwords are properly hashed"""
        from app.auth.password_handler import hash_password, verify_password

        password = "my_secure_password"
        hashed = hash_password(password)

        # Hash should be different from original
        assert hashed != password

        # Verify password works
        assert verify_password(password, hashed) is True
        assert verify_password("wrong_password", hashed) is False
