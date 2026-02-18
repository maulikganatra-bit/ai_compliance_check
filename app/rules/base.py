from openai import AsyncOpenAI
from jinja2 import Template
from app.utils.utils import response_parser
from app.core.logger import rules_logger
from app.core.retry_handler import retry_with_backoff
from app.core.rate_limiter import get_rate_limiter
from app.core.config import OPENAI_API_KEY

# Client will be set from main.py during startup
# For now, create a default client (will be replaced by pooled client)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)


def set_client(new_client: AsyncOpenAI):
    """Set the global OpenAI client (called from main.py during startup)."""
    global client
    client = new_client
    rules_logger.info("OpenAI client updated with connection pool")


@retry_with_backoff(max_retries=3)
async def get_fair_housing_violation_response(
    public_remarks="",
    private_remarks="",
    directions="",
    ShowingInstructions="",
    ConfidentialRemarks="",
    SupplementRemarks="",
    Concessions="",
    SaleFactors="",
    prompt_data="",
):
    
    if prompt_data is None:
        rules_logger.error("FAIR rule called without prompt_data - this should never happen")
        raise ValueError("prompt_data is required. Prompts must be pre-loaded by routes.py before calling rule functions")
    
    rate_limiter = get_rate_limiter()
    
    try:
        # Estimate tokens and wait if needed
        combined_text = " ".join(
            [
                public_remarks or "",
                private_remarks or "",
                directions or "",
                ShowingInstructions or "",
                ConfidentialRemarks or "",
                SupplementRemarks or "",
                Concessions or "",
                SaleFactors or "",
            ]
        )
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)

        # Extract prompt and config from cached data
        prompt_template = prompt_data['prompt']
        config = prompt_data.get("config", {})

        rules_logger.debug(f"Using cached prompt for FAIR rule (version: {prompt_data.get('version', 'unknown')})")
        
        template = Template(prompt_template)
        message = template.render(
            public_remarks=public_remarks,
            directions=directions,
            showing_instructions=ShowingInstructions,
            confidential_remarks=ConfidentialRemarks,
            private_agent_remarks=private_remarks,
            supplement_remarks=SupplementRemarks,
            concessions=Concessions,
            sale_factors=SaleFactors,
        )

        # print("MESSAGE", message)

        rules_logger.debug(f"Calling OpenAI Responses API for FAIR housing rule")

        # Call OpenAI 
        response = await client.responses.create(
            model=config.get("model", "gpt-4o"),
            input=[
                {
                    "role": "system",
                    "content": message
                }
            ],
            temperature=float(config.get("temperature", "0.0")),
            max_output_tokens=int(config.get("max_output_tokens", "6095")),
            top_p=float(config.get("top_p", "1.0"))
        )
        
        # Update rate limiter with response headers
        await rate_limiter.update_from_headers(response)
        
        rules_logger.debug("FAIR housing response received from OpenAI")
        
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        
        # Map input values for checking if fields had content
        input_fields = {
            'public_remarks': public_remarks,
            'private_agent_remarks': private_remarks,
            'directions': directions,
            'showing_instructions': ShowingInstructions,
            'confidential_remarks': ConfidentialRemarks,
            'supplement_remarks': SupplementRemarks,
            'concessions': Concessions,
            'sale_factors': SaleFactors,
        }
        
        # Extract field violations with mapping
        field_mappings = {
            'public_remarks': 'Remarks',
            'private_agent_remarks': 'PrivateRemarks',
            'directions': 'Directions',
            'showing_instructions': 'ShowingInstructions',
            'confidential_remarks': 'ConfidentialRemarks',
            'supplement_remarks': 'SupplementRemarks',
            'concessions': 'Concessions',
            'sale_factors': 'SaleFactors',
        }
        
        for source_key, target_key in field_mappings.items():
            violations = json_result.pop(source_key, [])
            input_value = input_fields.get(source_key, "")
            
            if violations:
                # Violations found - check if input was empty
                if not input_value:
                    rules_logger.warning(
                        f"FAIR housing rule: Violations found in '{target_key}' but input was empty. "
                        f"This is unexpected. Excluding from result. Violations: {violations}"
                    )
                    # Don't include this field if input was empty
                else:
                    # Input was non-empty, keep violations
                    json_result[target_key] = violations
            else:
                # No violations found
                if input_value:
                    # Input was non-empty but no violations found, keep empty array
                    json_result[target_key] = []
                # If input was empty and no violations, don't include the field
        
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        rules_logger.debug(f"FAIR housing rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations")
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in get_fair_housing_violation_response: {str(e)}", exc_info=True)
        raise


@retry_with_backoff(max_retries=3)
async def get_comp_violation_response(
    public_remarks="",
    private_remarks="",
    directions="",
    ShowingInstructions="",
    ConfidentialRemarks="",
    SupplementRemarks="",
    Concessions="",
    SaleFactors="",
    prompt_data="",
):
    
    if prompt_data is None:
        rules_logger.error("COMP rule called without prompt_data - this should never happen")
        raise ValueError("prompt_data is required. Prompts must be pre-loaded by routes.py before calling rule functions")
    
    rate_limiter = get_rate_limiter()
    
    try:
        # Estimate tokens and wait if needed
        combined_text = " ".join(
            [
                public_remarks or "",
                private_remarks or "",
                directions or "",
                ShowingInstructions or "",
                ConfidentialRemarks or "",
                SupplementRemarks or "",
                Concessions or "",
                SaleFactors or "",
            ]
        )
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)

        # Extract prompt and config from cached data
        prompt_template = prompt_data['prompt']
        config = prompt_data.get("config", {})

        rules_logger.debug(f"Using cached prompt for COMP rule (version: {prompt_data.get('version', 'unknown')})")

        template = Template(prompt_template)
        message = template.render(
            public_remarks=public_remarks,
            directions=directions,
            showing_instructions=ShowingInstructions,
            confidential_remarks=ConfidentialRemarks,
            private_agent_remarks=private_remarks,
            supplement_remarks=SupplementRemarks,
            concessions=Concessions,
            sale_factors=SaleFactors,
        )

        # print("MESSAGE", message)

        rules_logger.debug(f"Calling OpenAI Responses API for COMP housing rule")

        # Call OpenAI 
        response = await client.responses.create(
            model=config.get("model", "gpt-4o"),
            input=[
                {
                    "role": "system",
                    "content": message
                }
            ],
            temperature=float(config.get("temperature", "0.0")),
            max_output_tokens=int(config.get("max_output_tokens", "6095")),
            top_p=float(config.get("top_p", "1.0"))
        )
        
        # Update rate limiter with response headers
        await rate_limiter.update_from_headers(response)
        
        rules_logger.debug("COMP response received from OpenAI")
        
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        
        # Map input values for checking if fields had content
        input_fields = {
            'public_remarks': public_remarks,
            'private_agent_remarks': private_remarks,
            'directions': directions,
            'showing_instructions': ShowingInstructions,
            'confidential_remarks': ConfidentialRemarks,
            'supplement_remarks': SupplementRemarks,
            'concessions': Concessions,
            'sale_factors': SaleFactors,
        }
        
        # Extract field violations with mapping
        field_mappings = {
            'public_remarks': 'Remarks',
            'private_agent_remarks': 'PrivateRemarks',
            'directions': 'Directions',
            'showing_instructions': 'ShowingInstructions',
            'confidential_remarks': 'ConfidentialRemarks',
            'supplement_remarks': 'SupplementRemarks',
            'concessions': 'Concessions',
            'sale_factors': 'SaleFactors',
        }
        
        for source_key, target_key in field_mappings.items():
            violations = json_result.pop(source_key, [])
            input_value = input_fields.get(source_key, "")
            
            if violations:
                # Violations found - check if input was empty
                if not input_value:
                    rules_logger.warning(
                        f"COMP rule: Violations found in '{target_key}' but input was empty. "
                        f"This is unexpected. Excluding from result. Violations: {violations}"
                    )
                    # Don't include this field if input was empty
                else:
                    # Input was non-empty, keep violations
                    json_result[target_key] = violations
            else:
                # No violations found
                if input_value:
                    # Input was non-empty but no violations found, keep empty array
                    json_result[target_key] = []
                # If input was empty and no violations, don't include the field
        
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        rules_logger.debug(f"COMP rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations")
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in get_comp_violation_response: {str(e)}", exc_info=True)
        raise


@retry_with_backoff(max_retries=3)
async def get_marketing_rule_violation_response(
    public_remarks="",
    private_remarks="",
    directions="",
    ShowingInstructions="",
    ConfidentialRemarks="",
    SupplementRemarks="",
    Concessions="",
    SaleFactors="",
    prompt_data="",
):
    
    if prompt_data is None:
        rules_logger.error("PROMO rule called without prompt_data - this should never happen")
        raise ValueError("prompt_data is required. Prompts must be pre-loaded by routes.py before calling rule functions")
    
    rate_limiter = get_rate_limiter()
    
    try:
        # Estimate tokens and wait if needed
        combined_text = " ".join(
            [
                public_remarks or "",
                private_remarks or "",
                directions or "",
                ShowingInstructions or "",
                ConfidentialRemarks or "",
                SupplementRemarks or "",
                Concessions or "",
                SaleFactors or "",
            ]
        )
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)

        # Extract prompt and config from cached data
        prompt_template = prompt_data['prompt']
        config = prompt_data.get("config", {})

        rules_logger.debug(f"Using cached prompt for PROMO rule (version: {prompt_data.get('version', 'unknown')})")

        template = Template(prompt_template)
        message = template.render(
            public_remarks=public_remarks,
            directions=directions,
            showing_instructions=ShowingInstructions,
            confidential_remarks=ConfidentialRemarks,
            private_agent_remarks=private_remarks,
            supplement_remarks=SupplementRemarks,
            concessions=Concessions,
            sale_factors=SaleFactors,
        )

        # print("MESSAGE", message)

        rules_logger.debug(f"Calling OpenAI Responses API for PROMO housing rule")

        # Call OpenAI 
        response = await client.responses.create(
            model=config.get("model", "gpt-4o"),
            input=[
                {
                    "role": "system",
                    "content": message
                }
            ],
            temperature=float(config.get("temperature", "0.0")),
            max_output_tokens=int(config.get("max_output_tokens", "6095")),
            top_p=float(config.get("top_p", "1.0"))
        )
        
        # Update rate limiter with response headers
        await rate_limiter.update_from_headers(response)
        
        rules_logger.debug("PROMO response received from OpenAI")
        
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        
        # Map input values for checking if fields had content
        input_fields = {
            'public_remarks': public_remarks,
            'private_agent_remarks': private_remarks,
            'directions': directions,
            'showing_instructions': ShowingInstructions,
            'confidential_remarks': ConfidentialRemarks,
            'supplement_remarks': SupplementRemarks,
            'concessions': Concessions,
            'sale_factors': SaleFactors,
        }
        
        # Extract field violations with mapping
        field_mappings = {
            'public_remarks': 'Remarks',
            'private_agent_remarks': 'PrivateRemarks',
            'directions': 'Directions',
            'showing_instructions': 'ShowingInstructions',
            'confidential_remarks': 'ConfidentialRemarks',
            'supplement_remarks': 'SupplementRemarks',
            'concessions': 'Concessions',
            'sale_factors': 'SaleFactors',
        }
        
        for source_key, target_key in field_mappings.items():
            violations = json_result.pop(source_key, [])
            input_value = input_fields.get(source_key, "")
            
            if violations:
                # Violations found - check if input was empty
                if not input_value:
                    rules_logger.warning(
                        f"PROMO rule: Violations found in '{target_key}' but input was empty. "
                        f"This is unexpected. Excluding from result. Violations: {violations}"
                    )
                    # Don't include this field if input was empty
                else:
                    # Input was non-empty, keep violations
                    json_result[target_key] = violations
            else:
                # No violations found
                if input_value:
                    # Input was non-empty but no violations found, keep empty array
                    json_result[target_key] = []
                # If input was empty and no violations, don't include the field
        
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        rules_logger.debug(f"PROMO rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations")
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in get_marketing_rule_violation_response: {str(e)}", exc_info=True)
        raise




@retry_with_backoff(max_retries=3)
async def get_prohibited_words_rule_violation_response(
    public_remarks="",
    private_remarks="",
    directions="",
    ShowingInstructions="",
    ConfidentialRemarks="",
    SupplementRemarks="",
    Concessions="",
    SaleFactors="",
    prompt_data="",
):
    
    if prompt_data is None:
        rules_logger.error("PRWD rule called without prompt_data - this should never happen")
        raise ValueError("prompt_data is required. Prompts must be pre-loaded by routes.py before calling rule functions")
    
    rate_limiter = get_rate_limiter()
    
    try:
        # Estimate tokens and wait if needed
        combined_text = " ".join(
            [
                public_remarks or "",
                private_remarks or "",
                directions or "",
                ShowingInstructions or "",
                ConfidentialRemarks or "",
                SupplementRemarks or "",
                Concessions or "",
                SaleFactors or "",
            ]
        )
        estimated_tokens = rate_limiter.estimate_tokens(combined_text)
        await rate_limiter.wait_if_needed(estimated_tokens)

        # Extract prompt and config from cached data
        prompt_template = prompt_data['prompt']
        config = prompt_data.get("config", {})

        rules_logger.debug(f"Using cached prompt for PRWD rule (version: {prompt_data.get('version', 'unknown')})")

        template = Template(prompt_template)
        message = template.render(
            public_remarks=public_remarks,
            directions=directions,
            showing_instructions=ShowingInstructions,
            confidential_remarks=ConfidentialRemarks,
            private_agent_remarks=private_remarks,
            supplement_remarks=SupplementRemarks,
            concessions=Concessions,
            sale_factors=SaleFactors,
        )

        # print("MESSAGE", message)

        rules_logger.debug(f"Calling OpenAI Responses API for PRWD housing rule")

        # Call OpenAI 
        response = await client.responses.create(
            model=config.get("model", "gpt-4o"),
            input=[
                {
                    "role": "system",
                    "content": message
                }
            ],
            temperature=float(config.get("temperature", "0.0")),
            max_output_tokens=int(config.get("max_output_tokens", "6095")),
            top_p=float(config.get("top_p", "1.0"))
        )
        
        # Update rate limiter with response headers
        await rate_limiter.update_from_headers(response)
        
        rules_logger.debug("PRWD housing response received from OpenAI")

        # Parse and Normalize Result
        json_content = response_parser(response.output_text)
        json_result = json_content['result']
        
        # Map input values for checking if fields had content
        input_fields = {
            'public_remarks': public_remarks,
            'private_agent_remarks': private_remarks,
            'directions': directions,
            'showing_instructions': ShowingInstructions,
            'confidential_remarks': ConfidentialRemarks,
            'supplement_remarks': SupplementRemarks,
            'concessions': Concessions,
            'sale_factors': SaleFactors,
        }
        
        # Extract field violations with mapping
        field_mappings = {
            'public_remarks': 'Remarks',
            'private_agent_remarks': 'PrivateRemarks',
            'directions': 'Directions',
            'showing_instructions': 'ShowingInstructions',
            'confidential_remarks': 'ConfidentialRemarks',
            'supplement_remarks': 'SupplementRemarks',
            'concessions': 'Concessions',
            'sale_factors': 'SaleFactors',
        }
        
        for source_key, target_key in field_mappings.items():
            violations = json_result.pop(source_key, [])
            input_value = input_fields.get(source_key, "")
            
            if violations:
                # Violations found - check if input was empty
                if not input_value:
                    rules_logger.warning(
                        f"PRWD rule: Violations found in '{target_key}' but input was empty. "
                        f"This is unexpected. Excluding from result. Violations: {violations}"
                    )
                    # Don't include this field if input was empty
                else:
                    # Input was non-empty, keep violations
                    json_result[target_key] = violations
            else:
                # No violations found
                if input_value:
                    # Input was non-empty but no violations found, keep empty array
                    json_result[target_key] = []
                # If input was empty and no violations, don't include the field
        
        json_result['Total_tokens'] = getattr(response.usage, "total_tokens", 0)
        
        rules_logger.debug(f"PRWD rule processed. Found {len(json_result.get('Remarks', []))} Remarks violations")
        return json_result
    except Exception as e:
        rules_logger.error(f"Error in get_prohibited_words_rule_violation_response: {str(e)}", exc_info=True)
        raise

