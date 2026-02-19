"""
Test suite for admin cache management endpoints.

Endpoints under test:
  GET  /admin/cache/stats    — View cache statistics
  POST /admin/cache/clear    — Clear prompt cache
  POST /admin/cache/refresh  — Refresh specific or all cached prompts

All admin endpoints require authentication (API Key or JWT).
"""

import time
import pytest
from unittest.mock import Mock, patch

from app.core.prompt_cache import get_prompt_cache_manager, _USE_DEFAULT


# ============================================================================
# Helpers
# ============================================================================

def _make_prompt_obj(text="Test prompt", config=None, version="1.0"):
    """Build a minimal mock Langfuse prompt object."""
    obj = Mock()
    obj.prompt = text
    obj.config = config or {"model": "gpt-4o"}
    obj.version = version
    return obj


def _seed(cache, rule_id, mls_id, data):
    """Seed a prompt into the cache with a fresh timestamp."""
    rule_key = rule_id.upper()
    cache._cache.setdefault(rule_key, {})[mls_id] = data
    cache._cache_timestamps.setdefault(rule_key, {})[mls_id] = time.time()


# ============================================================================
# Tests: GET /admin/cache/stats
# ============================================================================

class TestAdminCacheStats:

    def test_returns_stats(self, client):
        """Stats endpoint returns current cache info including TTL."""
        response = client.get("/admin/cache/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_prompts_cached" in data
        assert "total_sentinel_entries" in data
        assert "ttl_seconds" in data
        assert "cache" in data

    def test_reflects_seeded_data(self, client):
        """Stats endpoint counts seeded cache entries correctly."""
        cache = get_prompt_cache_manager()
        _seed(cache, "FAIR", "default", {"prompt": "x"})
        _seed(cache, "COMP", "default", {"prompt": "y"})

        response = client.get("/admin/cache/stats")
        data = response.json()
        assert data["total_prompts_cached"] == 2

    def test_requires_authentication(self, client_no_auth):
        """Stats endpoint rejects unauthenticated requests."""
        response = client_no_auth.get("/admin/cache/stats")
        assert response.status_code == 401


# ============================================================================
# Tests: POST /admin/cache/clear
# ============================================================================

class TestAdminCacheClear:

    def test_clears_cache(self, client):
        """Clear endpoint empties the entire cache."""
        cache = get_prompt_cache_manager()
        _seed(cache, "FAIR", "default", {"prompt": "x"})
        assert cache._cache != {}

        response = client.post("/admin/cache/clear")
        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Cache cleared successfully"
        assert body["stats"]["total_prompts_cached"] == 0
        assert cache._cache == {}

    def test_clears_timestamps_too(self, client):
        """Clear endpoint also wipes timestamp tracking."""
        cache = get_prompt_cache_manager()
        _seed(cache, "FAIR", "default", {"prompt": "x"})
        assert cache._cache_timestamps != {}

        client.post("/admin/cache/clear")
        assert cache._cache_timestamps == {}

    def test_clear_on_empty_cache_is_safe(self, client):
        """Clearing an already-empty cache is a harmless no-op."""
        response = client.post("/admin/cache/clear")
        assert response.status_code == 200

    def test_requires_authentication(self, client_no_auth):
        """Clear endpoint rejects unauthenticated requests."""
        response = client_no_auth.post("/admin/cache/clear")
        assert response.status_code == 401


# ============================================================================
# Tests: POST /admin/cache/refresh
# ============================================================================

class TestAdminCacheRefresh:

    def test_refresh_all_no_body(self, client):
        """POST with no body refreshes all cached prompts."""
        cache = get_prompt_cache_manager()
        _seed(cache, "FAIR", "default", {"prompt": "old"})

        with patch("app.core.prompt_cache.LANGFUSE_CLIENT") as mock_lf:
            mock_lf.get_prompt = Mock(return_value=_make_prompt_obj("new"))
            response = client.post("/admin/cache/refresh")

        assert response.status_code == 200
        assert "Refreshed all" in response.json()["message"]

    def test_refresh_all_empty_body(self, client):
        """POST with empty JSON body refreshes all cached prompts."""
        cache = get_prompt_cache_manager()
        _seed(cache, "FAIR", "default", {"prompt": "old"})

        with patch("app.core.prompt_cache.LANGFUSE_CLIENT") as mock_lf:
            mock_lf.get_prompt = Mock(return_value=_make_prompt_obj("new"))
            response = client.post("/admin/cache/refresh", json={})

        assert response.status_code == 200
        assert "Refreshed all" in response.json()["message"]

    def test_refresh_specific_rule(self, client):
        """POST with rule_id refreshes all entries for that rule."""
        cache = get_prompt_cache_manager()
        _seed(cache, "FAIR", "default", {"prompt": "old"})

        with patch("app.core.prompt_cache.LANGFUSE_CLIENT") as mock_lf:
            mock_lf.get_prompt = Mock(return_value=_make_prompt_obj("new"))
            response = client.post(
                "/admin/cache/refresh",
                json={"rule_id": "FAIR"},
            )

        assert response.status_code == 200
        body = response.json()
        assert "FAIR" in body["message"]
        assert "stats" in body

    def test_refresh_specific_prompt(self, client):
        """POST with rule_id + mls_id refreshes one prompt."""
        cache = get_prompt_cache_manager()
        _seed(cache, "FAIR", "Miami", {"prompt": "old"})

        with patch("app.core.prompt_cache.LANGFUSE_CLIENT") as mock_lf:
            mock_lf.get_prompt = Mock(return_value=_make_prompt_obj("new"))
            response = client.post(
                "/admin/cache/refresh",
                json={"rule_id": "FAIR", "mls_id": "Miami"},
            )

        assert response.status_code == 200
        body = response.json()
        assert "FAIR" in body["message"]
        assert "Miami" in body["message"]
        assert "found" in body

    def test_refresh_returns_stats(self, client):
        """Refresh response always includes updated cache stats."""
        with patch("app.core.prompt_cache.LANGFUSE_CLIENT") as mock_lf:
            mock_lf.get_prompt = Mock(return_value=_make_prompt_obj())
            response = client.post("/admin/cache/refresh")

        body = response.json()
        assert "stats" in body
        assert "total_prompts_cached" in body["stats"]

    def test_requires_authentication(self, client_no_auth):
        """Refresh endpoint rejects unauthenticated requests."""
        response = client_no_auth.post("/admin/cache/refresh")
        assert response.status_code == 401
