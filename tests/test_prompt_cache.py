"""
Test suite for PromptCacheManager (auto-discovery naming convention)

Naming convention under test:
  - Default prompt : {RULE_ID}_violation          e.g. FAIR_violation
  - Custom prompt  : {RULE_ID}_{MLS_ID}_violation  e.g. FAIR_Miami_violation

Key behaviours:
  - rule_id  : always uppercased internally
  - mls_id   : case-sensitive, stored exactly as received
  - _USE_DEFAULT sentinel: stored when custom lookup fails, resolves to default transparently
  - No env-var configuration needed

Run all tests:
    pytest tests/test_prompt_cache.py -v

Run with coverage:
    pytest tests/test_prompt_cache.py --cov=app.core.prompt_cache --cov-report=html

Run a specific category:
    pytest tests/test_prompt_cache.py -k "sentinel" -v
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock

from app.core.prompt_cache import (
    PromptCacheManager,
    get_prompt_cache_manager,
    _custom_prompt_name,
    _default_prompt_name,
    _USE_DEFAULT,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_prompt_obj(text="Test prompt {public_remarks}", config=None, version="1.0"):
    """Build a minimal mock Langfuse prompt object."""
    obj = Mock()
    obj.prompt = text
    obj.config = config or {"model": "gpt-4o", "temperature": 0.1, "max_output_tokens": 1000}
    obj.version = version
    return obj


def _seed_cache(cache: PromptCacheManager, rule_id: str, mls_id: str, data: dict):
    """Directly write into the internal nested cache (with timestamp), bypassing Langfuse."""
    rule_key = rule_id.upper()
    cache._cache.setdefault(rule_key, {})[mls_id] = data
    cache._cache_timestamps.setdefault(rule_key, {})[mls_id] = time.time()


def _seed_sentinel(cache: PromptCacheManager, rule_id: str, mls_id: str):
    """Directly write the USE_DEFAULT sentinel (with timestamp) for (rule_id, mls_id)."""
    rule_key = rule_id.upper()
    cache._cache.setdefault(rule_key, {})[mls_id] = _USE_DEFAULT
    cache._cache_timestamps.setdefault(rule_key, {})[mls_id] = time.time()


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def clean_cache():
    """Reset the singleton cache before and after every test."""
    cache = get_prompt_cache_manager()
    cache.clear_cache()
    yield cache
    cache.clear_cache()


@pytest.fixture
def mock_langfuse(clean_cache):
    """
    Patch LANGFUSE_CLIENT with a mock whose get_prompt returns a valid
    prompt object by default.  Override per-test via mock_langfuse.get_prompt.
    """
    client = Mock()
    client.get_prompt = Mock(return_value=_make_prompt_obj())
    with patch("app.core.prompt_cache.LANGFUSE_CLIENT", client):
        yield client


@pytest.fixture
def langfuse_404(mock_langfuse):
    """Langfuse always raises 404 (no prompt found)."""
    mock_langfuse.get_prompt = Mock(side_effect=Exception("status_code: 404"))
    return mock_langfuse


# ============================================================================
# Test: Module-level naming helpers
# ============================================================================

class TestNamingHelpers:

    def test_default_prompt_name_uppercase(self):
        assert _default_prompt_name("FAIR") == "FAIR_violation"

    def test_default_prompt_name_lowercases_normalised(self):
        """rule_id input is always uppercased in the output."""
        assert _default_prompt_name("fair") == "FAIR_violation"
        assert _default_prompt_name("Fair") == "FAIR_violation"

    def test_custom_prompt_name_rule_uppercased(self):
        assert _custom_prompt_name("fair", "Miami") == "FAIR_Miami_violation"

    def test_custom_prompt_name_mls_preserved_exactly(self):
        """MLS ID must NOT be uppercased — case-sensitive."""
        assert _custom_prompt_name("FAIR", "Miami") == "FAIR_Miami_violation"
        assert _custom_prompt_name("FAIR", "MIAMI") == "FAIR_MIAMI_violation"
        assert _custom_prompt_name("FAIR", "miami") == "FAIR_miami_violation"

    def test_custom_and_default_names_are_different(self):
        assert _custom_prompt_name("FAIR", "Miami") != _default_prompt_name("FAIR")


# ============================================================================
# Test: Singleton pattern
# ============================================================================

class TestSingleton:

    def test_multiple_calls_return_same_instance(self):
        a = get_prompt_cache_manager()
        b = get_prompt_cache_manager()
        c = PromptCacheManager()
        assert a is b is c

    def test_clear_cache_affects_all_references(self, clean_cache):
        ref1 = get_prompt_cache_manager()
        ref2 = get_prompt_cache_manager()
        _seed_cache(ref1, "FAIR", "default", {"prompt": "x"})
        ref2.clear_cache()
        assert ref1._cache == {}


# ============================================================================
# Test: _get_from_cache — sentinel resolution
# ============================================================================

class TestGetFromCache:

    def test_returns_none_on_true_miss(self, clean_cache):
        assert clean_cache._get_from_cache("FAIR", "default") is None

    def test_returns_data_on_hit(self, clean_cache):
        data = {"prompt": "hello"}
        _seed_cache(clean_cache, "FAIR", "default", data)
        assert clean_cache._get_from_cache("FAIR", "default") is data

    def test_sentinel_resolves_to_default(self, clean_cache):
        default_data = {"prompt": "default text"}
        _seed_cache(clean_cache, "FAIR", "default", default_data)
        _seed_sentinel(clean_cache, "FAIR", "Miami1")

        result = clean_cache._get_from_cache("FAIR", "Miami1")
        assert result is default_data

    def test_sentinel_returns_none_when_default_also_missing(self, clean_cache):
        """Sentinel exists but default not yet loaded → None (not the sentinel string)."""
        _seed_sentinel(clean_cache, "FAIR", "Miami1")
        result = clean_cache._get_from_cache("FAIR", "Miami1")
        assert result is None

    def test_sentinel_string_never_leaks_to_caller(self, clean_cache):
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "d"})
        _seed_sentinel(clean_cache, "FAIR", "MLS1")
        result = clean_cache._get_from_cache("FAIR", "MLS1")
        assert result != _USE_DEFAULT
        assert isinstance(result, dict)

    def test_rule_id_normalised_to_upper(self, clean_cache):
        data = {"prompt": "x"}
        _seed_cache(clean_cache, "FAIR", "default", data)
        # Lookup with lowercase rule_id should still find it
        assert clean_cache._get_from_cache("fair", "default") is data

    def test_mls_id_is_case_sensitive(self, clean_cache):
        """Miami and MIAMI are distinct keys."""
        data_miami = {"prompt": "miami"}
        data_MIAMI = {"prompt": "MIAMI"}
        _seed_cache(clean_cache, "FAIR", "Miami", data_miami)
        _seed_cache(clean_cache, "FAIR", "MIAMI", data_MIAMI)

        assert clean_cache._get_from_cache("FAIR", "Miami") is data_miami
        assert clean_cache._get_from_cache("FAIR", "MIAMI") is data_MIAMI
        assert clean_cache._get_from_cache("FAIR", "miami") is None


# ============================================================================
# Test: _store_in_cache
# ============================================================================

class TestStoreInCache:

    def test_stores_under_correct_keys(self, clean_cache):
        data = {"prompt": "x"}
        clean_cache._store_in_cache("fair", "Miami", data)
        assert clean_cache._cache["FAIR"]["Miami"] is data

    def test_rule_id_uppercased_on_store(self, clean_cache):
        clean_cache._store_in_cache("fair", "Miami", {"p": 1})
        assert "FAIR" in clean_cache._cache
        assert "fair" not in clean_cache._cache

    def test_mls_id_preserved_on_store(self, clean_cache):
        clean_cache._store_in_cache("FAIR", "Miami", {"p": 1})
        clean_cache._store_in_cache("FAIR", "MIAMI", {"p": 2})
        assert "Miami" in clean_cache._cache["FAIR"]
        assert "MIAMI" in clean_cache._cache["FAIR"]

    def test_overwrites_existing_entry(self, clean_cache):
        clean_cache._store_in_cache("FAIR", "default", {"v": 1})
        clean_cache._store_in_cache("FAIR", "default", {"v": 2})
        assert clean_cache._cache["FAIR"]["default"]["v"] == 2


# ============================================================================
# Test: _load_prompt — custom → default fallback + sentinel
# ============================================================================

class TestLoadPrompt:

    @pytest.mark.asyncio
    async def test_loads_custom_when_found_in_langfuse(self, clean_cache, mock_langfuse):
        """When Langfuse returns a prompt for FAIR_Miami_violation, it is stored as custom."""
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("custom text"))

        result = await clean_cache._load_prompt("FAIR", "Miami")

        assert result is not None
        assert result["mls_id"] == "Miami"
        assert result["name"] == "FAIR_Miami_violation"
        # Stored under verbatim MLS key — NOT as sentinel
        assert isinstance(clean_cache._cache["FAIR"]["Miami"], dict)

    @pytest.mark.asyncio
    async def test_stores_sentinel_when_custom_not_found(self, clean_cache, mock_langfuse):
        """
        When custom prompt is missing (404), the sentinel _USE_DEFAULT is written
        for that MLS key so Langfuse is never queried again for this pair.
        """
        call_count = {"n": 0}

        def side_effect(name):
            call_count["n"] += 1
            if "Miami" in name:
                raise Exception("status_code: 404")
            return _make_prompt_obj("default text")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        await clean_cache._load_prompt("FAIR", "Miami")

        # Sentinel is stored under "Miami"
        assert clean_cache._cache["FAIR"]["Miami"] is _USE_DEFAULT

    @pytest.mark.asyncio
    async def test_fallback_loads_default_when_custom_missing(self, clean_cache, mock_langfuse):
        """After failing to find custom, the default prompt is loaded and returned."""
        def side_effect(name):
            if "Miami" in name:
                raise Exception("404")
            return _make_prompt_obj("default text")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        result = await clean_cache._load_prompt("FAIR", "Miami")

        assert result is not None
        assert result["name"] == "FAIR_violation"
        assert clean_cache._cache["FAIR"]["default"]["name"] == "FAIR_violation"

    @pytest.mark.asyncio
    async def test_reuses_cached_default_without_langfuse_call(self, clean_cache, mock_langfuse):
        """
        If default is already in cache, _load_prompt must NOT hit Langfuse
        for the default again when falling back.
        """
        default_data = {"name": "FAIR_violation", "prompt": "cached default", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default"}
        _seed_cache(clean_cache, "FAIR", "default", default_data)

        call_count = {"n": 0}

        def side_effect(name):
            call_count["n"] += 1
            if "Miami" in name:
                raise Exception("404")
            return _make_prompt_obj()  # should not be reached

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        result = await clean_cache._load_prompt("FAIR", "Miami")

        # Only 1 Langfuse call (for custom), not 2 (custom + default)
        assert call_count["n"] == 1
        assert result is default_data

    @pytest.mark.asyncio
    async def test_returns_none_when_both_custom_and_default_missing(self, clean_cache, langfuse_404):
        result = await clean_cache._load_prompt("FAIR", "Miami")
        assert result is None

    @pytest.mark.asyncio
    async def test_default_request_skips_custom_lookup(self, clean_cache, mock_langfuse):
        """Requesting mls_id='default' must never attempt a custom Langfuse lookup."""
        names_fetched = []
        mock_langfuse.get_prompt = Mock(side_effect=lambda n: (names_fetched.append(n), _make_prompt_obj())[1])

        await clean_cache._load_prompt("FAIR", "default")

        assert all("_default" not in n and "_violation" == n[-10:] or True for n in names_fetched)
        # More specifically: only FAIR_violation should have been tried, not FAIR_default_violation
        assert "FAIR_default_violation" not in names_fetched
        assert "FAIR_violation" in names_fetched

    @pytest.mark.asyncio
    async def test_mls_id_case_preserved_in_stored_data(self, clean_cache, mock_langfuse):
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj())

        await clean_cache._load_prompt("FAIR", "Miami")

        assert "Miami" in clean_cache._cache["FAIR"]
        assert "MIAMI" not in clean_cache._cache["FAIR"]
        assert "miami" not in clean_cache._cache["FAIR"]

    @pytest.mark.asyncio
    async def test_miami_and_MIAMI_are_independent_cache_entries(self, clean_cache, mock_langfuse):
        """Two requests with different MLS ID casing must result in two independent cache entries."""
        results = []

        def side_effect(name):
            results.append(name)
            if "_Miami_" in name:
                return _make_prompt_obj("custom Miami")
            raise Exception("404")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        res_miami = await clean_cache._load_prompt("FAIR", "Miami")
        res_MIAMI = await clean_cache._load_prompt("FAIR", "MIAMI")

        # Miami → custom prompt
        assert res_miami["name"] == "FAIR_Miami_violation"
        # MIAMI → sentinel + default
        assert clean_cache._cache["FAIR"]["MIAMI"] is _USE_DEFAULT


# ============================================================================
# Test: get_prompt (public, single pair)
# ============================================================================

class TestGetPrompt:

    @pytest.mark.asyncio
    async def test_cache_hit_returns_immediately(self, clean_cache, mock_langfuse):
        data = {"prompt": "cached", "name": "x", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default"}
        _seed_cache(clean_cache, "FAIR", "default", data)

        result = await clean_cache.get_prompt("FAIR", "default")

        assert result is data
        mock_langfuse.get_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_load(self, clean_cache, mock_langfuse):
        result = await clean_cache.get_prompt("FAIR", "default")

        assert result is not None
        mock_langfuse.get_prompt.assert_called_once_with("FAIR_violation")

    @pytest.mark.asyncio
    async def test_sentinel_hit_returns_default_data(self, clean_cache, mock_langfuse):
        default_data = {"prompt": "default", "name": "FAIR_violation", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default"}
        _seed_cache(clean_cache, "FAIR", "default", default_data)
        _seed_sentinel(clean_cache, "FAIR", "Miami1")

        result = await clean_cache.get_prompt("FAIR", "Miami1")

        assert result is default_data
        mock_langfuse.get_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_second_call_for_same_mls_hits_cache(self, clean_cache, mock_langfuse):
        await clean_cache.get_prompt("FAIR", "Miami")
        langfuse_call_count = mock_langfuse.get_prompt.call_count

        # Second call — should not touch Langfuse at all
        await clean_cache.get_prompt("FAIR", "Miami")
        assert mock_langfuse.get_prompt.call_count == langfuse_call_count


# ============================================================================
# Test: load_batch_prompts
# ============================================================================

class TestLoadBatchPrompts:

    @pytest.mark.asyncio
    async def test_all_cached_no_langfuse_calls(self, clean_cache, mock_langfuse):
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "f"})
        _seed_cache(clean_cache, "COMP", "default", {"prompt": "c"})

        pairs = [("FAIR", "default"), ("COMP", "default")]
        result = await clean_cache.load_batch_prompts(pairs)

        assert result[("FAIR", "default")]["prompt"] == "f"
        assert result[("COMP", "default")]["prompt"] == "c"
        mock_langfuse.get_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_pairs_fetched_from_langfuse(self, clean_cache, mock_langfuse):
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "cached"})

        pairs = [("FAIR", "default"), ("COMP", "default")]
        result = await clean_cache.load_batch_prompts(pairs)

        assert result[("FAIR", "default")] is not None
        assert result[("COMP", "default")] is not None
        # Only COMP needed a Langfuse fetch
        assert mock_langfuse.get_prompt.called

    @pytest.mark.asyncio
    async def test_sentinel_pairs_counted_as_cached(self, clean_cache, mock_langfuse):
        """A pair with a sentinel already set should NOT trigger a Langfuse call."""
        default_data = {"prompt": "d", "name": "FAIR_violation", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default"}
        _seed_cache(clean_cache, "FAIR", "default", default_data)
        _seed_sentinel(clean_cache, "FAIR", "Miami1")

        pairs = [("FAIR", "Miami1")]
        result = await clean_cache.load_batch_prompts(pairs)

        assert result[("FAIR", "Miami1")] is default_data
        mock_langfuse.get_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_for_unfound_prompts(self, clean_cache, langfuse_404):
        pairs = [("FAIR", "default")]
        result = await clean_cache.load_batch_prompts(pairs)
        assert result[("FAIR", "default")] is None

    @pytest.mark.asyncio
    async def test_mls_case_sensitivity_in_batch(self, clean_cache, mock_langfuse):
        """Miami and MIAMI in the same batch are independent lookups."""
        def side_effect(name):
            if "_Miami_" in name:
                return _make_prompt_obj("custom")
            raise Exception("404")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        pairs = [("FAIR", "Miami"), ("FAIR", "MIAMI")]
        result = await clean_cache.load_batch_prompts(pairs)

        # Miami → custom prompt found
        assert result[("FAIR", "Miami")]["name"] == "FAIR_Miami_violation"
        # MIAMI → sentinel resolved to default (default also not found here → None)
        assert result[("FAIR", "MIAMI")] is None


# ============================================================================
# Test: initialize
# ============================================================================

class TestInitialize:

    @pytest.mark.asyncio
    async def test_initialize_validates_langfuse_client(self, clean_cache, mock_langfuse):
        await clean_cache.initialize()
        # Cache is empty — no startup pre-warming; prompts load on-demand
        assert clean_cache._cache == {}

    @pytest.mark.asyncio
    async def test_raises_when_langfuse_client_is_none(self, clean_cache):
        with patch("app.core.prompt_cache.LANGFUSE_CLIENT", None):
            with pytest.raises(RuntimeError, match="LANGFUSE_CLIENT is not initialised"):
                await clean_cache.initialize()

    @pytest.mark.asyncio
    async def test_double_initialize_is_skipped(self, clean_cache, mock_langfuse):
        await clean_cache.initialize()

        # Manually add an entry to verify it survives the second init
        _seed_cache(clean_cache, "EXTRA", "default", {"prompt": "extra"})

        await clean_cache.initialize()  # should be a no-op

        assert "EXTRA" in clean_cache._cache

    @pytest.mark.asyncio
    async def test_initialize_succeeds_even_with_langfuse_issues(self, clean_cache, langfuse_404):
        """initialize() only validates Langfuse client, does not fetch prompts."""
        await clean_cache.initialize()  # must not raise

        # Cache is empty — prompts load on-demand
        assert clean_cache._cache == {}


# ============================================================================
# Test: refresh_prompt
# ============================================================================

class TestRefreshPrompt:

    @pytest.mark.asyncio
    async def test_evicts_and_reloads(self, clean_cache, mock_langfuse):
        old_data = {"prompt": "old", "name": "FAIR_violation", "config": {}, "version": "1.0", "rule_id": "FAIR", "mls_id": "default"}
        _seed_cache(clean_cache, "FAIR", "default", old_data)

        new_obj = _make_prompt_obj("new text", version="2.0")
        mock_langfuse.get_prompt = Mock(return_value=new_obj)

        result = await clean_cache.refresh_prompt("FAIR", "default")

        assert result["prompt"] == "new text"
        assert result["version"] == "2.0"
        assert clean_cache._cache["FAIR"]["default"]["version"] == "2.0"

    @pytest.mark.asyncio
    async def test_refresh_uses_verbatim_mls_id(self, clean_cache, mock_langfuse):
        """refresh_prompt('FAIR', 'Miami') must evict 'Miami', not 'MIAMI'."""
        miami_data = {"prompt": "miami", "name": "FAIR_Miami_violation", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "Miami"}
        MIAMI_data = {"prompt": "MIAMI", "name": "FAIR_MIAMI_violation", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "MIAMI"}
        _seed_cache(clean_cache, "FAIR", "Miami", miami_data)
        _seed_cache(clean_cache, "FAIR", "MIAMI", MIAMI_data)

        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("refreshed Miami"))

        await clean_cache.refresh_prompt("FAIR", "Miami")

        # "Miami" was evicted and reloaded
        assert clean_cache._cache["FAIR"]["Miami"]["prompt"] == "refreshed Miami"
        # "MIAMI" was NOT touched
        assert clean_cache._cache["FAIR"]["MIAMI"]["prompt"] == "MIAMI"

    @pytest.mark.asyncio
    async def test_refresh_sentinel_retriggers_langfuse_lookup(self, clean_cache, mock_langfuse):
        """Refreshing a sentinel entry should re-attempt the Langfuse lookup."""
        _seed_sentinel(clean_cache, "FAIR", "Miami1")
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "d", "name": "FAIR_violation", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default"})

        # Now a custom prompt exists in Langfuse
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("now custom"))

        result = await clean_cache.refresh_prompt("FAIR", "Miami1")

        assert result["name"] == "FAIR_Miami1_violation"
        assert isinstance(clean_cache._cache["FAIR"]["Miami1"], dict)


# ============================================================================
# Test: get_cache_stats
# ============================================================================

class TestGetCacheStats:

    def test_empty_cache(self, clean_cache):
        stats = clean_cache.get_cache_stats()
        assert stats["total_prompts_cached"] == 0
        assert stats["total_sentinel_entries"] == 0
        assert stats["cache"] == {}

    def test_counts_real_and_sentinel_separately(self, clean_cache):
        _seed_cache(clean_cache, "FAIR", "default", {"p": 1})
        _seed_cache(clean_cache, "FAIR", "Miami", {"p": 2})
        _seed_sentinel(clean_cache, "FAIR", "Miami1")
        _seed_sentinel(clean_cache, "FAIR", "Miami2")
        _seed_cache(clean_cache, "COMP", "default", {"p": 3})

        stats = clean_cache.get_cache_stats()

        assert stats["total_prompts_cached"] == 3     # FAIR/default, FAIR/Miami, COMP/default
        assert stats["total_sentinel_entries"] == 2   # FAIR/Miami1, FAIR/Miami2

    def test_cache_view_structure(self, clean_cache):
        _seed_cache(clean_cache, "FAIR", "default", {"p": 1})
        _seed_sentinel(clean_cache, "FAIR", "Miami1")

        stats = clean_cache.get_cache_stats()

        assert "FAIR" in stats["cache"]
        assert "default" in stats["cache"]["FAIR"]["loaded"]
        assert "Miami1" in stats["cache"]["FAIR"]["uses_default"]

    def test_sentinel_not_counted_as_real_prompt(self, clean_cache):
        _seed_sentinel(clean_cache, "FAIR", "Miami1")
        stats = clean_cache.get_cache_stats()
        assert stats["total_prompts_cached"] == 0
        assert stats["total_sentinel_entries"] == 1

    def test_mls_ids_preserved_in_stats(self, clean_cache):
        """Stats must show the verbatim MLS IDs, not uppercased versions."""
        _seed_cache(clean_cache, "FAIR", "Miami", {"p": 1})
        _seed_sentinel(clean_cache, "FAIR", "Miami1")

        stats = clean_cache.get_cache_stats()
        assert "Miami" in stats["cache"]["FAIR"]["loaded"]
        assert "Miami1" in stats["cache"]["FAIR"]["uses_default"]
        # Must NOT appear uppercased
        assert "MIAMI" not in stats["cache"]["FAIR"]["loaded"]


# ============================================================================
# Test: clear_cache
# ============================================================================

class TestClearCache:

    def test_empties_entire_cache(self, clean_cache):
        _seed_cache(clean_cache, "FAIR", "default", {"p": 1})
        _seed_cache(clean_cache, "COMP", "Miami", {"p": 2})
        _seed_sentinel(clean_cache, "FAIR", "Miami1")

        clean_cache.clear_cache()

        assert clean_cache._cache == {}

    def test_cache_usable_after_clear(self, clean_cache, mock_langfuse):
        _seed_cache(clean_cache, "FAIR", "default", {"p": 1})
        clean_cache.clear_cache()

        # Can store again without issues
        _seed_cache(clean_cache, "COMP", "default", {"p": 2})
        assert clean_cache._cache["COMP"]["default"]["p"] == 2


# ============================================================================
# Test: Integration / end-to-end scenarios
# ============================================================================

class TestIntegration:

    @pytest.mark.asyncio
    async def test_first_request_unknown_mls_uses_default(self, clean_cache, mock_langfuse):
        """
        An MLS ID never seen before: custom not in Langfuse → sentinel stored →
        default loaded → correct data returned.
        """
        def side_effect(name):
            if "UnknownMLS" in name:
                raise Exception("404")
            return _make_prompt_obj("default prompt")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        result = await clean_cache.get_prompt("FAIR", "UnknownMLS")

        assert result is not None
        assert result["name"] == "FAIR_violation"

    @pytest.mark.asyncio
    async def test_second_request_unknown_mls_no_langfuse_call(self, clean_cache, mock_langfuse):
        """After first request, subsequent calls for same unknown MLS must NOT hit Langfuse."""
        def side_effect(name):
            if "UnknownMLS" in name:
                raise Exception("404")
            return _make_prompt_obj()

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        await clean_cache.get_prompt("FAIR", "UnknownMLS")
        calls_after_first = mock_langfuse.get_prompt.call_count

        await clean_cache.get_prompt("FAIR", "UnknownMLS")
        await clean_cache.get_prompt("FAIR", "UnknownMLS")

        assert mock_langfuse.get_prompt.call_count == calls_after_first  # no new calls

    @pytest.mark.asyncio
    async def test_known_custom_mls_always_uses_custom_prompt(self, clean_cache, mock_langfuse):
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("custom Miami"))

        result = await clean_cache.get_prompt("FAIR", "Miami")

        assert result["name"] == "FAIR_Miami_violation"
        assert result["mls_id"] == "Miami"

    @pytest.mark.asyncio
    async def test_multiple_rules_same_mls_id_independent(self, clean_cache, mock_langfuse):
        """FAIR and COMP with the same MLS ID are stored independently."""
        def side_effect(name):
            if "Miami" in name and "FAIR" in name:
                return _make_prompt_obj("custom FAIR Miami")
            if "Miami" in name and "COMP" in name:
                raise Exception("404")  # no custom COMP for Miami
            return _make_prompt_obj("default")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        fair_result = await clean_cache.get_prompt("FAIR", "Miami")
        comp_result = await clean_cache.get_prompt("COMP", "Miami")

        assert fair_result["name"] == "FAIR_Miami_violation"
        assert comp_result["name"] == "COMP_violation"  # fell back to default

    @pytest.mark.asyncio
    async def test_batch_then_single_get_consistent(self, clean_cache, mock_langfuse):
        """Results from load_batch_prompts and get_prompt are consistent."""
        batch_result = await clean_cache.load_batch_prompts([("FAIR", "default")])
        single_result = await clean_cache.get_prompt("FAIR", "default")

        assert batch_result[("FAIR", "default")] is single_result

    @pytest.mark.asyncio
    async def test_concurrent_loads_same_pair_safe(self, clean_cache, mock_langfuse):
        """
        Concurrent requests for the same (rule_id, mls_id) must all succeed and
        return consistent data.

        Note: _load_prompt has no deduplication lock, so multiple concurrent
        coroutines that all see a cache miss may each call Langfuse independently
        before any of them writes to the cache.  That is acceptable — the last
        writer wins and subsequent requests hit the cache.  What we guarantee is:
          1. Every result is non-None.
          2. Every result contains the same data (equal dicts).
          3. After the gather, all future calls are served from cache (no new
             Langfuse calls).
        """
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj())

        tasks = [clean_cache.get_prompt("FAIR", "default") for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All results must be valid prompt data dicts
        assert all(r is not None for r in results)
        assert all(isinstance(r, dict) for r in results)

        # All results must carry the same content (idempotent load)
        first = results[0]
        assert all(r["name"] == first["name"] for r in results)

        # After the concurrent load, the cache is warm — no more Langfuse calls
        calls_after_gather = mock_langfuse.get_prompt.call_count
        await clean_cache.get_prompt("FAIR", "default")
        assert mock_langfuse.get_prompt.call_count == calls_after_gather


# ============================================================================
# Test: Performance
# ============================================================================

class TestPerformance:

    def test_cache_read_is_fast(self, clean_cache):
        """100 synchronous cache reads should complete in under 10ms."""
        for i in range(100):
            _seed_cache(clean_cache, f"RULE{i}", "default", {"prompt": f"p{i}"})

        start = time.perf_counter()
        for i in range(100):
            clean_cache._get_from_cache(f"RULE{i}", "default")
        elapsed = time.perf_counter() - start

        assert elapsed < 0.01, f"Cache reads too slow: {elapsed:.4f}s"

    def test_sentinel_resolution_is_fast(self, clean_cache):
        """1000 sentinel resolutions should complete in under 10ms."""
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "default"})
        for i in range(1000):
            _seed_sentinel(clean_cache, "FAIR", f"MLS{i}")

        start = time.perf_counter()
        for i in range(1000):
            clean_cache._get_from_cache("FAIR", f"MLS{i}")
        elapsed = time.perf_counter() - start

        assert elapsed < 0.01, f"Sentinel resolutions too slow: {elapsed:.4f}s"


# ============================================================================
# Test: TTL-based cache expiry
# ============================================================================

class TestTTL:

    def test_fresh_entry_is_cache_hit(self, clean_cache):
        """Entries younger than TTL are returned normally."""
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "fresh"})
        result = clean_cache._get_from_cache("FAIR", "default")
        assert result is not None
        assert result["prompt"] == "fresh"

    def test_expired_entry_is_cache_miss(self, clean_cache):
        """Entries older than TTL are evicted and return None."""
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "stale"})
        # Manually backdate the timestamp past TTL
        clean_cache._cache_timestamps["FAIR"]["default"] = time.time() - clean_cache._ttl - 1

        result = clean_cache._get_from_cache("FAIR", "default")
        assert result is None
        # Entry should have been evicted
        assert "default" not in clean_cache._cache.get("FAIR", {})

    def test_expired_sentinel_is_cache_miss(self, clean_cache):
        """Expired sentinels are evicted so custom lookup is retried on next access."""
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "d"})
        _seed_sentinel(clean_cache, "FAIR", "Miami")
        # Backdate only the sentinel
        clean_cache._cache_timestamps["FAIR"]["Miami"] = time.time() - clean_cache._ttl - 1

        result = clean_cache._get_from_cache("FAIR", "Miami")
        assert result is None

    def test_ttl_zero_disables_expiry(self, clean_cache):
        """When TTL is 0, entries never expire regardless of age."""
        original_ttl = clean_cache._ttl
        try:
            clean_cache._ttl = 0
            _seed_cache(clean_cache, "FAIR", "default", {"prompt": "forever"})
            # Backdate far into the past
            clean_cache._cache_timestamps["FAIR"]["default"] = 0

            result = clean_cache._get_from_cache("FAIR", "default")
            assert result is not None
            assert result["prompt"] == "forever"
        finally:
            clean_cache._ttl = original_ttl

    @pytest.mark.asyncio
    async def test_expired_entry_triggers_langfuse_refetch(self, clean_cache, mock_langfuse):
        """After TTL expiry, get_prompt re-fetches from Langfuse automatically."""
        old = {
            "prompt": "old", "name": "FAIR_violation",
            "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default",
        }
        _seed_cache(clean_cache, "FAIR", "default", old)
        # Backdate past TTL
        clean_cache._cache_timestamps["FAIR"]["default"] = time.time() - clean_cache._ttl - 1

        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("updated text", version="2.0"))

        result = await clean_cache.get_prompt("FAIR", "default")
        assert result["prompt"] == "updated text"
        assert result["version"] == "2.0"
        mock_langfuse.get_prompt.assert_called()

    @pytest.mark.asyncio
    async def test_expired_sentinel_retries_custom_lookup(self, clean_cache, mock_langfuse):
        """When sentinel expires, custom-prompt discovery is retried in Langfuse."""
        _seed_cache(clean_cache, "FAIR", "default", {
            "prompt": "d", "name": "FAIR_violation",
            "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default",
        })
        _seed_sentinel(clean_cache, "FAIR", "Miami")
        # Expire both sentinel and default so the full re-discovery runs
        clean_cache._cache_timestamps["FAIR"]["Miami"] = time.time() - clean_cache._ttl - 1
        clean_cache._cache_timestamps["FAIR"]["default"] = time.time() - clean_cache._ttl - 1

        # Langfuse now has a custom prompt for Miami
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("now custom"))

        result = await clean_cache.get_prompt("FAIR", "Miami")
        assert result["name"] == "FAIR_Miami_violation"

    def test_stats_include_ttl_seconds(self, clean_cache):
        """get_cache_stats must include the configured TTL value."""
        stats = clean_cache.get_cache_stats()
        assert "ttl_seconds" in stats
        assert stats["ttl_seconds"] == clean_cache._ttl

    @pytest.mark.asyncio
    async def test_refresh_prompt_resets_ttl(self, clean_cache, mock_langfuse):
        """After refresh_prompt, the entry gets a fresh timestamp."""
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "old", "name": "FAIR_violation", "config": {}, "version": "1", "rule_id": "FAIR", "mls_id": "default"})
        # Backdate
        clean_cache._cache_timestamps["FAIR"]["default"] = time.time() - clean_cache._ttl - 1

        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("refreshed"))
        await clean_cache.refresh_prompt("FAIR", "default")

        # Should now be fresh
        result = clean_cache._get_from_cache("FAIR", "default")
        assert result is not None
        assert result["prompt"] == "refreshed"


# ============================================================================
# Test: refresh_rule / refresh_all_prompts
# ============================================================================

class TestRefreshBulk:

    @pytest.mark.asyncio
    async def test_refresh_rule_reloads_all_mls_entries(self, clean_cache, mock_langfuse):
        """refresh_rule reloads every MLS entry under a specific rule."""
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "d"})
        _seed_cache(clean_cache, "FAIR", "Miami", {"prompt": "m"})
        _seed_sentinel(clean_cache, "FAIR", "UnknownMLS")

        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("reloaded"))

        stats = await clean_cache.refresh_rule("FAIR")

        assert "FAIR" in stats["cache"]
        # All entries should have been reloaded from Langfuse
        mock_langfuse.get_prompt.assert_called()

    @pytest.mark.asyncio
    async def test_refresh_all_prompts_clears_and_reloads(self, clean_cache, mock_langfuse):
        """refresh_all_prompts rebuilds the entire cache from Langfuse."""
        _seed_cache(clean_cache, "FAIR", "default", {"prompt": "f"})
        _seed_cache(clean_cache, "COMP", "default", {"prompt": "c"})

        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("fresh"))

        stats = await clean_cache.refresh_all_prompts()

        assert stats["total_prompts_cached"] >= 2
        mock_langfuse.get_prompt.assert_called()

    @pytest.mark.asyncio
    async def test_refresh_rule_no_entries_is_noop(self, clean_cache, mock_langfuse):
        """refresh_rule for a rule with no cached entries is a safe no-op."""
        stats = await clean_cache.refresh_rule("NONEXISTENT")
        assert stats["total_prompts_cached"] == 0
        mock_langfuse.get_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_all_empty_cache_is_noop(self, clean_cache, mock_langfuse):
        """refresh_all_prompts on an empty cache is a safe no-op."""
        stats = await clean_cache.refresh_all_prompts()
        assert stats["total_prompts_cached"] == 0
        mock_langfuse.get_prompt.assert_not_called()