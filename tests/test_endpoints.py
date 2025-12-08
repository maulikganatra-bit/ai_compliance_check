"""Unit tests for API endpoints.

Tests the FastAPI routes and request/response validation.
"""

import pytest
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
        assert len(data["results"]) == 1
        assert data["results"][0]["mlsnum"] == "ML12345"
        assert "FAIR" in data["results"][0]
        assert "total_tokens" in data
        assert "elapsed_time" in data
    
    def test_compliance_check_empty_data(self, client):
        """Test that empty Data list returns 400 error."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks"}],
            "Data": []
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 400
        assert "Empty data list" in response.json()["detail"]
    
    def test_compliance_check_invalid_rule_id(self, client, sample_data_item):
        """Test that invalid rule ID returns 400 error."""
        request = {
            "AIViolationID": [{"ID": "INVALID_RULE", "CheckColumns": "Remarks"}],
            "Data": [sample_data_item]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 400
        assert "Invalid rule IDs" in response.json()["detail"]
        assert "INVALID_RULE" in response.json()["detail"]
    
    def test_compliance_check_invalid_check_columns(self, client, sample_data_item):
        """Test that invalid CheckColumns returns 400 error."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "InvalidColumn"}],
            "Data": [sample_data_item]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 400
        assert "Invalid CheckColumns" in response.json()["detail"]
    
    def test_compliance_check_invalid_data_fields(self, client):
        """Test that invalid Data fields returns 200 (extra fields are ignored)."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks"}],
            "Data": [{
                "mlsnum": "ML12345",
                "mls_id": "TESTMLS",
                "Remarks": "Test",
                "InvalidField": "This is ignored"
            }]
        }
        response = client.post("/check_compliance", json=request)
        # Extra fields are ignored, request proceeds normally
        assert response.status_code == 200
    
    def test_compliance_check_missing_mandatory_fields(self, client):
        """Test that missing mlsnum/mls_id returns 422 validation error."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks"}],
            "Data": [{
                "Remarks": "Test remarks"
                # Missing mlsnum and mls_id
            }]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 422  # Pydantic validation error
    
    def test_compliance_check_multiple_rules(self, client, sample_data_item):
        """Test compliance check with multiple rules."""
        request = {
            "AIViolationID": [
                {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "COMP", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "PROMO", "CheckColumns": "Remarks"}
            ],
            "Data": [sample_data_item]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 200
        
        data = response.json()
        result = data["results"][0]
        assert "FAIR" in result
        assert "COMP" in result
        assert "PROMO" in result
    
    def test_compliance_check_batch_processing(self, client, sample_batch_request, mock_openai_client, mock_openai_response):
        """Test batch processing with multiple records."""
        from unittest.mock import patch, AsyncMock
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        with patch('app.rules.base.client', mock_openai_client):
            response = client.post("/check_compliance", json=sample_batch_request)
            assert response.status_code == 200
            
            data = response.json()
            assert len(data["results"]) == 5
            assert all("FAIR" in r for r in data["results"])
            assert all("COMP" in r for r in data["results"])
    
    def test_compliance_check_returns_request_id(self, client, sample_compliance_request):
        """Test that response includes X-Request-ID header."""
        response = client.post("/check_compliance", json=sample_compliance_request)
        assert "X-Request-ID" in response.headers
        # UUID format check
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36  # UUID4 format
        assert request_id.count("-") == 4


class TestRequestValidation:
    """Tests for Pydantic request validation."""
    
    def test_invalid_json(self, client):
        """Test that invalid JSON returns 422 error."""
        response = client.post(
            "/check_compliance",
            data="not json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_missing_required_fields(self, client):
        """Test that missing required fields returns 422 error."""
        request = {
            "AIViolationID": [{"ID": "FAIR"}]  # Missing CheckColumns
            # Missing Data
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 422
    
    def test_wrong_data_types(self, client):
        """Test that wrong data types return 422 error."""
        request = {
            "AIViolationID": "not a list",  # Should be list
            "Data": [{"mlsnum": "ML123", "mls_id": "TEST"}]
        }
        response = client.post("/check_compliance", json=request)
        assert response.status_code == 422
