from openai import AsyncOpenAI
from app.utils.utils import response_parser
from app.core.logger import rules_logger
from app.core.retry_handler import retry_with_backoff
from app.core.rate_limiter import get_rate_limiter
from dotenv import load_dotenv
load_dotenv()

# Client will be set from main.py during startup
# For now, create a default client (will be replaced by pooled client)
client = AsyncOpenAI()


def set_client(new_client: AsyncOpenAI):
    """Set the global OpenAI client (called from main.py during startup)."""
    global client
    client = new_client
    rules_logger.info("OpenAI client updated with connection pool")

@retry_with_backoff(max_retries=3)
async def get_fair_housing_violation_response(public_remarks, private_remarks, directions=None):
    rate_limiter = get_rate_limiter()
    
    try:
        # Estimate tokens and wait if needed
        combined_text = f"{public_remarks or ''} {private_remarks or ''}"
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)
        
        rules_logger.debug("Calling OpenAI Responses API for FAIR housing rule")
        response = await client.responses.create(
            prompt={
                "id": "pmpt_68c29d3553688193b6d064d556ebc3c7039d675dbb8aefa0",
                "variables": {
                    "public_remarks": public_remarks or "",
                    "private_agent_remarks": private_remarks or ""
                }
            }
        )
        
        # Update rate limiter with response headers
        await rate_limiter.update_from_headers(response)
        
        rules_logger.debug("FAIR housing response received from OpenAI")
        
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        json_result['Remarks'] = json_result.pop('public_remarks', [])
        json_result['PrivateRemarks'] = json_result.pop('private_agent_remarks', [])
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        rules_logger.debug(f"FAIR housing rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations")
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in get_fair_housing_violation_response: {str(e)}", exc_info=True)
        raise


@retry_with_backoff(max_retries=3)
async def get_comp_violation_response(public_remarks, private_remarks, directions=None):
    rate_limiter = get_rate_limiter()
    
    try:
        # Estimate tokens and wait if needed
        combined_text = f"{public_remarks or ''} {private_remarks or ''}"
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)
        
        rules_logger.debug("Calling OpenAI Responses API for COMP rule")
        response = await client.responses.create(
            prompt={
                "id": "pmpt_6908794dae1c8195a2902ca8e69120d609db2ac6e42d0716",
                
                "variables": {
                    "public_remarks": public_remarks or "",
                    "private_agent_remarks": private_remarks or ""
                }
            }
        )
        
        # Update rate limiter with response headers
        await rate_limiter.update_from_headers(response)
        
        rules_logger.debug("COMP response received from OpenAI")
        
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        json_result['Remarks'] = json_result.pop('public_remarks', [])
        json_result['PrivateRemarks'] = json_result.pop('private_agent_remarks', [])
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        rules_logger.debug(f"COMP rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations")
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in get_comp_violation_response: {str(e)}", exc_info=True)
        raise


@retry_with_backoff(max_retries=3)
async def get_marketing_rule_violation_response(public_remarks, private_remarks, directions=None):
    rate_limiter = get_rate_limiter()
    
    try:
        # Estimate tokens and wait if needed
        combined_text = f"{public_remarks or ''} {private_remarks or ''}"
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)
        
        rules_logger.debug("Calling OpenAI Responses API for PROMO rule")
        response = await client.responses.create(
            prompt={
                "id": "pmpt_692458777bf08196abfd60b7c31d760e0eeb936b11d480f6",
                
                "variables": {
                    "public_remarks": public_remarks or "",
                    "private_agent_remarks": private_remarks or ""
                }
            }
        )
        
        # Update rate limiter with response headers
        await rate_limiter.update_from_headers(response)
        
        rules_logger.debug("PROMO response received from OpenAI")
        
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        json_result['Remarks'] = json_result.pop('public_remarks', [])
        json_result['PrivateRemarks'] = json_result.pop('private_agent_remarks', [])
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        rules_logger.debug(f"PROMO rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations")
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in get_marketing_rule_violation_response: {str(e)}", exc_info=True)
        raise
