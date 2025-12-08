"""Unit tests for rate limiter functionality."""

import pytest
import asyncio
from unittest.mock import MagicMock
from app.core.rate_limiter import DynamicRateLimiter, get_rate_limiter, reset_rate_limiter


class TestRateLimiterInitialization:
    """Tests for rate limiter initialization."""
    
    def test_rate_limiter_singleton(self):
        """Test that get_rate_limiter returns same instance."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2
    
    def test_rate_limiter_reset(self):
        """Test that reset_rate_limiter creates new instance."""
        limiter1 = get_rate_limiter()
        reset_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is not limiter2
    
    def test_initial_state(self):
        """Test initial rate limiter state."""
        limiter = DynamicRateLimiter()
        assert limiter.token_limit is None
        assert limiter.remaining_tokens is None
        assert limiter.current_concurrency == 50  # DEFAULT_CONCURRENCY
        assert limiter.total_tokens_used == 0
        assert limiter.total_requests_made == 0
        assert limiter.paused is False


class TestTokenEstimation:
    """Tests for token estimation."""
    
    def test_estimate_tokens_short_text(self):
        """Test token estimation for short text."""
        limiter = DynamicRateLimiter()
        text = "Short text"
        estimated = limiter.estimate_tokens(text)
        # Should be: len(text)//4 + MAX_OUTPUT_TOKENS
        # len("Short text") = 10, 10//4 = 2, 2 + 6590 = 6592
        assert estimated == 6592
    
    def test_estimate_tokens_long_text(self):
        """Test token estimation for long text."""
        limiter = DynamicRateLimiter()
        text = "A" * 8000  # 8000 characters
        estimated = limiter.estimate_tokens(text)
        # 8000//4 + 6590 = 2000 + 6590 = 8590
        assert estimated == 8590
    
    def test_estimate_tokens_empty_text(self):
        """Test token estimation for empty text."""
        limiter = DynamicRateLimiter()
        estimated = limiter.estimate_tokens("")
        assert estimated == 6590  # Just output tokens


class TestResetTimeParsing:
    """Tests for reset time string parsing."""
    
    def test_parse_seconds_only(self):
        """Test parsing seconds only format."""
        limiter = DynamicRateLimiter()
        assert limiter.parse_reset_time("1s") == 1.0
        assert limiter.parse_reset_time("30s") == 30.0
    
    def test_parse_minutes_and_seconds(self):
        """Test parsing minutes and seconds format."""
        limiter = DynamicRateLimiter()
        assert limiter.parse_reset_time("1m0s") == 60.0
        assert limiter.parse_reset_time("6m0s") == 360.0
        assert limiter.parse_reset_time("2m30s") == 150.0
    
    def test_parse_hours_minutes_seconds(self):
        """Test parsing full time format."""
        limiter = DynamicRateLimiter()
        assert limiter.parse_reset_time("1h0m0s") == 3600.0
        assert limiter.parse_reset_time("2h30m15s") == 9015.0
    
    def test_parse_invalid_format(self):
        """Test parsing invalid format returns default."""
        limiter = DynamicRateLimiter()
        # Should return 60.0 (default) on error
        assert limiter.parse_reset_time("invalid") == 60.0
        assert limiter.parse_reset_time("") == 60.0


class TestHeaderUpdates:
    """Tests for updating from response headers."""
    
    @pytest.mark.asyncio
    async def test_update_from_headers(self, mock_openai_response):
        """Test updating rate limiter from response headers."""
        limiter = DynamicRateLimiter()
        await limiter.update_from_headers(mock_openai_response)
        
        assert limiter.token_limit == 10000000
        assert limiter.remaining_tokens == 9999850
        assert limiter.request_limit == 10000
        assert limiter.remaining_requests == 9999
        assert limiter.total_tokens_used == 150
        assert limiter.total_requests_made == 1
    
    @pytest.mark.asyncio
    async def test_update_cumulative_stats(self, mock_openai_response):
        """Test that stats accumulate across multiple updates."""
        limiter = DynamicRateLimiter()
        
        # First update
        await limiter.update_from_headers(mock_openai_response)
        assert limiter.total_tokens_used == 150
        assert limiter.total_requests_made == 1
        
        # Second update
        await limiter.update_from_headers(mock_openai_response)
        assert limiter.total_tokens_used == 300
        assert limiter.total_requests_made == 2
    
    @pytest.mark.asyncio
    async def test_update_with_missing_headers(self):
        """Test handling response with missing headers."""
        limiter = DynamicRateLimiter()
        response = MagicMock()
        response.http_response = MagicMock()
        response.http_response.headers = {}  # Empty headers
        
        # Should not crash
        await limiter.update_from_headers(response)
        assert limiter.token_limit is None


class TestConcurrencyCalculation:
    """Tests for dynamic concurrency calculation."""
    
    def test_concurrency_high_budget(self):
        """Test concurrency when budget is high (>50%)."""
        limiter = DynamicRateLimiter()
        limiter.token_limit = 10000000
        limiter.remaining_tokens = 7000000  # 70% remaining
        
        concurrency = limiter.get_safe_concurrency()
        assert concurrency == 200  # MAX_CONCURRENCY
    
    def test_concurrency_medium_budget(self):
        """Test concurrency when budget is medium (20-50%)."""
        limiter = DynamicRateLimiter()
        limiter.token_limit = 10000000
        limiter.remaining_tokens = 3000000  # 30% remaining
        
        concurrency = limiter.get_safe_concurrency()
        # Should scale linearly: 10 + ratio * (200-10)
        # ratio = (0.3 - 0.2) / (0.5 - 0.2) = 0.33
        # concurrency = 10 + 0.33 * 190 = 73
        assert 60 < concurrency < 90
    
    def test_concurrency_low_budget(self):
        """Test concurrency when budget is low (10-20%)."""
        limiter = DynamicRateLimiter()
        limiter.token_limit = 10000000
        limiter.remaining_tokens = 1500000  # 15% remaining
        
        concurrency = limiter.get_safe_concurrency()
        assert concurrency == 10  # MIN_CONCURRENCY
    
    def test_concurrency_critical_budget(self):
        """Test concurrency when budget is critical (<10%)."""
        limiter = DynamicRateLimiter()
        limiter.token_limit = 10000000
        limiter.remaining_tokens = 500000  # 5% remaining
        
        concurrency = limiter.get_safe_concurrency()
        assert concurrency == 5  # MIN_CONCURRENCY // 2
    
    def test_concurrency_no_data(self):
        """Test concurrency returns default when no data."""
        limiter = DynamicRateLimiter()
        # No rate limit data yet
        concurrency = limiter.get_safe_concurrency()
        assert concurrency == 50  # DEFAULT_CONCURRENCY
    
    def test_concurrency_respects_request_limit(self):
        """Test that concurrency considers request limit too."""
        limiter = DynamicRateLimiter()
        limiter.token_limit = 10000000
        limiter.remaining_tokens = 9000000  # 90% tokens remaining
        limiter.request_limit = 10000
        limiter.remaining_requests = 500  # Only 5% requests remaining
        
        concurrency = limiter.get_safe_concurrency()
        # Should be throttled due to low request budget
        assert concurrency == 5


class TestWaitIfNeeded:
    """Tests for wait_if_needed method."""
    
    @pytest.mark.asyncio
    async def test_no_wait_when_sufficient_budget(self):
        """Test that no wait occurs when budget is sufficient."""
        limiter = DynamicRateLimiter()
        limiter.token_limit = 10000000
        limiter.remaining_tokens = 5000000  # Plenty of tokens
        
        # Should return immediately
        await limiter.wait_if_needed(7000)
        assert limiter.paused is False
    
    @pytest.mark.asyncio
    async def test_no_wait_on_first_request(self):
        """Test that no wait occurs when no rate limit data yet."""
        limiter = DynamicRateLimiter()
        # No rate limit data
        
        # Should return immediately
        await limiter.wait_if_needed(7000)
        assert limiter.paused is False


class TestGetStats:
    """Tests for get_stats method."""
    
    def test_get_stats_initial_state(self):
        """Test stats in initial state."""
        limiter = DynamicRateLimiter()
        stats = limiter.get_stats()
        
        assert stats["total_tokens_used"] == 0
        assert stats["total_requests_made"] == 0
        assert stats["remaining_tokens"] is None
        assert stats["current_concurrency"] == 50
        assert stats["paused"] is False
    
    @pytest.mark.asyncio
    async def test_get_stats_after_updates(self, mock_openai_response):
        """Test stats after processing requests."""
        limiter = DynamicRateLimiter()
        await limiter.update_from_headers(mock_openai_response)
        
        stats = limiter.get_stats()
        assert stats["total_tokens_used"] == 150
        assert stats["total_requests_made"] == 1
        assert stats["token_limit"] == 10000000
        assert stats["remaining_tokens"] == 9999850
