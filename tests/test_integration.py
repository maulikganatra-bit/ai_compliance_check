"""Integration tests for end-to-end API workflows."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestEndToEndWorkflow:
    """Integration tests for complete API workflows."""
    
    @pytest.mark.asyncio
    async def test_single_listing_single_rule_workflow(self, client, mock_openai_client, mock_openai_response):
        """Test complete workflow for single listing with one rule."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Beautiful home",
                    "PrivateRemarks": "Must see"
                }
            ]
        }
        
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        with patch('app.rules.base.client', mock_openai_client):
            response = client.post("/check_compliance", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response structure
            assert data["ok"] == 200
            assert "results" in data
            assert len(data["results"]) == 1
            
            # Verify result content
            result = data["results"][0]
            assert "FAIR" in result
    
    @pytest.mark.asyncio
    async def test_multiple_listings_multiple_rules_workflow(self, client, mock_openai_client, mock_openai_response):
        """Test complete workflow for multiple listings with multiple rules."""
        request_data = {
            "AIViolationID": [
                {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "COMP", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "PROMO", "CheckColumns": "Remarks"}
            ],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Beautiful home",
                    "PrivateRemarks": "Must see"
                },
                {
                    "mlsnum": "67890",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Spacious property",
                    "PrivateRemarks": "Great location"
                }
            ]
        }
        
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        with patch('app.rules.base.client', mock_openai_client):
            response = client.post("/check_compliance", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response structure
            assert data["ok"] == 200
            assert len(data["results"]) == 2
            
            # Verify each result has all rules
            for result in data["results"]:
                assert "FAIR" in result
                assert "COMP" in result
                assert "PROMO" in result
            
            # Verify OpenAI was called 6 times (2 listings × 3 rules)
            assert mock_openai_client.responses.create.call_count == 6
    
    @pytest.mark.asyncio
    async def test_request_id_propagation(self, client, mock_openai_client, mock_openai_response):
        """Test that request ID propagates through entire workflow."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Test",
                    "PrivateRemarks": "Test"
                }
            ]
        }
        
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        with patch('app.rules.base.client', mock_openai_client):
            response = client.post("/check_compliance", json=request_data)
            
            assert response.status_code == 200
            
            # Verify request ID is in response headers
            assert "X-Request-ID" in response.headers
            request_id = response.headers["X-Request-ID"]
            assert len(request_id) == 36  # UUID length with hyphens
    
    @pytest.mark.asyncio
    async def test_rate_limiter_integration(self, client, mock_openai_client, mock_openai_response):
        """Test that rate limiter is updated during workflow."""
        from app.core.rate_limiter import get_rate_limiter
        
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Test",
                    "PrivateRemarks": "Test"
                }
            ]
        }
        
        limiter = get_rate_limiter()
        initial_requests = limiter.total_requests_made
        
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        with patch('app.rules.base.client', mock_openai_client):
            response = client.post("/check_compliance", json=request_data)
            
            assert response.status_code == 200
            
            # Verify rate limiter was updated
            assert limiter.total_requests_made > initial_requests


class TestErrorHandling:
    """Integration tests for error handling workflows."""
    
    @pytest.mark.asyncio
    async def test_openai_api_error_handling(self, client, mock_openai_client):
        """Test handling of OpenAI API errors."""
        from openai import APIError
        
        # Mock API error
        mock_openai_client.responses.create = AsyncMock(
            side_effect=APIError("Server error", request=MagicMock(), body=None)
        )
        
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Test",
                    "PrivateRemarks": "Test"
                }
            ]
        }
        
        with patch('app.rules.base.client', mock_openai_client):
            with patch('asyncio.sleep', new=AsyncMock()):  # Skip retry delays
                response = client.post("/check_compliance", json=request_data)
                
                # Should return 200 with error in results
                assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_invalid_rule_id_error(self, client):
        """Test error handling for invalid rule ID."""
        request_data = {
            "AIViolationID": [{"ID": "INVALID_RULE", "CheckColumns": "Remarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Test",
                    "PrivateRemarks": "Test"
                }
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        
        # API returns 400 for invalid rule IDs
        assert response.status_code == 400
        data = response.json()
        assert "Invalid rule" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_missing_required_columns_error(self, client):
        """Test error handling for missing required columns."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS"
                    # Missing Remarks and PrivateRemarks columns
                }
            ]
        }
        
        response = client.post("/check_compliance", json=request_data)
        
        # Returns 200 with error in results
        assert response.status_code == 200


class TestParallelExecution:
    """Integration tests for parallel execution behavior."""
    
    @pytest.mark.asyncio
    async def test_parallel_rule_execution(self, client, mock_openai_client, mock_openai_response):
        """Test that rules execute in parallel for each listing."""
        call_times = []
        
        async def track_calls(*args, **kwargs):
            import time
            call_times.append(time.time())
            return mock_openai_response
        
        mock_openai_client.responses.create = AsyncMock(side_effect=track_calls)
        
        request_data = {
            "AIViolationID": [
                {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "COMP", "CheckColumns": "Remarks,PrivateRemarks"},
                {"ID": "PROMO", "CheckColumns": "Remarks"}
            ],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "TEST_MLS",
                    "Remarks": "Test",
                    "PrivateRemarks": "Test"
                }
            ]
        }
        
        with patch('app.rules.base.client', mock_openai_client):
            response = client.post("/check_compliance", json=request_data)
            
            assert response.status_code == 200
            
            # Verify 3 calls were made
            assert len(call_times) == 3
            
            # Verify calls happened nearly simultaneously (parallel)
            time_span = max(call_times) - min(call_times)
            assert time_span < 0.1  # Should be very close if parallel


class TestCustomRules:
    """Integration tests for custom rule loading."""
    
    @pytest.mark.asyncio
    async def test_custom_rule_file_loading(self, client, mock_openai_client, mock_openai_response):
        """Test that custom rule system works (falls back to default when no custom exists)."""
        request_data = {
            "AIViolationID": [{"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}],
            "Data": [
                {
                    "mlsnum": "12345",
                    "mls_id": "CUSTOM_MLS",
                    "Remarks": "Test",
                    "PrivateRemarks": "Test"
                }
            ]
        }
        
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        with patch('app.rules.base.client', mock_openai_client):
            response = client.post("/check_compliance", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify default rule was used (since no custom rule exists)
            result = data["results"][0]
            assert "FAIR" in result
