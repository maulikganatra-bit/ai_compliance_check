"""
Tests for API Key authentication.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import SERVICE_API_KEY
from app.auth.models import fake_users_db
from app.auth.password_handler import hash_password
from datetime import datetime, timezone

client = TestClient(app)


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


class TestAPIKeyAuthentication:
    """Test API key authentication for service-to-service calls"""
    
    def test_api_key_success(self):
        """Test successful API key authentication"""
        response = client.post(
            "/check_compliance",
            headers={"X-API-Key": SERVICE_API_KEY},
            json={
                "Data": [{"mlsnum": "123", "mlsId": "MLS1", "Remarks": "Test property"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        # Should not be auth error (401/403)
        assert response.status_code not in [401, 403]
    
    def test_api_key_invalid(self):
        """Test with invalid API key"""
        response = client.post(
            "/check_compliance",
            headers={"X-API-Key": "invalid-key-123"},
            json={
                "Data": [{"mlsnum": "123", "mlsId": "MLS1"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        assert response.status_code == 403
        assert "Invalid API Key" in response.json()["detail"]
    
    def test_api_key_missing(self, client_no_auth):
        """Test without API key or JWT token"""
        response = client_no_auth.post(
            "/check_compliance",
            json={
                "Data": [{"mlsnum": "123", "mlsId": "MLS1"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]
    
    def test_api_key_empty_string(self):
        """Test with empty API key"""
        response = client.post(
            "/check_compliance",
            headers={"X-API-Key": ""},
            json={
                "Data": [{"mlsnum": "123", "mlsId": "MLS1"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        assert response.status_code in [401, 403]


class TestCombinedAuthentication:
    """Test that both JWT and API key authentication work"""
    
    def test_jwt_still_works(self):
        """Verify JWT authentication still works after adding API key"""
        # First login to get JWT token
        login_response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]
        
        # Use JWT token for compliance check
        response = client.post(
            "/check_compliance",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                    "Data": [{"mlsnum": "123", "mlsId": "MLS1", "Remarks": "Test"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        # Should not be auth error
        assert response.status_code not in [401, 403]
    
    def test_api_key_and_jwt_both_provided(self):
        """Test when both API key and JWT are provided (API key takes precedence)"""
        # Get JWT token
        login_response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        access_token = login_response.json()["access_token"]
        
        # Send both API key and JWT
        response = client.post(
            "/check_compliance",
            headers={
                "X-API-Key": SERVICE_API_KEY,
                "Authorization": f"Bearer {access_token}"
            },
            json={
                    "Data": [{"mlsnum": "123", "mlsId": "MLS1", "Remarks": "Test"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        # Should work (API key has precedence)
        assert response.status_code not in [401, 403]
    
    def test_invalid_api_key_with_valid_jwt(self):
        """Test that invalid API key prevents fallback to JWT"""
        # Get valid JWT token
        login_response = client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "password123"
            }
        )
        access_token = login_response.json()["access_token"]
        
        # Send invalid API key with valid JWT
        response = client.post(
            "/check_compliance",
            headers={
                "X-API-Key": "invalid-key",
                "Authorization": f"Bearer {access_token}"
            },
            json={
                    "Data": [{"mlsnum": "123", "mlsId": "MLS1", "Remarks": "Test"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        # Should fail because API key is invalid (API key checked first)
        assert response.status_code == 403


class TestAPIKeyFormatting:
    """Test various API key formats and edge cases"""
    
    def test_api_key_case_sensitive(self):
        """Test that API key is case sensitive"""
        # Try with wrong case
        wrong_case_key = SERVICE_API_KEY.swapcase() if SERVICE_API_KEY else "WRONG"
        
        response = client.post(
            "/check_compliance",
            headers={"X-API-Key": wrong_case_key},
            json={
                    "Data": [{"mlsnum": "123", "mlsId": "MLS1"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        assert response.status_code == 403
    
    def test_api_key_with_whitespace(self):
        """Test API key with leading/trailing whitespace"""
        response = client.post(
            "/check_compliance",
            headers={"X-API-Key": f" {SERVICE_API_KEY} "},
            json={
                    "Data": [{"mlsnum": "123", "mlsId": "MLS1"}],
                "AIViolationID": [{"ID": "AI_RULE_1", "CheckColumns": "Remarks"}]
            }
        )
        # Should fail - whitespace not stripped
        assert response.status_code == 403
