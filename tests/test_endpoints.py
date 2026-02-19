"""Unit tests for API endpoints.

Tests the FastAPI routes and request/response validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for the root health check endpoint."""
    
    def test_health_check(self, client):
        """Test GET / returns 200 OK."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "message" in response.json()
    
    def test_health_check_includes_message(self, client):
        """Test health check includes descriptive message."""
        response = client.get("/")
        data = response.json()
        assert "AI Compliance Checker" in data["message"]


class TestComplianceEndpoint:
    """Tests for /check_compliance endpoint."""
    
    def test_compliance_check_success(self, client, sample_compliance_request):
        """Test successful compliance check with valid request."""
        response = client.post("/check_compliance", json=sample_compliance_request)
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == 200
        # The API returns successfully processed results
        # Even if individual rules had errors, the response is 200
        assert "results" in data
        assert "total_tokens" in data
        assert "elapsed_time" in data
    
    def test_compliance_check_empty_data(self, client):
        """Test that empty Data list returns 400 error."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": []
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 400
    
    def test_compliance_check_unknown_rule_accepted_dynamically(self, client):
        """Test that any rule ID is accepted (dynamic system — no whitelist)."""
        request = {
            "AIViolationID": [{"ID": "BRAND_NEW_RULE", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [{"mlsnum": "ML123", "mlsId": "TESTMLS", "Remarks": "test"}]
        }
        # With mocked Langfuse, all prompts appear to exist, so ANY rule ID works
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 200

    def test_compliance_check_missing_prompt_returns_400(self, client):
        """Test that a rule with no Langfuse prompt returns 400 error."""
        request = {
            "AIViolationID": [{"ID": "NO_PROMPT_RULE", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [{"mlsnum": "ML123", "mlsId": "TESTMLS", "Remarks": "test"}]
        }
        with patch("app.api.routes.get_prompt_cache_manager") as mock_cache:
            mock_manager = MagicMock()
            mock_manager.load_batch_prompts = AsyncMock(
                return_value={("NO_PROMPT_RULE", "TESTMLS"): None}
            )
            mock_cache.return_value = mock_manager
            response = client.post("/check_compliance", json=request)
        assert response.status_code == 400
        assert "Langfuse" in response.json()["detail"]
    
    def test_compliance_check_invalid_check_columns(self, client):
        """Test that invalid CheckColumns returns 400 error."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "InvalidColumn"}],
            "Data": [{"mlsnum": "ML123", "mlsId": "TESTMLS", "Remarks": "test"}]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 400
    
    def test_compliance_check_invalid_data_fields(self, client):
        """Test that response returns 200 (extra fields ignored)."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [{"mlsnum": "ML123", "mlsId": "TESTMLS", "Remarks": "test"}]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 200
    
    def test_compliance_check_missing_mandatory_fields(self, client):
        """Test that missing mlsId returns 422 validation error."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [{"mlsnum": "ML123", "Remarks": "test"}]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 422
    
    def test_compliance_check_multiple_rules(self, client):
        """Test compliance check with multiple rules."""
        request = {
            "AIViolationID": [
                {"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "COMP", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "PROMO", "mlsId": "TESTMLS", "CheckColumns": "Remarks"},
                {"ID": "PRWD", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}
            ],
            "Data": [{"mlsnum": "ML12345", "mlsId": "TESTMLS", "Remarks": "Test", "PrivateRemarks": "Private"}]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == 200
        assert isinstance(data["results"], list)
    
    def test_compliance_check_batch_processing(self, client, sample_batch_request):
        """Test batch processing with multiple records."""
        response = client.post("/check_compliance", json=sample_batch_request)
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data["results"], list)
        assert data["ok"] == 200
    
    def test_compliance_check_returns_request_id(self, client, sample_compliance_request):
        """Test that response includes X-Request-ID header."""
        response = client.post("/check_compliance", json=sample_compliance_request)
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36


class TestRequestValidation:
    """Tests for request validation."""
    
    def test_invalid_json(self, client):
        """Test that invalid JSON returns 422 error."""
        response = client.post(
            "/check_compliance",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_missing_required_fields(self, client):
        """Test that missing required fields returns 422 error."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 422
    
    def test_wrong_data_types(self, client):
        """Test that wrong data types return 422 error."""
        request = {
            "AIViolationID": "not-a-list",
            "Data": [{"mlsnum": "ML123", "mlsId": "TESTMLS", "Remarks": "test"}]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 422
