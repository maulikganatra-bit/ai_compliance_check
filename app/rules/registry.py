"""Rule registry for rule IDs and validation.

This module provides:
1. DEFAULT_RULE_FUNCTIONS - Mapping of rule IDs to generic rule executors
2. RULE_REQUIRED_COLUMNS - Validation registry for allowed columns per rule
3. get_rule_function() - Returns a rule executor (prompt-driven)

Usage:
    rule_func = get_rule_function("TESTMLS", "FAIR")
    result = await rule_func(remarks, private_remarks, directions)
"""

from app.core.logger import rules_logger

from app.rules.base import make_rule_function

# ============================================================================
# DEFAULT RULE FUNCTIONS
# ============================================================================
# Maps rule ID to corresponding default rule function
# These are used when no MLS-specific custom rule exists

DEFAULT_RULE_FUNCTIONS = {
    "FAIR": make_rule_function("FAIR"),    # Fair Housing compliance (prompt-driven)
    "COMP": make_rule_function("COMP"),    # Compensation disclosure (prompt-driven)
    "PROMO": make_rule_function("PROMO"),  # Marketing/promotional rules (prompt-driven)
    "PRWD": make_rule_function("PRWD"),    # Prohibited words rule (prompt-driven)
}

# ============================================================================
# COLUMN VALIDATION REGISTRY
# ============================================================================
# Defines which columns are allowed for each rule type
# Used to validate incoming requests (prevents invalid column names)
# Note: mlsnum and mlsId are mandatory and excluded from this registry

RULE_REQUIRED_COLUMNS = {
    "FAIR": [
        "Remarks",
        "PrivateRemarks",
        "Directions",
        "ShowingInstructions",
        "ConfidentialRemarks",
        "SupplementRemarks",
        "Concessions",
        "SaleFactors",
    ],
    "COMP": [
        "Remarks",
        "PrivateRemarks",
        "Directions",
        "ShowingInstructions",
        "ConfidentialRemarks",
        "SupplementRemarks",
        "Concessions",
        "SaleFactors",
    ],
    "PROMO": [
        "Remarks",
        "PrivateRemarks",
        "Directions",
        "ShowingInstructions",
        "ConfidentialRemarks",
        "SupplementRemarks",
        "Concessions",
        "SaleFactors",
    ],
    "PRWD": [
        "Remarks",
        "PrivateRemarks",
        "Directions",
        "ShowingInstructions",
        "ConfidentialRemarks",
        "SupplementRemarks",
        "Concessions",
        "SaleFactors",
    ],
}

def get_rule_function(mls_id: str, rule_id: str):
    """Return the prompt-driven rule executor for the given rule ID.

    MLS-specific behavior is implemented via Langfuse prompt naming and the
    prompt cache (custom prompt → default prompt fallback), not via Python
    custom rule modules.
    
    Args:
        mls_id: MLS system identifier from DataItem.mlsId (unused here; kept for API compatibility)
        rule_id: Rule identifier from RuleConfig.ID
        
    Returns:
        Async function that implements the rule logic (prompt-driven)
        
    Raises:
        ValueError: If rule_id is not in DEFAULT_RULE_FUNCTIONS
        
    Example:
        # For TESTMLS with custom FAIR rule:
        rule_func = get_rule_function("TESTMLS", "FAIR")
        # Returns: custom function from TESTMLS_FAIR.py
        
        # For ANOTHERMLS without custom FAIR rule:
        rule_func = get_rule_function("ANOTHERMLS", "FAIR")
        # Returns: default get_fair_housing_violation_response()
    """
    rule_key = rule_id.upper()
    if rule_key in DEFAULT_RULE_FUNCTIONS:
        rules_logger.debug(f"Using prompt-driven rule executor for rule '{rule_key}' (mls_id='{mls_id}')")
        return DEFAULT_RULE_FUNCTIONS[rule_key]
    
    # Neither custom nor default rule found - invalid rule_id
    rules_logger.error(f"No rule function found for rule ID '{rule_id}'")
    raise ValueError(
        f"Rule function not found for rule '{rule_id}'. "
        f"Available rules: {list(DEFAULT_RULE_FUNCTIONS.keys())}"
    )
