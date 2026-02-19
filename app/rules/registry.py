"""Rule registry for rule IDs and validation.

This module provides a **fully dynamic** rule system.  Adding a new rule
requires only creating the corresponding Langfuse prompt — no Python code
changes are necessary.

Exports:
    VALID_CHECK_COLUMNS  – Universal list of column names accepted in requests.
    get_rule_function()  – Returns a prompt-driven rule executor for *any* ID.

Usage:
    rule_func = get_rule_function("TESTMLS", "FAIR")
    result = await rule_func(remarks, private_remarks, directions)

    # Adding a brand-new rule:
    # 1. Create a Langfuse prompt named  NEW_RULE_violation  (and optionally
    #    MLS-specific variants like  TESTMLS_NEW_RULE_violation).
    # 2. Send a request with  {"ID": "NEW_RULE", ...}  — it just works.
    #    Prompts are loaded from Langfuse on the first request that references
    #    the rule, then cached for all subsequent requests.
"""

from app.core.logger import rules_logger
from app.rules.base import make_rule_function

# ============================================================================
# VALID CHECK COLUMNS  (universal — same for every rule)
# ============================================================================
# Column names that may appear in CheckColumns.  mlsnum and mlsId are
# mandatory on every request and are therefore excluded from this list.

VALID_CHECK_COLUMNS = [
    "Remarks",
    "PrivateRemarks",
    "Directions",
    "ShowingInstructions",
    "ConfidentialRemarks",
    "SupplementRemarks",
    "Concessions",
    "SaleFactors",
]


def get_rule_function(mls_id: str, rule_id: str):
    """Return a prompt-driven rule executor for **any** rule ID.

    The executor is created dynamically via ``make_rule_function``.  There is
    no static whitelist — if a matching Langfuse prompt exists, the rule will
    execute successfully.

    MLS-specific behaviour is implemented via Langfuse prompt naming and the
    prompt cache (custom prompt → default prompt fallback), not via Python
    custom rule modules.

    Args:
        mls_id: MLS system identifier (unused here; kept for API compat).
        rule_id: Rule identifier from RuleConfig.ID.

    Returns:
        Async function that implements the rule logic (prompt-driven).
    """
    rule_key = rule_id.upper()
    rules_logger.debug(
        f"Creating prompt-driven rule executor for rule '{rule_key}' "
        f"(mls_id='{mls_id}')"
    )
    return make_rule_function(rule_key)
