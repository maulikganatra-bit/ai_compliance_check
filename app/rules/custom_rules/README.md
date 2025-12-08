# Custom Rules Directory

This directory contains MLS-specific custom rule implementations.

## File Naming Convention

Custom rule files must follow this naming pattern:
```
{MLS_ID}_{RULE_ID}.py
```

**Examples:**
- `TESTMLS_FAIR.py` - Custom FAIR rule for TESTMLS
- `CRMLS_COMP.py` - Custom COMP rule for CRMLS
- `NWMLS_PROMO.py` - Custom PROMO rule for NWMLS

## How to Create a Custom Rule

1. **Create a new Python file** with the naming convention above
2. **Import required dependencies** (AsyncOpenAI, response_parser, logger, etc.)
3. **Define at least one async function** that accepts:
   - `public_remarks` (str)
   - `private_remarks` (str)
   - `directions` (str, optional)
4. **Return a dict** with structure:
   ```python
   {
       "Remarks": [...],          # List of violations found in Remarks
       "PrivateRemarks": [...],   # List of violations found in PrivateRemarks
       "Total_tokens": int        # Token usage
   }
   ```

## Example Custom Rule

```python
from openai import AsyncOpenAI
from app.utils.utils import response_parser
from app.core.logger import rules_logger

client = AsyncOpenAI()

async def custom_rule_checker(public_remarks, private_remarks, directions=None):
    """Custom implementation for specific MLS"""
    try:
        rules_logger.debug("Using custom rule logic")
        
        # Your custom logic here
        response = await client.responses.create(
            prompt={
                "id": "your_prompt_id",
                "variables": {
                    "public_remarks": public_remarks or "",
                    "private_agent_remarks": private_remarks or ""
                }
            }
        )
        
        # Parse and format response
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        json_result['Remarks'] = json_result.pop('public_remarks', [])
        json_result['PrivateRemarks'] = json_result.pop('private_agent_remarks', [])
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        return json_result
        
    except Exception as e:
        rules_logger.error(f"Error in custom rule: {str(e)}", exc_info=True)
        raise
```

## How It Works

The system automatically:
1. Checks for custom rule file `{mls_id}_{rule_id}.py` in this directory
2. Dynamically imports the module if found
3. Uses the first async function defined in the module
4. Falls back to default rule if no custom rule exists

## Priority Order

1. **Custom rule** from `custom_rules/{MLS_ID}_{RULE_ID}.py` (if exists)
2. **Default rule** from `app/rules/base.py` (fallback)

## Logs

Custom rule loading is logged with:
- `DEBUG`: Attempting to load custom module
- `INFO`: Successfully loaded custom rule function
- `WARNING`: Custom module found but no async function
- `ERROR`: Error loading custom rule
