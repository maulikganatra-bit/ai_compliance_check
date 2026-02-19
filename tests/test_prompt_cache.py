"""
Test suite for PromptManager (no-cache, fresh fetch from Langfuse per request)

Naming convention under test:
  - Default prompt : {RULE_ID}_violation          e.g. FAIR_violation
  - Custom prompt  : {RULE_ID}_{MLS_ID}_violation  e.g. FAIR_Miami_violation

Key behaviours:
  - rule_id  : always uppercased internally
  - mls_id   : case-sensitive, used exactly as received
  - Every call fetches fresh from Langfuse (no caching)
  - Custom -> default fallback on each request

Run all tests:
    pytest tests/test_prompt_cache.py -v

Run with coverage:
    pytest tests/test_prompt_cache.py --cov=app.core.prompt_cache --cov-report=html
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from app.core.prompt_cache import (
    PromptManager,
    get_prompt_manager,
    _custom_prompt_name,
    _default_prompt_name,
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


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def manager():
    """Return the singleton PromptManager."""
    return get_prompt_manager()


@pytest.fixture
def mock_langfuse(manager):
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
        """MLS ID must NOT be uppercased -- case-sensitive."""
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
        a = get_prompt_manager()
        b = get_prompt_manager()
        c = PromptManager()
        assert a is b is c


# ============================================================================
# Test: _load_prompt -- custom -> default fallback
# ============================================================================

class TestLoadPrompt:

    @pytest.mark.asyncio
    async def test_loads_custom_when_found_in_langfuse(self, manager, mock_langfuse):
        """When Langfuse returns a prompt for FAIR_Miami_violation, it is used."""
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("custom text"))

        result = await manager._load_prompt("FAIR", "Miami")

        assert result is not None
        assert result["mls_id"] == "Miami"
        assert result["name"] == "FAIR_Miami_violation"

    @pytest.mark.asyncio
    async def test_fallback_loads_default_when_custom_missing(self, manager, mock_langfuse):
        """After failing to find custom, the default prompt is loaded and returned."""
        def side_effect(name):
            if "Miami" in name:
                raise Exception("404")
            return _make_prompt_obj("default text")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        result = await manager._load_prompt("FAIR", "Miami")

        assert result is not None
        assert result["name"] == "FAIR_violation"

    @pytest.mark.asyncio
    async def test_returns_none_when_both_custom_and_default_missing(self, manager, langfuse_404):
        result = await manager._load_prompt("FAIR", "Miami")
        assert result is None

    @pytest.mark.asyncio
    async def test_default_request_skips_custom_lookup(self, manager, mock_langfuse):
        """Requesting mls_id='default' must never attempt a custom Langfuse lookup."""
        names_fetched = []
        mock_langfuse.get_prompt = Mock(side_effect=lambda n: (names_fetched.append(n), _make_prompt_obj())[1])

        await manager._load_prompt("FAIR", "default")

        # Only FAIR_violation should have been tried, not FAIR_default_violation
        assert "FAIR_default_violation" not in names_fetched
        assert "FAIR_violation" in names_fetched

    @pytest.mark.asyncio
    async def test_mls_id_case_preserved_in_result(self, manager, mock_langfuse):
        """Custom prompt result preserves exact MLS ID casing."""
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj())

        result = await manager._load_prompt("FAIR", "Miami")

        assert result["mls_id"] == "Miami"
        assert result["name"] == "FAIR_Miami_violation"

    @pytest.mark.asyncio
    async def test_miami_and_MIAMI_are_independent_lookups(self, manager, mock_langfuse):
        """Two requests with different MLS ID casing result in different Langfuse lookups."""
        names_fetched = []

        def side_effect(name):
            names_fetched.append(name)
            if "_Miami_" in name:
                return _make_prompt_obj("custom Miami")
            raise Exception("404")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        res_miami = await manager._load_prompt("FAIR", "Miami")
        res_MIAMI = await manager._load_prompt("FAIR", "MIAMI")

        # Miami -> custom prompt found
        assert res_miami["name"] == "FAIR_Miami_violation"
        # MIAMI -> custom not found, fell back to default (also not found -> None)
        assert res_MIAMI is None

    @pytest.mark.asyncio
    async def test_always_fetches_from_langfuse(self, manager, mock_langfuse):
        """Every call fetches fresh from Langfuse -- no caching."""
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj())

        await manager._load_prompt("FAIR", "default")
        first_call_count = mock_langfuse.get_prompt.call_count

        await manager._load_prompt("FAIR", "default")
        second_call_count = mock_langfuse.get_prompt.call_count

        # Second call should also hit Langfuse
        assert second_call_count > first_call_count


# ============================================================================
# Test: get_prompt (public, single pair)
# ============================================================================

class TestGetPrompt:

    @pytest.mark.asyncio
    async def test_fetches_from_langfuse(self, manager, mock_langfuse):
        """get_prompt always fetches fresh from Langfuse."""
        result = await manager.get_prompt("FAIR", "default")

        assert result is not None
        mock_langfuse.get_prompt.assert_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, manager, langfuse_404):
        result = await manager.get_prompt("FAIR", "default")
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_fallback_to_default(self, manager, mock_langfuse):
        """When custom prompt not found, falls back to default."""
        def side_effect(name):
            if "Miami" in name:
                raise Exception("404")
            return _make_prompt_obj("default text")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        result = await manager.get_prompt("FAIR", "Miami")
        assert result is not None
        assert result["name"] == "FAIR_violation"


# ============================================================================
# Test: load_batch_prompts
# ============================================================================

class TestLoadBatchPrompts:

    @pytest.mark.asyncio
    async def test_fetches_all_from_langfuse(self, manager, mock_langfuse):
        """All pairs are fetched from Langfuse concurrently."""
        pairs = [("FAIR", "default"), ("COMP", "default")]
        result = await manager.load_batch_prompts(pairs)

        assert result[("FAIR", "default")] is not None
        assert result[("COMP", "default")] is not None
        # Langfuse was called for each pair
        assert mock_langfuse.get_prompt.call_count >= 2

    @pytest.mark.asyncio
    async def test_returns_none_for_unfound_prompts(self, manager, langfuse_404):
        pairs = [("FAIR", "default")]
        result = await manager.load_batch_prompts(pairs)
        assert result[("FAIR", "default")] is None

    @pytest.mark.asyncio
    async def test_mls_case_sensitivity_in_batch(self, manager, mock_langfuse):
        """Miami and MIAMI in the same batch are independent lookups."""
        def side_effect(name):
            if "_Miami_" in name:
                return _make_prompt_obj("custom")
            raise Exception("404")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        pairs = [("FAIR", "Miami"), ("FAIR", "MIAMI")]
        result = await manager.load_batch_prompts(pairs)

        # Miami -> custom prompt found
        assert result[("FAIR", "Miami")]["name"] == "FAIR_Miami_violation"
        # MIAMI -> not found (no custom, no default)
        assert result[("FAIR", "MIAMI")] is None

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, manager, mock_langfuse):
        """Exceptions during fetch result in None for that pair."""
        call_count = {"n": 0}

        def side_effect(name):
            call_count["n"] += 1
            if "COMP" in name:
                raise Exception("Connection timeout")
            return _make_prompt_obj()

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        pairs = [("FAIR", "default"), ("COMP", "default")]
        result = await manager.load_batch_prompts(pairs)

        assert result[("FAIR", "default")] is not None
        assert result[("COMP", "default")] is None

    @pytest.mark.asyncio
    async def test_mixed_custom_and_default(self, manager, mock_langfuse):
        """Batch with mixed custom and default prompt lookups."""
        def side_effect(name):
            if "_Miami_" in name and "FAIR" in name:
                return _make_prompt_obj("custom FAIR Miami")
            if "_Miami_" in name and "COMP" in name:
                raise Exception("404")
            return _make_prompt_obj("default")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        pairs = [("FAIR", "Miami"), ("COMP", "Miami")]
        result = await manager.load_batch_prompts(pairs)

        assert result[("FAIR", "Miami")]["name"] == "FAIR_Miami_violation"
        assert result[("COMP", "Miami")]["name"] == "COMP_violation"  # fell back to default


# ============================================================================
# Test: initialize
# ============================================================================

class TestInitialize:

    @pytest.mark.asyncio
    async def test_initialize_validates_langfuse_client(self, manager, mock_langfuse):
        await manager.initialize()
        # No error: Langfuse client is valid

    @pytest.mark.asyncio
    async def test_raises_when_langfuse_client_is_none(self, manager):
        with patch("app.core.prompt_cache.LANGFUSE_CLIENT", None):
            with pytest.raises(RuntimeError, match="LANGFUSE_CLIENT is not initialised"):
                await manager.initialize()


# ============================================================================
# Test: Integration / end-to-end scenarios
# ============================================================================

class TestIntegration:

    @pytest.mark.asyncio
    async def test_unknown_mls_uses_default(self, manager, mock_langfuse):
        """
        An MLS ID never seen before: custom not in Langfuse ->
        default loaded -> correct data returned.
        """
        def side_effect(name):
            if "UnknownMLS" in name:
                raise Exception("404")
            return _make_prompt_obj("default prompt")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        result = await manager.get_prompt("FAIR", "UnknownMLS")

        assert result is not None
        assert result["name"] == "FAIR_violation"

    @pytest.mark.asyncio
    async def test_known_custom_mls_uses_custom_prompt(self, manager, mock_langfuse):
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("custom Miami"))

        result = await manager.get_prompt("FAIR", "Miami")

        assert result["name"] == "FAIR_Miami_violation"
        assert result["mls_id"] == "Miami"

    @pytest.mark.asyncio
    async def test_multiple_rules_same_mls_id_independent(self, manager, mock_langfuse):
        """FAIR and COMP with the same MLS ID are independent lookups."""
        def side_effect(name):
            if "Miami" in name and "FAIR" in name:
                return _make_prompt_obj("custom FAIR Miami")
            if "Miami" in name and "COMP" in name:
                raise Exception("404")
            return _make_prompt_obj("default")

        mock_langfuse.get_prompt = Mock(side_effect=side_effect)

        fair_result = await manager.get_prompt("FAIR", "Miami")
        comp_result = await manager.get_prompt("COMP", "Miami")

        assert fair_result["name"] == "FAIR_Miami_violation"
        assert comp_result["name"] == "COMP_violation"  # fell back to default

    @pytest.mark.asyncio
    async def test_concurrent_fetches_safe(self, manager, mock_langfuse):
        """
        Concurrent requests for the same (rule_id, mls_id) must all succeed
        and return consistent data.
        """
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj())

        tasks = [manager.get_prompt("FAIR", "default") for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All results must be valid prompt data dicts
        assert all(r is not None for r in results)
        assert all(isinstance(r, dict) for r in results)

        # All results must carry the same content
        first = results[0]
        assert all(r["name"] == first["name"] for r in results)

    @pytest.mark.asyncio
    async def test_batch_and_single_return_equivalent_data(self, manager, mock_langfuse):
        """Results from load_batch_prompts and get_prompt contain the same data."""
        batch_result = await manager.load_batch_prompts([("FAIR", "default")])
        single_result = await manager.get_prompt("FAIR", "default")

        assert batch_result[("FAIR", "default")]["name"] == single_result["name"]
        assert batch_result[("FAIR", "default")]["prompt"] == single_result["prompt"]

    @pytest.mark.asyncio
    async def test_every_request_gets_latest_version(self, manager, mock_langfuse):
        """Without caching, prompt version changes are picked up immediately."""
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("v1 text", version="1.0"))
        result_v1 = await manager.get_prompt("FAIR", "default")
        assert result_v1["version"] == "1.0"

        # Simulate Langfuse prompt update
        mock_langfuse.get_prompt = Mock(return_value=_make_prompt_obj("v2 text", version="2.0"))
        result_v2 = await manager.get_prompt("FAIR", "default")
        assert result_v2["version"] == "2.0"
