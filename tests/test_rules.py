# """Unit tests for rule functions."""

# import pytest
# from unittest.mock import AsyncMock, MagicMock, patch
# from app.rules.base import (
#     get_fair_housing_violation_response,
#     get_comp_violation_response,
#     get_marketing_rule_violation_response
# )


# class TestFairHousingRule:
#     """Tests for Fair Housing rule function."""
    
#     @pytest.mark.asyncio
#     async def test_fair_housing_success(self, mock_openai_client, mock_openai_response):
#         """Test Fair Housing rule with successful response."""
#         mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
#         with patch('app.rules.base.client', mock_openai_client):
#             result = await get_fair_housing_violation_response(
#                 "Beautiful home with great school district",
#                 "Must see property"
#             )
            
#             assert "Remarks" in result
#             assert "PrivateRemarks" in result
#             assert "Total_tokens" in result
#             mock_openai_client.responses.create.assert_called_once()
    
#     @pytest.mark.asyncio
#     async def test_fair_housing_with_violation(self, mock_openai_client):
#         """Test Fair Housing rule detecting violations."""
#         # Mock response indicating violation
#         violation_response = MagicMock()
#         violation_response.output_text = """```json
# {
#     "result": {
#         "public_remarks": ["Violation found"],
#         "private_agent_remarks": []
#     }
# }
# ```"""
#         violation_response.usage = MagicMock()
#         violation_response.usage.total_tokens = 150
#         violation_response.http_response = MagicMock()
#         violation_response.http_response.headers = {
#             "x-ratelimit-limit-tokens": "10000000",
#             "x-ratelimit-remaining-tokens": "9999850",
#             "x-ratelimit-reset-tokens": "6m0s"
#         }
        
#         mock_openai_client.responses.create = AsyncMock(return_value=violation_response)
        
#         with patch('app.rules.base.client', mock_openai_client):
#             result = await get_fair_housing_violation_response(
#                 "Perfect for families with children",
#                 "Great for kids"
#             )
            
#             assert "Remarks" in result
#             assert len(result["Remarks"]) > 0
    
#     @pytest.mark.asyncio
#     async def test_fair_housing_formats_prompt_correctly(self, mock_openai_client, mock_openai_response):
#         """Test that Fair Housing rule formats the prompt correctly."""
#         mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
#         with patch('app.rules.base.client', mock_openai_client):
#             await get_fair_housing_violation_response(
#                 "Beautiful home",
#                 "Must see"
#             )
            
#             call_args = mock_openai_client.responses.create.call_args
#             prompt = call_args.kwargs['prompt']
            
#             assert "public_remarks" in prompt['variables']
#             assert "private_agent_remarks" in prompt['variables']
    
#     @pytest.mark.asyncio
#     async def test_fair_housing_retries_on_failure(self, mock_openai_client, mock_openai_response):
#         """Test that Fair Housing rule retries on API error."""
#         from openai import APIError
#         from unittest.mock import MagicMock
        
#         # Create a proper APIError with status_code for server error (will retry)
#         api_error = APIError("Server error", request=MagicMock(), body=None)
#         api_error.status_code = 500  # Set status code for retryable error
        
#         # First call fails, second succeeds
#         mock_openai_client.responses.create = AsyncMock(
#             side_effect=[
#                 api_error,
#                 mock_openai_response
#             ]
#         )
        
#         with patch('app.rules.base.client', mock_openai_client):
#             with patch('asyncio.sleep', new=AsyncMock()):  # Skip sleep delays
#                 result = await get_fair_housing_violation_response(
#                     "Test data",
#                     "Test remarks"
#                 )
                
#                 assert result is not None
#                 assert mock_openai_client.responses.create.call_count == 2


# class TestCompRule:
#     """Tests for Compensation rule function."""
    
#     @pytest.mark.asyncio
#     async def test_comp_rule_success(self, mock_openai_client, mock_openai_response):
#         """Test COMP rule with successful response."""
#         mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
#         with patch('app.rules.base.client', mock_openai_client):
#             result = await get_comp_violation_response(
#                 "Standard commission structure",
#                 "Buyer agent welcome"
#             )
            
#             assert "Remarks" in result
#             assert "PrivateRemarks" in result
#             mock_openai_client.responses.create.assert_called_once()
    
#     @pytest.mark.asyncio
#     async def test_comp_rule_with_violation(self, mock_openai_client):
#         """Test COMP rule detecting violations."""
#         violation_response = MagicMock()
#         violation_response.output_text = """```json
# {
#     "result": {
#         "public_remarks": ["Mentions specific commission"],
#         "private_agent_remarks": []
#     }
# }
# ```"""
#         violation_response.usage = MagicMock()
#         violation_response.usage.total_tokens = 100
#         violation_response.http_response = MagicMock()
#         violation_response.http_response.headers = {}
        
#         mock_openai_client.responses.create = AsyncMock(return_value=violation_response)
        
#         with patch('app.rules.base.client', mock_openai_client):
#             result = await get_comp_violation_response(
#                 "3% commission offered",
#                 "Generous compensation"
#             )
            
#             assert "Remarks" in result
#             assert len(result["Remarks"]) > 0
    
#     @pytest.mark.asyncio
#     async def test_comp_rule_formats_prompt_correctly(self, mock_openai_client, mock_openai_response):
#         """Test that COMP rule formats the prompt correctly."""
#         mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
#         with patch('app.rules.base.client', mock_openai_client):
#             await get_comp_violation_response(
#                 "Property details",
#                 "Agent notes"
#             )
            
#             call_args = mock_openai_client.responses.create.call_args
#             prompt = call_args.kwargs['prompt']
            
#             assert "public_remarks" in prompt['variables']
#             assert "private_agent_remarks" in prompt['variables']


# class TestMarketingRule:
#     """Tests for Marketing rule function."""
    
#     @pytest.mark.asyncio
#     async def test_marketing_rule_success(self, mock_openai_client, mock_openai_response):
#         """Test PROMO rule with successful response."""
#         mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
#         with patch('app.rules.base.client', mock_openai_client):
#             result = await get_marketing_rule_violation_response(
#                 "Professional listing with accurate details",
#                 "Well maintained property"
#             )
            
#             assert "Remarks" in result
#             assert "PrivateRemarks" in result
#             mock_openai_client.responses.create.assert_called_once()
    
#     @pytest.mark.asyncio
#     async def test_marketing_rule_with_violation(self, mock_openai_client):
#         """Test PROMO rule detecting violations."""
#         violation_response = MagicMock()
#         violation_response.output_text = """```json
# {
#     "result": {
#         "public_remarks": ["Contains unverified superlatives"],
#         "private_agent_remarks": []
#     }
# }
# ```"""
#         violation_response.usage = MagicMock()
#         violation_response.usage.total_tokens = 120
#         violation_response.http_response = MagicMock()
#         violation_response.http_response.headers = {}
        
#         mock_openai_client.responses.create = AsyncMock(return_value=violation_response)
        
#         with patch('app.rules.base.client', mock_openai_client):
#             result = await get_marketing_rule_violation_response(
#                 "BEST HOUSE EVER! GUARANTEED INVESTMENT!",
#                 "You won't find better!"
#             )
            
#             assert "Remarks" in result
#             assert len(result["Remarks"]) > 0
    
#     @pytest.mark.asyncio
#     async def test_marketing_rule_formats_prompt_correctly(self, mock_openai_client, mock_openai_response):
#         """Test that PROMO rule formats the prompt correctly."""
#         mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
#         with patch('app.rules.base.client', mock_openai_client):
#             await get_marketing_rule_violation_response(
#                 "Listing description",
#                 "Marketing notes"
#             )
            
#             call_args = mock_openai_client.responses.create.call_args
#             prompt = call_args.kwargs['prompt']
            
#             assert "public_remarks" in prompt['variables']
#             assert "private_agent_remarks" in prompt['variables']


# class TestRuleIntegration:
#     """Integration tests for rule functions."""
    
#     @pytest.mark.asyncio
#     async def test_all_rules_use_rate_limiter(self, mock_openai_client, mock_openai_response):
#         """Test that all rules integrate with rate limiter."""
#         mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
#         with patch('app.rules.base.client', mock_openai_client):
#             # All rules should update rate limiter from response headers
#             await get_fair_housing_violation_response("test", "test")
#             await get_comp_violation_response("test", "test")
#             await get_marketing_rule_violation_response("test", "test")
            
#             # Should have made 3 API calls
#             assert mock_openai_client.responses.create.call_count == 3
    
#     @pytest.mark.asyncio
#     async def test_all_rules_use_retry_handler(self, mock_openai_client, mock_openai_response):
#         """Test that all rules use retry handler decorator."""
#         from openai import APITimeoutError
        
#         # Mock timeout then success for each rule
#         mock_openai_client.responses.create = AsyncMock(
#             side_effect=[
#                 # FAIR rule: timeout then success
#                 APITimeoutError(request=MagicMock()),
#                 mock_openai_response,
#                 # COMP rule: timeout then success
#                 APITimeoutError(request=MagicMock()),
#                 mock_openai_response,
#                 # PROMO rule: timeout then success
#                 APITimeoutError(request=MagicMock()),
#                 mock_openai_response,
#             ]
#         )
        
#         with patch('app.rules.base.client', mock_openai_client):
#             with patch('asyncio.sleep', new=AsyncMock()):
#                 # All should succeed after retry
#                 result1 = await get_fair_housing_violation_response("test", "test")
#                 result2 = await get_comp_violation_response("test", "test")
#                 result3 = await get_marketing_rule_violation_response("test", "test")
                
#                 assert result1 is not None
#                 assert result2 is not None
#                 assert result3 is not None
#                 assert mock_openai_client.responses.create.call_count == 6
