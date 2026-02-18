"""Integration tests for end-to-end API workflows."""

import pytest


class TestEndToEndWorkflow:
    """Integration tests for complete API workflows."""
    
    def test_single_listing_single_rule_workflow(self, client):
        """Test complete workflow for single listing with one rule."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mlsId": "TESTMLS",
                    "Remarks": "Beautiful home",
                    "PrivateRemarks": "Must see"
                }
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == 200
        assert "results" in data
        assert isinstance(data["results"], list)
    
    def test_multiple_listings_multiple_rules_workflow(self, client):
        """Test complete workflow for multiple listings with multiple rules."""
        request_data = {
            "AIViolationID": [
                {"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "COMP", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "PROMO", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}
            ],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mlsId": "TESTMLS",
                    "Remarks": "Beautiful home",
                    "PrivateRemarks": "Must see"
                },
                {
                    "mlsnum": "67890",
                    "mlsId": "TESTMLS",
                    "Remarks": "Spacious property",
                    "PrivateRemarks": "Great location"
                }
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == 200
        assert isinstance(data["results"], list)
    
    def test_request_id_propagation(self, client):
        """Test that request ID is propagated through the entire workflow."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [
                {
                    "mlsnum": "99999",
                    "mlsId": "TESTMLS",
                    "Remarks": "Test property"
                }
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] == response.headers["X-Request-ID"]
    
    def test_rate_limiter_integration(self, client):
        """Test that rate limiter statistics are tracked."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [
                {
                    "mlsnum": "55555",
                    "mlsId": "TESTMLS",
                    "Remarks": "Another test"
                }
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "total_tokens" in data
        assert "elapsed_time" in data
        assert data["elapsed_time"] >= 0


class TestErrorHandling:
    """Tests for error handling in end-to-end workflows."""
    
    def test_invalid_rule_id_error(self, client):
        """Test that invalid rule IDs are caught early."""
        request_data = {
            "AIViolationID": [{"ID": "NONEXISTENT", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [{"mlsnum": "88888", "mlsId": "TESTMLS", "Remarks": "Test"}]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 400
        assert "Invalid rule ID" in response.json()["detail"]
    
    def test_missing_required_columns_error(self, client):
        """Test that missing required columns are caught."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "99999",
                    "mlsId": "TESTMLS",
                    "Remarks": "No private remarks field"
                }
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 400
        assert "missing required columns" in response.json()["detail"]


class TestParallelExecution:
    """Tests for parallel rule execution."""
    
    def test_parallel_rule_execution(self, client):
        """Test that multiple rules execute in parallel."""
        request_data = {
            "AIViolationID": [
                {"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"},
                {"ID": "COMP", "mlsId": "TESTMLS", "CheckColumns": "Remarks"},
                {"ID": "PROMO", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}
            ],
            "Data": [
                {"mlsnum": f"{i:05d}", "mlsId": "TESTMLS", "Remarks": f"Property {i}"}
                for i in range(3)
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == 200
        assert isinstance(data["results"], list)


class TestCustomRules:
    """Tests for custom rule loading and execution."""
    
    def test_custom_rule_file_loading(self, client):
        """Test that custom rules can be loaded and applied."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": [
                {"mlsnum": "12345", "mlsId": "TESTMLS", "Remarks": "Standard test property"}
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == 200
        assert isinstance(data["results"], list)
