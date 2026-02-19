from openai import AsyncOpenAI
from jinja2 import Template
from typing import Dict, Any

from app.utils.utils import response_parser
from app.core.logger import rules_logger
from app.core.retry_handler import retry_with_backoff
from app.core.rate_limiter import get_rate_limiter
from app.core.config import OPENAI_API_KEY


# Client will be set from main.py during startup.
# For now, create a default client (will be replaced by pooled client).
client = AsyncOpenAI(api_key=OPENAI_API_KEY)


def set_client(new_client: AsyncOpenAI):
    """Set the global OpenAI client (called from main.py during startup)."""
    global client
    client = new_client
    rules_logger.info("OpenAI client updated with connection pool")


def _build_input_fields(field_values: Dict[str, str]) -> Dict[str, str]:
    """
    Normalize incoming per-field text so the prompt template and the
    response parsing logic can stay generic across all rules.
    """
    return {
        "public_remarks": field_values.get("Remarks", "") or "",
        "private_agent_remarks": field_values.get("PrivateRemarks", "") or "",
        "directions": field_values.get("Directions", "") or "",
        "showing_instructions": field_values.get("ShowingInstructions", "") or "",
        "confidential_remarks": field_values.get("ConfidentialRemarks", "") or "",
        "supplement_remarks": field_values.get("SupplementRemarks", "") or "",
        "concessions": field_values.get("Concessions", "") or "",
        "sale_factors": field_values.get("SaleFactors", "") or "",
    }


def _map_result_fields(
    json_result: Dict[str, Any],
    input_fields: Dict[str, str],
    rule_id: str,
) -> Dict[str, Any]:
    """
    Map model output keys back to API response keys and enforce the
    "only include fields that had input" rule. This is shared by all rules.
    """
    field_mappings = {
        "public_remarks": "Remarks",
        "private_agent_remarks": "PrivateRemarks",
        "directions": "Directions",
        "showing_instructions": "ShowingInstructions",
        "confidential_remarks": "ConfidentialRemarks",
        "supplement_remarks": "SupplementRemarks",
        "concessions": "Concessions",
        "sale_factors": "SaleFactors",
    }

    for source_key, target_key in field_mappings.items():
        violations = json_result.pop(source_key, [])
        input_value = input_fields.get(source_key, "")

        if violations:
            if not input_value:
                rules_logger.warning(
                    f"{rule_id} rule: Violations found in '{target_key}' but input was empty. "
                    f"Excluding from result. Violations: {violations}"
                )
            else:
                json_result[target_key] = violations
        else:
            if input_value:
                json_result[target_key] = []

    return json_result


@retry_with_backoff(max_retries=3)
async def execute_rule_with_prompt(
    rule_id: str,
    field_values: Dict[str, str],
    prompt_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generic executor for all rules.

    The caller (routes layer) is responsible for:
    - Selecting which text fields to include based on CheckColumns.
    - Providing the pre-loaded prompt_data from the cache.

    This function:
    - Estimates tokens and cooperates with the DynamicRateLimiter.
    - Renders the Langfuse prompt template with standard variables.
    - Calls OpenAI Responses API.
    - Normalizes / maps the JSON result back to API field names.
    """
    if prompt_data is None:
        rules_logger.error(f"{rule_id} rule called without prompt_data - this should never happen")
        raise ValueError(
            "prompt_data is required. Prompts must be pre-loaded by routes.py before calling rule functions"
        )

    rate_limiter = get_rate_limiter()

    try:
        input_fields = _build_input_fields(field_values)

        combined_text = " ".join(input_fields.values())
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)

        prompt_template = prompt_data["prompt"]
        config = prompt_data.get("config", {})

        rules_logger.debug(
            f"Using cached prompt for {rule_id} rule (version: {prompt_data.get('version', 'unknown')})"
        )

        template = Template(prompt_template)
        message = template.render(**input_fields)

        rules_logger.debug(f"Calling OpenAI Responses API for {rule_id} rule")

        response = await client.responses.create(
            model=config.get("model", "gpt-4o"),
            input=[
                {
                    "role": "system",
                    "content": message,
                }
            ],
            temperature=float(config.get("temperature", "0.0")),
            max_output_tokens=int(config.get("max_output_tokens", "6095")),
            top_p=float(config.get("top_p", "1.0")),
        )

        await rate_limiter.update_from_headers(response)

        rules_logger.debug(f"{rule_id} response received from OpenAI")

        json_content = response_parser(response.output_text)
        if not json_content or "result" not in json_content:
            rules_logger.error(
                f"{rule_id} rule: Unable to parse JSON result from model output: {json_content}"
            )
            raise ValueError(f"{rule_id} rule: invalid model output format")

        json_result = json_content["result"]

        json_result = _map_result_fields(json_result, input_fields, rule_id)

        json_result["Total_tokens"] = getattr(response.usage, "total_tokens", 0)

        rules_logger.debug(
            f"{rule_id} rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations"
        )
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in execute_rule_with_prompt for {rule_id}: {str(e)}", exc_info=True)
        raise


def make_rule_function(rule_id: str):
    """
    Backwards-compatible adapter for the previous per-rule function signatures.

    This allows `routes.py` to keep calling a "rule function" that accepts
    public/private remarks etc, while all logic flows through the generic
    prompt-driven executor.
    """
    rule_id_upper = rule_id.upper()

    async def _rule_func(
        public_remarks="",
        private_remarks="",
        directions="",
        ShowingInstructions="",
        ConfidentialRemarks="",
        SupplementRemarks="",
        Concessions="",
        SaleFactors="",
        prompt_data=None,
    ):
        field_values = {
            "Remarks": public_remarks,
            "PrivateRemarks": private_remarks,
            "Directions": directions,
            "ShowingInstructions": ShowingInstructions,
            "ConfidentialRemarks": ConfidentialRemarks,
            "SupplementRemarks": SupplementRemarks,
            "Concessions": Concessions,
            "SaleFactors": SaleFactors,
        }
        return await execute_rule_with_prompt(rule_id_upper, field_values, prompt_data)

    _rule_func.__name__ = f"execute_{rule_id_upper.lower()}_rule"
    return _rule_func

