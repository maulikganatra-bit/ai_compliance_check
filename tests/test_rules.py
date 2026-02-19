"""Unit tests for the rule system.

Tests cover:
- make_rule_function() factory for all 4 rule types (FAIR, COMP, PROMO, PRWD)
- execute_rule_with_prompt() generic executor
- _build_input_fields() field normalisation
- _map_result_fields() field mapping back to API column names
- Registry (VALID_CHECK_COLUMNS, get_rule_function – fully dynamic)
- Retry behaviour via the @retry_with_backoff decorator
- Rate limiter integration (token estimation + header updates)
- Edge cases: empty input, missing fields, invalid JSON, None prompt_data
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rules.base import (
    make_rule_function,
    execute_rule_with_prompt,
    _build_input_fields,
    _map_result_fields,
)
from app.rules.registry import (
    VALID_CHECK_COLUMNS,
    get_rule_function,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_RULE_IDS = ["FAIR", "COMP", "PROMO", "PRWD"]

ALL_COLUMN_NAMES = [
    "Remarks", "PrivateRemarks", "Directions", "ShowingInstructions",
    "ConfidentialRemarks", "SupplementRemarks", "Concessions", "SaleFactors",
]

FIELD_MAP_PAIRS = [
    ("public_remarks", "Remarks"),
    ("private_agent_remarks", "PrivateRemarks"),
    ("directions", "Directions"),
    ("showing_instructions", "ShowingInstructions"),
    ("confidential_remarks", "ConfidentialRemarks"),
    ("supplement_remarks", "SupplementRemarks"),
    ("concessions", "Concessions"),
    ("sale_factors", "SaleFactors"),
]


def _make_openai_response(output_json: str, total_tokens: int = 150):
    """Build a mock OpenAI response whose output_text wraps *output_json*
    in a fenced code block exactly as the real API does."""
    resp = MagicMock()
    resp.output_text = f"```json\n{output_json}\n```"
    resp.usage = MagicMock()
    resp.usage.total_tokens = total_tokens
    resp.http_response = MagicMock()
    resp.http_response.headers = {
        "x-ratelimit-limit-tokens": "10000000",
        "x-ratelimit-remaining-tokens": "9999850",
        "x-ratelimit-reset-tokens": "6m0s",
        "x-ratelimit-limit-requests": "10000",
        "x-ratelimit-remaining-requests": "9999",
        "x-ratelimit-reset-requests": "1s",
    }
    return resp


# A minimal valid JSON that execute_rule_with_prompt expects from the model.
_CLEAN_RESULT_JSON = """{
    "result": {
        "public_remarks": [],
        "private_agent_remarks": [],
        "directions": [],
        "showing_instructions": [],
        "confidential_remarks": [],
        "supplement_remarks": [],
        "concessions": [],
        "sale_factors": []
    }
}"""

_VIOLATIONS_RESULT_JSON = """{
    "result": {
        "public_remarks": ["Discriminatory language detected"],
        "private_agent_remarks": ["Commission mentioned"],
        "directions": [],
        "showing_instructions": [],
        "confidential_remarks": [],
        "supplement_remarks": [],
        "concessions": [],
        "sale_factors": []
    }
}"""

_ALL_FIELDS_VIOLATIONS_JSON = """{
    "result": {
        "public_remarks": ["Violation A"],
        "private_agent_remarks": ["Violation B"],
        "directions": ["Violation C"],
        "showing_instructions": ["Violation D"],
        "confidential_remarks": ["Violation E"],
        "supplement_remarks": ["Violation F"],
        "concessions": ["Violation G"],
        "sale_factors": ["Violation H"]
    }
}"""


# ============================================================================
# TestBuildInputFields — unit tests for _build_input_fields
# ============================================================================

class TestBuildInputFields:
    """Tests for the field normalisation helper."""

    def test_maps_all_columns(self):
        """All 8 DataItem columns are mapped to their normalised keys."""
        field_values = {col: f"text_{col}" for col in ALL_COLUMN_NAMES}
        result = _build_input_fields(field_values)

        for norm_key, api_key in FIELD_MAP_PAIRS:
            assert result[norm_key] == f"text_{api_key}"

    def test_missing_columns_default_to_empty_string(self):
        """Columns not present in field_values default to empty strings."""
        result = _build_input_fields({})
        for norm_key, _ in FIELD_MAP_PAIRS:
            assert result[norm_key] == ""

    def test_none_values_default_to_empty_string(self):
        """None values are coerced to empty strings."""
        field_values = {col: None for col in ALL_COLUMN_NAMES}
        result = _build_input_fields(field_values)
        for norm_key, _ in FIELD_MAP_PAIRS:
            assert result[norm_key] == ""


# ============================================================================
# TestMapResultFields — unit tests for _map_result_fields
# ============================================================================

class TestMapResultFields:
    """Tests for the result → API column mapping helper."""

    def test_maps_violations_to_api_columns(self):
        """Violation lists are mapped from normalised keys to API column names."""
        json_result = {
            "public_remarks": ["V1"],
            "private_agent_remarks": ["V2"],
            "directions": [],
            "showing_instructions": [],
            "confidential_remarks": [],
            "supplement_remarks": [],
            "concessions": [],
            "sale_factors": [],
        }
        input_fields = {k: "some text" for k, _ in FIELD_MAP_PAIRS}
        mapped = _map_result_fields(json_result, input_fields, "TEST")

        assert mapped["Remarks"] == ["V1"]
        assert mapped["PrivateRemarks"] == ["V2"]
        # Fields with empty violations but non-empty input → empty list
        assert mapped["Directions"] == []

    def test_excludes_violations_when_input_was_empty(self):
        """Violations on a field whose input was empty are dropped with a warning."""
        json_result = {
            "public_remarks": ["Spurious violation"],
            "private_agent_remarks": [],
            "directions": [], "showing_instructions": [],
            "confidential_remarks": [], "supplement_remarks": [],
            "concessions": [], "sale_factors": [],
        }
        input_fields = {k: "" for k, _ in FIELD_MAP_PAIRS}  # all empty
        mapped = _map_result_fields(json_result, input_fields, "TEST")

        # Violation excluded because input was empty
        assert "Remarks" not in mapped

    def test_empty_input_fields_not_in_result(self):
        """Fields whose input was empty and have no violations are absent from result."""
        json_result = {
            "public_remarks": [],
            "private_agent_remarks": [],
            "directions": [], "showing_instructions": [],
            "confidential_remarks": [], "supplement_remarks": [],
            "concessions": [], "sale_factors": [],
        }
        input_fields = {k: "" for k, _ in FIELD_MAP_PAIRS}
        mapped = _map_result_fields(json_result, input_fields, "TEST")

        for _, api_key in FIELD_MAP_PAIRS:
            assert api_key not in mapped


# ============================================================================
# TestMakeRuleFunction — the factory that produces per-rule executors
# ============================================================================

class TestMakeRuleFunction:
    """Tests for make_rule_function() factory."""

    @pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
    def test_returns_callable_with_correct_name(self, rule_id):
        """Factory returns an async callable named execute_{rule}_rule."""
        func = make_rule_function(rule_id)
        assert callable(func)
        assert func.__name__ == f"execute_{rule_id.lower()}_rule"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
    async def test_success_basic_two_fields(
        self, rule_id, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """Each rule succeeds with Remarks + PrivateRemarks and returns expected keys."""
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        rule_func = make_rule_function(rule_id)

        with patch("app.rules.base.client", mock_openai_client):
            result = await rule_func(
                public_remarks="Beautiful home",
                private_remarks="Must see property",
                prompt_data=mock_prompt_data,
            )

        assert "Remarks" in result
        assert "PrivateRemarks" in result
        assert "Total_tokens" in result
        assert result["Total_tokens"] == 150
        mock_openai_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
    async def test_success_all_eight_fields(
        self, rule_id, mock_openai_client, mock_prompt_data
    ):
        """Rule executor handles all 8 columns when all are provided."""
        resp = _make_openai_response(_ALL_FIELDS_VIOLATIONS_JSON, total_tokens=300)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)
        rule_func = make_rule_function(rule_id)

        with patch("app.rules.base.client", mock_openai_client):
            result = await rule_func(
                public_remarks="rm",
                private_remarks="pr",
                directions="dir",
                ShowingInstructions="si",
                ConfidentialRemarks="cr",
                SupplementRemarks="sr",
                Concessions="co",
                SaleFactors="sf",
                prompt_data=mock_prompt_data,
            )

        for col in ALL_COLUMN_NAMES:
            assert col in result, f"Missing column {col} in result"
            assert len(result[col]) > 0, f"Expected violations for {col}"
        assert result["Total_tokens"] == 300

    @pytest.mark.asyncio
    async def test_no_violations_returns_empty_lists(
        self, mock_openai_client, mock_prompt_data
    ):
        """When the model returns no violations all populated fields get empty lists."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)
        rule_func = make_rule_function("FAIR")

        with patch("app.rules.base.client", mock_openai_client):
            result = await rule_func(
                public_remarks="Clean listing",
                private_remarks="No issues",
                prompt_data=mock_prompt_data,
            )

        assert result["Remarks"] == []
        assert result["PrivateRemarks"] == []

    @pytest.mark.asyncio
    async def test_violations_returned_correctly(
        self, mock_openai_client, mock_prompt_data
    ):
        """Violation strings from the model are included in the result."""
        resp = _make_openai_response(_VIOLATIONS_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)
        rule_func = make_rule_function("COMP")

        with patch("app.rules.base.client", mock_openai_client):
            result = await rule_func(
                public_remarks="3% commission offered",
                private_remarks="Generous compensation",
                prompt_data=mock_prompt_data,
            )

        assert result["Remarks"] == ["Discriminatory language detected"]
        assert result["PrivateRemarks"] == ["Commission mentioned"]

    @pytest.mark.asyncio
    async def test_raises_without_prompt_data(self, mock_openai_client):
        """Rule function raises ValueError when prompt_data is None."""
        rule_func = make_rule_function("FAIR")

        with patch("app.rules.base.client", mock_openai_client):
            with pytest.raises(ValueError, match="prompt_data is required"):
                await rule_func(
                    public_remarks="text",
                    private_remarks="text",
                    prompt_data=None,
                )


# ============================================================================
# TestExecuteRuleWithPrompt — the generic executor
# ============================================================================

class TestExecuteRuleWithPrompt:
    """Tests for execute_rule_with_prompt()."""

    @pytest.mark.asyncio
    async def test_renders_jinja2_template(self, mock_openai_client, mock_prompt_data):
        """Prompt template variables are rendered into the OpenAI system message."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)
        field_values = {"Remarks": "hello world", "PrivateRemarks": "secret"}

        with patch("app.rules.base.client", mock_openai_client):
            await execute_rule_with_prompt("FAIR", field_values, mock_prompt_data)

        call_kwargs = mock_openai_client.responses.create.call_args.kwargs
        system_msg = call_kwargs["input"][0]["content"]
        assert "hello world" in system_msg
        assert "secret" in system_msg

    @pytest.mark.asyncio
    async def test_uses_model_from_config(self, mock_openai_client, mock_prompt_data):
        """Model name is taken from prompt config."""
        mock_prompt_data["config"]["model"] = "gpt-4o-mini"
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client):
            await execute_rule_with_prompt("FAIR", {"Remarks": "x"}, mock_prompt_data)

        call_kwargs = mock_openai_client.responses.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_uses_temperature_and_top_p_from_config(
        self, mock_openai_client, mock_prompt_data
    ):
        """Temperature and top_p are forwarded from prompt config."""
        mock_prompt_data["config"]["temperature"] = "0.5"
        mock_prompt_data["config"]["top_p"] = "0.9"
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client):
            await execute_rule_with_prompt("FAIR", {"Remarks": "x"}, mock_prompt_data)

        call_kwargs = mock_openai_client.responses.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["top_p"] == 0.9

    @pytest.mark.asyncio
    async def test_raises_on_none_prompt_data(self, mock_openai_client):
        """ValueError raised when prompt_data is None."""
        with patch("app.rules.base.client", mock_openai_client):
            with pytest.raises(ValueError, match="prompt_data is required"):
                await execute_rule_with_prompt("FAIR", {"Remarks": "x"}, None)

    @pytest.mark.asyncio
    async def test_raises_on_invalid_model_output(self, mock_openai_client, mock_prompt_data):
        """ValueError raised when the model returns unparseable JSON."""
        bad_resp = _make_openai_response('{"not_result": "bad"}')
        mock_openai_client.responses.create = AsyncMock(return_value=bad_resp)

        with patch("app.rules.base.client", mock_openai_client):
            with pytest.raises(ValueError, match="invalid model output format"):
                await execute_rule_with_prompt("FAIR", {"Remarks": "x"}, mock_prompt_data)

    @pytest.mark.asyncio
    async def test_raises_on_empty_model_output(self, mock_openai_client, mock_prompt_data):
        """ValueError raised when the model returns empty output."""
        empty_resp = MagicMock()
        empty_resp.output_text = ""
        empty_resp.usage = MagicMock(total_tokens=0)
        empty_resp.http_response = MagicMock()
        empty_resp.http_response.headers = {}
        mock_openai_client.responses.create = AsyncMock(return_value=empty_resp)

        with patch("app.rules.base.client", mock_openai_client):
            with pytest.raises(ValueError, match="invalid model output format"):
                await execute_rule_with_prompt("FAIR", {"Remarks": "x"}, mock_prompt_data)

    @pytest.mark.asyncio
    async def test_total_tokens_included_in_result(
        self, mock_openai_client, mock_prompt_data
    ):
        """Total_tokens from the API response is included in the result dict."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON, total_tokens=999)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client):
            result = await execute_rule_with_prompt(
                "FAIR", {"Remarks": "text"}, mock_prompt_data
            )

        assert result["Total_tokens"] == 999

    @pytest.mark.asyncio
    async def test_updates_rate_limiter_from_headers(
        self, mock_openai_client, mock_prompt_data
    ):
        """Rate limiter update_from_headers is called after each API response."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client), \
             patch("app.rules.base.get_rate_limiter") as mock_get_rl:
            mock_rl = MagicMock()
            mock_rl.estimate_tokens.return_value = 100
            mock_rl.wait_if_needed = AsyncMock()
            mock_rl.update_from_headers = AsyncMock()
            mock_get_rl.return_value = mock_rl

            await execute_rule_with_prompt("FAIR", {"Remarks": "x"}, mock_prompt_data)

            mock_rl.update_from_headers.assert_awaited_once_with(resp)

    @pytest.mark.asyncio
    async def test_waits_on_rate_limiter_before_call(
        self, mock_openai_client, mock_prompt_data
    ):
        """Rate limiter wait_if_needed is called before the API call."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client), \
             patch("app.rules.base.get_rate_limiter") as mock_get_rl:
            mock_rl = MagicMock()
            mock_rl.estimate_tokens.return_value = 500
            mock_rl.wait_if_needed = AsyncMock()
            mock_rl.update_from_headers = AsyncMock()
            mock_get_rl.return_value = mock_rl

            await execute_rule_with_prompt("FAIR", {"Remarks": "some text"}, mock_prompt_data)

            mock_rl.wait_if_needed.assert_awaited_once()
            # Should be called with the estimated token count
            mock_rl.wait_if_needed.assert_awaited_once_with(500)

    @pytest.mark.asyncio
    async def test_only_populated_fields_appear_in_result(
        self, mock_openai_client, mock_prompt_data
    ):
        """Fields with empty input do NOT appear in the result even with no violations."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client):
            result = await execute_rule_with_prompt(
                "FAIR",
                {"Remarks": "has text"},  # only Remarks provided
                mock_prompt_data,
            )

        assert "Remarks" in result
        # Unpopulated fields should NOT be in the result
        assert "Directions" not in result
        assert "ShowingInstructions" not in result
        assert "Concessions" not in result


# ============================================================================
# TestRetryBehaviour — tests that the @retry_with_backoff decorator works
# ============================================================================

class TestRetryBehaviour:
    """Tests for retry logic on transient OpenAI errors."""

    @pytest.mark.asyncio
    async def test_retries_on_server_error(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """Rule retries on 500 APIError then succeeds."""
        from openai import APIError

        api_error = APIError("Server error", request=MagicMock(), body=None)
        api_error.status_code = 500

        mock_openai_client.responses.create = AsyncMock(
            side_effect=[api_error, mock_openai_response]
        )

        with patch("app.rules.base.client", mock_openai_client), \
             patch("asyncio.sleep", new=AsyncMock()):
            result = await execute_rule_with_prompt(
                "FAIR", {"Remarks": "test"}, mock_prompt_data
            )

        assert result is not None
        assert mock_openai_client.responses.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_timeout_error(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """Rule retries on APITimeoutError then succeeds."""
        from openai import APITimeoutError

        timeout = APITimeoutError(request=MagicMock())
        mock_openai_client.responses.create = AsyncMock(
            side_effect=[timeout, mock_openai_response]
        )

        with patch("app.rules.base.client", mock_openai_client), \
             patch("asyncio.sleep", new=AsyncMock()):
            result = await execute_rule_with_prompt(
                "COMP", {"Remarks": "test"}, mock_prompt_data
            )

        assert result is not None
        assert mock_openai_client.responses.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_error(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """Rule retries on RateLimitError (429) then succeeds."""
        from openai import RateLimitError

        rate_err = RateLimitError("Rate limit", request=MagicMock(), body=None)
        mock_openai_client.responses.create = AsyncMock(
            side_effect=[rate_err, mock_openai_response]
        )

        with patch("app.rules.base.client", mock_openai_client), \
             patch("asyncio.sleep", new=AsyncMock()):
            result = await execute_rule_with_prompt(
                "PROMO", {"Remarks": "test"}, mock_prompt_data
            )

        assert result is not None
        assert mock_openai_client.responses.create.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_raises(
        self, mock_openai_client, mock_prompt_data
    ):
        """After max retries the original exception is re-raised."""
        from openai import APITimeoutError

        timeout = APITimeoutError(request=MagicMock())
        mock_openai_client.responses.create = AsyncMock(side_effect=timeout)

        with patch("app.rules.base.client", mock_openai_client), \
             patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(APITimeoutError):
                await execute_rule_with_prompt(
                    "PRWD", {"Remarks": "test"}, mock_prompt_data
                )

        # initial attempt + 3 retries = 4 calls
        assert mock_openai_client.responses.create.call_count == 4

    @pytest.mark.asyncio
    async def test_non_retryable_error_not_retried(
        self, mock_openai_client, mock_prompt_data
    ):
        """A 400-level APIError is NOT retried."""
        from openai import APIError

        client_error = APIError("Bad request", request=MagicMock(), body=None)
        client_error.status_code = 400

        mock_openai_client.responses.create = AsyncMock(side_effect=client_error)

        with patch("app.rules.base.client", mock_openai_client), \
             patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(APIError):
                await execute_rule_with_prompt(
                    "FAIR", {"Remarks": "test"}, mock_prompt_data
                )

        # Only a single attempt, no retry
        assert mock_openai_client.responses.create.call_count == 1


# ============================================================================
# TestRegistry — VALID_CHECK_COLUMNS, get_rule_function (fully dynamic)
# ============================================================================

class TestRegistry:
    """Tests for the dynamic rule registry module."""

    def test_valid_check_columns_contains_all_eight(self):
        """VALID_CHECK_COLUMNS lists all 8 accepted column names."""
        assert set(VALID_CHECK_COLUMNS) == set(ALL_COLUMN_NAMES)

    @pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
    def test_get_rule_function_returns_callable_for_known_rules(self, rule_id):
        """get_rule_function returns a callable for every known rule ID."""
        func = get_rule_function("ANY_MLS", rule_id)
        assert callable(func)

    def test_get_rule_function_returns_callable_for_unknown_rule(self):
        """get_rule_function returns a callable for ANY rule ID (dynamic)."""
        func = get_rule_function("ANY_MLS", "BRAND_NEW_RULE")
        assert callable(func)

    def test_get_rule_function_case_insensitive(self):
        """get_rule_function normalises rule_id to uppercase."""
        func = get_rule_function("MLS", "fair")
        assert callable(func)

    def test_get_rule_function_different_calls_are_independent(self):
        """Each call returns a fresh callable (not cached reference)."""
        f1 = get_rule_function("MLS1", "FAIR")
        f2 = get_rule_function("MLS2", "FAIR")
        # Both callable but not the exact same object
        assert callable(f1) and callable(f2)


# ============================================================================
# TestRuleIntegration — cross-cutting tests across all 4 rules
# ============================================================================

class TestRuleIntegration:
    """Integration tests exercising all rule types together."""

    @pytest.mark.asyncio
    async def test_all_rules_succeed_sequentially(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """All 4 rules complete successfully one after another."""
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)

        with patch("app.rules.base.client", mock_openai_client):
            for rule_id in ALL_RULE_IDS:
                rule_func = make_rule_function(rule_id)
                result = await rule_func(
                    public_remarks="test",
                    private_remarks="test",
                    prompt_data=mock_prompt_data,
                )
                assert result is not None
                assert "Total_tokens" in result

        assert mock_openai_client.responses.create.call_count == len(ALL_RULE_IDS)

    @pytest.mark.asyncio
    async def test_all_rules_retry_on_timeout(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """Each of the 4 rules retries once on timeout then succeeds."""
        from openai import APITimeoutError

        side_effects = []
        for _ in ALL_RULE_IDS:
            side_effects.append(APITimeoutError(request=MagicMock()))
            side_effects.append(mock_openai_response)

        mock_openai_client.responses.create = AsyncMock(side_effect=side_effects)

        with patch("app.rules.base.client", mock_openai_client), \
             patch("asyncio.sleep", new=AsyncMock()):
            for rule_id in ALL_RULE_IDS:
                rule_func = make_rule_function(rule_id)
                result = await rule_func(
                    public_remarks="test",
                    private_remarks="test",
                    prompt_data=mock_prompt_data,
                )
                assert result is not None

        # 4 rules × 2 calls each (1 fail + 1 success) = 8
        assert mock_openai_client.responses.create.call_count == 8

    @pytest.mark.asyncio
    async def test_all_rules_update_rate_limiter(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """Every rule calls rate_limiter.update_from_headers after success."""
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)

        with patch("app.rules.base.client", mock_openai_client), \
             patch("app.rules.base.get_rate_limiter") as mock_get_rl:
            mock_rl = MagicMock()
            mock_rl.estimate_tokens.return_value = 100
            mock_rl.wait_if_needed = AsyncMock()
            mock_rl.update_from_headers = AsyncMock()
            mock_get_rl.return_value = mock_rl

            for rule_id in ALL_RULE_IDS:
                rule_func = make_rule_function(rule_id)
                await rule_func(
                    public_remarks="test",
                    private_remarks="test",
                    prompt_data=mock_prompt_data,
                )

        assert mock_rl.update_from_headers.await_count == len(ALL_RULE_IDS)

    @pytest.mark.asyncio
    async def test_default_registry_functions_work_end_to_end(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """Dynamically-created rule executors for all known IDs execute successfully."""
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)

        with patch("app.rules.base.client", mock_openai_client):
            for rule_id in ALL_RULE_IDS:
                rule_func = make_rule_function(rule_id)
                result = await rule_func(
                    public_remarks="listing text",
                    private_remarks="agent notes",
                    prompt_data=mock_prompt_data,
                )
                assert "Total_tokens" in result, f"Rule {rule_id} missing Total_tokens"


# ============================================================================
# TestEdgeCases — boundary / unusual conditions
# ============================================================================

class TestEdgeCases:
    """Edge-case and boundary-condition tests."""

    @pytest.mark.asyncio
    async def test_empty_strings_for_all_fields(
        self, mock_openai_client, mock_prompt_data
    ):
        """Calling a rule with all empty strings still succeeds."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client):
            result = await execute_rule_with_prompt(
                "FAIR", {}, mock_prompt_data
            )

        assert "Total_tokens" in result

    @pytest.mark.asyncio
    async def test_very_long_text_input(self, mock_openai_client, mock_prompt_data):
        """A very long input string does not crash the executor."""
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)
        long_text = "A" * 100_000

        with patch("app.rules.base.client", mock_openai_client):
            result = await execute_rule_with_prompt(
                "FAIR", {"Remarks": long_text}, mock_prompt_data
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_model_returns_extra_keys_in_result(
        self, mock_openai_client, mock_prompt_data
    ):
        """Extra keys in the model's JSON result are preserved (pass-through)."""
        json_with_extra = """{
            "result": {
                "public_remarks": [],
                "private_agent_remarks": [],
                "directions": [], "showing_instructions": [],
                "confidential_remarks": [], "supplement_remarks": [],
                "concessions": [], "sale_factors": [],
                "extra_key": "extra_value"
            }
        }"""
        resp = _make_openai_response(json_with_extra)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client):
            result = await execute_rule_with_prompt(
                "FAIR", {"Remarks": "text"}, mock_prompt_data
            )

        assert result["extra_key"] == "extra_value"

    @pytest.mark.asyncio
    async def test_config_defaults_when_keys_missing(
        self, mock_openai_client,
    ):
        """When prompt config has missing keys, sensible defaults are used."""
        minimal_prompt_data = {
            "prompt": "Check: {{ public_remarks }}",
            "config": {},  # no model, temperature, etc.
        }
        resp = _make_openai_response(_CLEAN_RESULT_JSON)
        mock_openai_client.responses.create = AsyncMock(return_value=resp)

        with patch("app.rules.base.client", mock_openai_client):
            await execute_rule_with_prompt(
                "FAIR", {"Remarks": "text"}, minimal_prompt_data
            )

        call_kwargs = mock_openai_client.responses.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"  # default
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["top_p"] == 1.0
        assert call_kwargs["max_output_tokens"] == 6095

    @pytest.mark.asyncio
    async def test_make_rule_function_case_insensitive(
        self, mock_openai_client, mock_openai_response, mock_prompt_data
    ):
        """make_rule_function uppercases the rule_id internally."""
        mock_openai_client.responses.create = AsyncMock(return_value=mock_openai_response)
        rule_func = make_rule_function("fair")  # lowercase

        with patch("app.rules.base.client", mock_openai_client):
            result = await rule_func(
                public_remarks="test", private_remarks="test",
                prompt_data=mock_prompt_data,
            )

        assert result is not None
