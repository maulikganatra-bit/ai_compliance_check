"""Rule registry for dynamic rule loading and validation.

This module provides:
1. DEFAULT_RULE_FUNCTIONS - Mapping of rule IDs to default rule functions
2. RULE_REQUIRED_COLUMNS - Validation registry for allowed columns per rule
3. load_custom_rule() - Dynamically loads MLS-specific custom rules
4. get_rule_function() - Returns appropriate rule function (custom > default)

Custom Rule System:
- Custom rules are loaded from app/rules/custom_rules/{mls_id}_{rule_id}.py
- Example: TESTMLS_FAIR.py for Fair Housing rule specific to TESTMLS
- If custom rule not found, falls back to default rule
- Custom rules must define an async function

Usage:
    rule_func = get_rule_function("TESTMLS", "FAIR")
    result = await rule_func(remarks, private_remarks, directions)
"""

import importlib
import inspect
from pathlib import Path
from app.core.logger import rules_logger

# Import default rule functions from base.py
from app.rules.base import (
    get_fair_housing_violation_response,
    get_comp_violation_response,
    get_marketing_rule_violation_response
)

# ============================================================================
# DEFAULT RULE FUNCTIONS
# ============================================================================
# Maps rule ID to corresponding default rule function
# These are used when no MLS-specific custom rule exists

DEFAULT_RULE_FUNCTIONS = {
    "FAIR": get_fair_housing_violation_response,   # Fair Housing compliance
    "COMP": get_comp_violation_response,           # Compensation disclosure
    "PROMO": get_marketing_rule_violation_response, # Marketing/promotional rules
}

# ============================================================================
# COLUMN VALIDATION REGISTRY
# ============================================================================
# Defines which columns are allowed for each rule type
# Used to validate incoming requests (prevents invalid column names)
# Note: mlsnum and mls_id are mandatory and excluded from this registry

RULE_REQUIRED_COLUMNS = {
    "FAIR": ["Remarks", "PrivateRemarks", "Directions"],
    "COMP": ["Remarks", "PrivateRemarks", "Directions"],
    "PROMO": ["Remarks", "PrivateRemarks", "Directions"],
}

def load_custom_rule(mls_id: str, rule_id: str):
    """Dynamically load MLS-specific custom rule function.
    
    Attempts to import a custom rule module following the naming pattern:
    app/rules/custom_rules/{mls_id}_{rule_id}.py
    
    Example:
        MLS ID: "TESTMLS", Rule ID: "FAIR"
        → Looks for: app/rules/custom_rules/TESTMLS_FAIR.py
        → Finds first async function in module
    
    Args:
        mls_id: MLS system identifier (e.g., "TESTMLS", "ANOTHERMLS")
        rule_id: Rule identifier ("FAIR", "COMP", "PROMO")
        
    Returns:
        Async function from custom module, or None if not found
        
    How to create custom rule:
        1. Create file: app/rules/custom_rules/TESTMLS_FAIR.py
        2. Define async function:
           async def check_fair_housing_testmls(public_remarks, private_remarks, directions):
               # Custom logic here
               return {"Remarks": [...], "PrivateRemarks": [...], "Total_tokens": 100}
        3. System will auto-detect and use it for TESTMLS + FAIR combination
    """
    try:
        # Construct module name: TESTMLS_FAIR
        module_name = f"{mls_id}_{rule_id}"
        # Full import path: app.rules.custom_rules.TESTMLS_FAIR
        module_path = f"app.rules.custom_rules.{module_name}"
        
        rules_logger.debug(f"Attempting to load custom rule module: {module_path}")
        
        # Try to import the custom module dynamically
        module = importlib.import_module(module_path)
        
        # Look for an async function in the module
        # Convention: First public async function found is used
        for name, obj in inspect.getmembers(module):
            if inspect.iscoroutinefunction(obj) and not name.startswith('_'):
                rules_logger.info(f"Loaded custom rule function '{name}' from {module_path}")
                return obj
        
        # Module found but no async function
        rules_logger.warning(f"No async function found in custom module {module_path}")
        return None
        
    except ModuleNotFoundError:
        # No custom module exists (normal case, fall back to default)
        rules_logger.debug(f"No custom rule module found for {mls_id}_{rule_id}")
        return None
    except Exception as e:
        # Unexpected error (syntax error, import error, etc.)
        rules_logger.error(f"Error loading custom rule {mls_id}_{rule_id}: {str(e)}", exc_info=True)
        return None

def get_rule_function(mls_id: str, rule_id: str):
    """Get the appropriate rule function for given MLS and rule ID.
    
    Priority:
    1. Custom rule from custom_rules/{mls_id}_{rule_id}.py (if exists)
    2. Default rule from DEFAULT_RULE_FUNCTIONS[rule_id] (fallback)
    
    This allows MLS-specific customization while maintaining default behavior.
    
    Args:
        mls_id: MLS system identifier from DataItem.mls_id
        rule_id: Rule identifier from RuleConfig.ID
        
    Returns:
        Async function that implements the rule logic
        
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
    # Try to load custom rule first (MLS-specific)
    custom_func = load_custom_rule(mls_id, rule_id)
    if custom_func:
        rules_logger.debug(f"Using custom rule function for MLS '{mls_id}' and rule '{rule_id}'")
        return custom_func
    
    # Fall back to default rule (generic)
    if rule_id in DEFAULT_RULE_FUNCTIONS:
        rules_logger.debug(f"Using default rule function for rule '{rule_id}'")
        return DEFAULT_RULE_FUNCTIONS[rule_id]
    
    # Neither custom nor default rule found - invalid rule_id
    rules_logger.error(f"No rule function found for rule ID '{rule_id}'")
    raise ValueError(
        f"Rule function not found for rule '{rule_id}'. "
        f"Available rules: {list(DEFAULT_RULE_FUNCTIONS.keys())}"
    )
