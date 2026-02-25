from fastapi import APIRouter, HTTPException, Request, Depends
from app.models.models import (
    ComplianceRequest, APIResponse, DataItem, PromptValidationRequest
)
from app.rules.registry import VALID_CHECK_COLUMNS
from app.rules.registry import get_rule_function
from app.core.logger import api_logger
from app.core.rate_limiter import get_rate_limiter
from app.auth.dependencies import verify_authentication
from app.core.prompt_cache import get_prompt_manager
from typing import Dict, Union, Any, Optional
import asyncio
import time
import inspect

router = APIRouter()

@router.post("/check_compliance", response_model=APIResponse)
async def check_compliance(
    compliance_request: ComplianceRequest, 
    request: Request,
    auth_info: Dict[str, Union[str, object]] = Depends(verify_authentication)
):
    request_id = request.state.request_id
    
    # Log request with appropriate authentication info
    if auth_info["auth_type"] == "jwt":
        api_logger.info(f"Compliance check request from user '{auth_info['username']}' with {len(compliance_request.Data)} records")
    else:
        api_logger.info(f"Compliance check request from service '{auth_info['client']}' with {len(compliance_request.Data)} records")
    api_logger.debug(f"Rules to check: {[rule.ID for rule in compliance_request.AIViolationID]}")

    # Log full request payload (truncate long text fields for readability)
    api_logger.debug(
        "Full request payload - AIViolationID: "
        f"{[{'ID': r.ID, 'mlsId': r.mlsId, 'CheckColumns': r.CheckColumns} for r in compliance_request.AIViolationID]}"
    )
    api_logger.debug(
        "Full request payload - Data records: "
        f"{[{'mlsnum': d.mlsnum, 'mlsId': d.mlsId, 'Remarks': (d.Remarks or '')[:200], 'PrivateRemarks': (d.PrivateRemarks or '')[:200], 'Directions': (d.Directions or '')[:200], 'ShowingInstructions': (d.ShowingInstructions or '')[:200], 'ConfidentialRemarks': (d.ConfidentialRemarks or '')[:200], 'SupplementRemarks': (d.SupplementRemarks or '')[:200], 'Concessions': (d.Concessions or '')[:200], 'SaleFactors': (d.SaleFactors or '')[:200]} for d in compliance_request.Data]}"
    )
    
    if not compliance_request.Data:
        api_logger.warning("Empty data list received")
        raise HTTPException(status_code=400, detail="Empty data list")
    
    # Validate rule IDs and build MLS-scoped rule lookup
    
    # Validate each rule has a valid mlsId
    for rule in compliance_request.AIViolationID:
        if not rule.mlsId:
            api_logger.error(f"Missing mlsId for rule {rule.ID}")
            raise HTTPException(
                status_code=400, 
                detail=f"Rule {rule.ID} is missing required 'mlsId' field"
            )
    
    # Validate CheckColumns against VALID_CHECK_COLUMNS (universal for all rules)
    for rule in compliance_request.AIViolationID:
        rule_id = rule.ID
        check_columns = rule.columns_list()
        
        invalid_check_columns = [col for col in check_columns if col not in VALID_CHECK_COLUMNS]
        if invalid_check_columns:
            api_logger.error(f"Invalid CheckColumns for rule {rule_id}: {invalid_check_columns}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid CheckColumns for rule '{rule_id}': {invalid_check_columns}. Valid columns are: {VALID_CHECK_COLUMNS}"
            )
    
    # Build MLS-scoped rule lookup: (ID, mlsId) -> [columns]
    # For duplicate (ID, mlsId) pairs, merge columns (union)
    mls_rules_map = {}  # Key: (rule_id, mls_id), Value: set of columns
    for rule in compliance_request.AIViolationID:
        key = (rule.ID, rule.mlsId)
        columns = set(rule.columns_list())
        if key in mls_rules_map:
            # Merge columns if duplicate rule entry
            mls_rules_map[key].update(columns)
            api_logger.debug(f"Merged duplicate rule entry for {key}: {mls_rules_map[key]}")
        else:
            mls_rules_map[key] = columns
    
    # Validate Data records: ensure each record has required columns for its mlsId
    for idx, record in enumerate(compliance_request.Data):
        record_mls_id = record.mlsId
        record_fields = set(record.model_dump(exclude_unset=True).keys()) - {"mlsnum", "mlsId"}
        
        # Find all rules applicable to this record's mlsId
        applicable_rules = {k: v for k, v in mls_rules_map.items() if k[1] == record_mls_id}
        
        if not applicable_rules:
            api_logger.error(f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) has no matching rules")
            raise HTTPException(
                status_code=400,
                detail=f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) has no matching rules. Available mlsIds in rules: {list(set(k[1] for k in mls_rules_map.keys()))}"
            )
        
        # Collect all required columns for this record
        required_columns = set()
        for (rule_id, mls_id), columns in applicable_rules.items():
            required_columns.update(columns)
        
        # Check for missing required columns
        missing_columns = required_columns - record_fields
        if missing_columns:
            api_logger.error(f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) missing required columns: {missing_columns}")
            raise HTTPException(
                status_code=400,
                detail=f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) missing required columns: {list(missing_columns)}. Required: {list(required_columns)}"
            )

    api_logger.info("Validation completed successfully")

    # Fetch all required prompts fresh from Langfuse
    api_logger.info("Fetching prompts from Langfuse...")
    prompt_manager = get_prompt_manager()

    # Get all unique (rule_id, mls_id) pairs
    rule_mls_pairs = list(mls_rules_map.keys())

    try:
        # Fetch prompts concurrently from Langfuse (no cache — always fresh)
        prompts_map = await prompt_manager.load_batch_prompts(rule_mls_pairs)

        # CRITICAL: Check for missing prompts and raise error
        # Since prompt_data is REQUIRED in rule functions, we must have prompts
        missing_prompts = []
        for pair, prompt in prompts_map.items():
            if prompt is None:
                missing_prompts.append(pair)

        if missing_prompts:
            api_logger.warning(f"Missing prompts for: {missing_prompts}")
            missing_details = [
                f"'{rule_id}' (mls_id='{mls_id}')" for rule_id, mls_id in missing_prompts
            ]
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No Langfuse prompts found for: {', '.join(missing_details)}. "
                    f"To add a new rule, create a Langfuse prompt named "
                    f"'<RULE_ID>_violation' (default) or '<MLS_ID>_<RULE_ID>_violation' "
                    f"(MLS-specific)."
                )
            )
        
        loaded_count = sum(1 for p in prompts_map.values() if p is not None)
        api_logger.info(f"Loaded {loaded_count}/{len(rule_mls_pairs)} prompts from cache")
    
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"Error loading prompts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load prompts from Langfuse: {str(e)}"
        )

    
    try:
        # Pass the generated request_id and MLS-scoped rules map into processing
        request_id = getattr(request.state, 'request_id', None)
        result = await process_all_records(compliance_request, mls_rules_map=mls_rules_map, prompts_map=prompts_map, request_id=request_id)
        api_logger.info(f"Compliance check completed successfully. Total tokens: {result.total_tokens}, Elapsed time: {result.elapsed_time:.2f}s")
        return result
    except Exception as e:
        api_logger.error(f"Error during compliance check: {str(e)}", exc_info=True)
        raise

async def process_single_rule(record: DataItem, rule_id: str, columns: list, mls_id: str, prompt_data: Optional[Dict[str,Any]]):
    """
    Process a single rule for a record (used for parallel execution).
    
    Args:
        record: Data record to process
        rule_id: Rule identifier (FAIR, COMP, PROMO, PRWD)
        columns: List of columns to check for this rule
        mls_id: MLS identifier
        prompt_data: Pre-loaded prompt data from cache
        
    Returns:
        Tuple of (rule_id, result_dict, tokens_used)
    """
    # Validate that prompt_data was provided
    if prompt_data is None:
        error_msg = f"prompt_data is None for rule {rule_id}, MLS {mls_id}. This should never happen."
        api_logger.error(error_msg)
        return (rule_id.upper(), {
            "Remarks": [],
            "PrivateRemarks": [],
            "Directions": [],
            "ShowingInstructions": [],
            "ConfidentialRemarks": [],
            "SupplementRemarks": [],
            "Concessions": [],
            "SaleFactors": [],
            "error": error_msg
        }, 0)

    public_remarks = record.Remarks if "Remarks" in columns else ""
    private_remarks = record.PrivateRemarks if "PrivateRemarks" in columns else ""
    directions = record.Directions if "Directions" in columns else ""
    ShowingInstructions = record.ShowingInstructions if "ShowingInstructions" in columns else ""
    ConfidentialRemarks = record.ConfidentialRemarks if "ConfidentialRemarks" in columns else ""
    SupplementRemarks = record.SupplementRemarks if "SupplementRemarks" in columns else ""
    Concessions = record.Concessions if "Concessions" in columns else ""
    SaleFactors = record.SaleFactors if "SaleFactors" in columns else ""
    
    try:
        api_logger.debug(f"Applying rule {rule_id} to record {record.mlsnum}")
        rule_func = get_rule_function(mls_id, rule_id)

        # Pass only arguments that the rule function accepts to keep custom rules compatible
        candidate_args = {
            "public_remarks": public_remarks,
            "private_remarks": private_remarks,
            "directions": directions,
            "ShowingInstructions": ShowingInstructions,
            "ConfidentialRemarks": ConfidentialRemarks,
            "SupplementRemarks": SupplementRemarks,
            "Concessions": Concessions,
            "SaleFactors": SaleFactors,
            "prompt_data": prompt_data,
        }

        # Pass only arguments that the rule function accepts
        accepted_params = set(inspect.signature(rule_func).parameters.keys())
        call_kwargs = {k: v for k, v in candidate_args.items() if k in accepted_params}

        # Call rule function
        result = await rule_func(**call_kwargs)
        tokens_used = result.get("Total_tokens", 0)
        
        api_logger.debug(f"Rule {rule_id} completed for {record.mlsnum}. Tokens: {tokens_used}")
        return (rule_id.upper(), result, tokens_used)
    
    except Exception as e:
        api_logger.error(f"Error applying rule {rule_id} to record {record.mlsnum}: {str(e)}", exc_info=True)
        return (rule_id.upper(), {
            "Remarks": [],
            "PrivateRemarks": [],
            "Directions": [],
            "ShowingInstructions": [],
            "ConfidentialRemarks": [],
            "SupplementRemarks": [],
            "Concessions": [],
            "SaleFactors": [],
            "error": str(e)
        }, 0)



async def process_record(record: DataItem, mls_rules_map: Dict, prompts_map: Dict, semaphore: asyncio.Semaphore):
    """
    Process all rules for a single record in parallel.
    
    Args:
        record: Data record to process
        mls_rules_map: Dictionary mapping (rule_id, mls_id) -> set of columns
        prompts_map: Dictionary mapping (rule_id, mls_id) -> prompts data
        semaphore: Semaphore for concurrency control
        
    Returns:
        Dictionary with results for all rules
    """
    async with semaphore:
        start_time = time.time()
        mlsnum = record.mlsnum
        mls_id = record.mlsId
        record_result = {"mlsnum": mlsnum, "mlsId": mls_id}
        
        # Filter rules applicable to this record's mlsId
        applicable_rules = {k[0]: list(v) for k, v in mls_rules_map.items() if k[1] == mls_id}
        
        api_logger.debug(f"Processing record {mlsnum} from MLS {mls_id} with {len(applicable_rules)} rules in parallel")
        
        # Execute ALL applicable rules in parallel for this record
        rule_tasks = []
        for rule_id, columns in applicable_rules.items():
            # Get pre-loaded prompt for this rule
            prompt_key = (rule_id, mls_id)
            prompt_data = prompts_map.get(prompt_key)

            rule_tasks.append(process_single_rule(record, rule_id, columns, mls_id, prompt_data))
        
        # Wait for all rules to complete
        rule_results = await asyncio.gather(*rule_tasks, return_exceptions=True)
        # Aggregate results
        total_tokens = 0
        for result in rule_results:
            if isinstance(result, tuple):
                rule_id_upper, rule_result, tokens_used = result
                record_result[rule_id_upper] = rule_result
                total_tokens += tokens_used
            elif isinstance(result, Exception):
                api_logger.error(f"Exception in rule processing for {mlsnum}: {str(result)}")
        
        # Set rule to null if all field arrays are empty (no violations detected)
        for rule_id_upper in list(record_result.keys()):
            if rule_id_upper not in ["mlsnum", "mlsId", "latency", "tokens_used"]:
                rule_data = record_result[rule_id_upper]
                if isinstance(rule_data, dict):
                    # Check if all field arrays are empty
                    all_empty = True
                    for field_key, field_value in rule_data.items():
                        # Skip metadata fields like Total_tokens, error
                        if field_key not in ["Total_tokens", "error"] and isinstance(field_value, list):
                            if len(field_value) > 0:
                                all_empty = False
                                break
                    
                    # If all field arrays are empty, set rule to null
                    if all_empty:
                        record_result[rule_id_upper] = None
                        api_logger.debug(f"Rule {rule_id_upper} set to null for {mlsnum} (no violations detected)")
        
        latency = time.time() - start_time
        record_result["latency"] = latency
        record_result["tokens_used"] = total_tokens

        api_logger.debug(f"Record {mlsnum} processed in {latency:.2f}s with {total_tokens} tokens ({len(applicable_rules)} rules in parallel)")
        return record_result


async def process_all_records(request: ComplianceRequest, mls_rules_map: Dict, prompts_map: Dict, request_id: str = None):
    """
    Process all records with dynamic concurrency based on rate limits.
    
    Args:
        request: ComplianceRequest with data and rules
        mls_rules_map: Dictionary mapping (rule_id, mls_id) -> set of columns
        prompts_map: Dictionary mapping (rule_id, mls_id) -> prompt data
        request_id: Optional request ID for tracing
        
    Returns:
        APIResponse with results
    """
    rate_limiter = get_rate_limiter()
    start_time = time.time()
    
    # Count unique rule IDs across all mlsIds
    unique_rule_ids = set(k[0] for k in mls_rules_map.keys())
    total_api_calls = len(request.Data) * len(unique_rule_ids)
    
    api_logger.info(
        f"Starting batch processing: {len(request.Data)} records × {len(unique_rule_ids)} unique rules = "
        f"{total_api_calls} API calls (MLS-scoped)"
    )
    api_logger.debug(f"MLS-scoped rules configuration: {mls_rules_map}")

    # Log prompt loading status
    prompts_loaded = sum(1 for p in prompts_map.values() if p is not None)
    api_logger.info(f"Using {prompts_loaded}/{len(mls_rules_map)} pre-loaded prompts")
    
    # Get initial safe concurrency from rate limiter
    initial_concurrency = rate_limiter.get_safe_concurrency()
    api_logger.info(f"Initial concurrency: {initial_concurrency}")
    
    semaphore = asyncio.Semaphore(initial_concurrency)
    
    # Create tasks for all records
    api_logger.info(f"Creating tasks for {len(request.Data)} records (parallel rule execution enabled)")
    tasks = [process_record(record, mls_rules_map, prompts_map, semaphore) for record in request.Data]
    
    # Process with dynamic concurrency adjustment
    results = []
    chunk_size = 100  # Process in chunks to allow concurrency adjustment
    
    for i in range(0, len(tasks), chunk_size):
        chunk = tasks[i:i + chunk_size]
        chunk_num = i // chunk_size + 1
        total_chunks = (len(tasks) + chunk_size - 1) // chunk_size
        
        api_logger.info(f"Processing chunk {chunk_num}/{total_chunks} ({len(chunk)} records)")
        
        # Check and adjust concurrency before each chunk
        new_concurrency = rate_limiter.get_safe_concurrency()
        if new_concurrency != semaphore._value:
            api_logger.info(f"Adjusting concurrency: {semaphore._value} → {new_concurrency}")
            semaphore = asyncio.Semaphore(new_concurrency)
            # Update semaphore for remaining tasks
            for task_idx in range(i, len(tasks)):
                # Note: Existing tasks keep their semaphore, new chunks get updated one
                pass
        
        chunk_results = await asyncio.gather(*chunk, return_exceptions=True)
        results.extend(chunk_results)
        
        # Log progress
        completed = min(i + chunk_size, len(tasks))
        progress_pct = (completed / len(tasks)) * 100
        elapsed_so_far = time.time() - start_time
        api_logger.info(f"Progress: {completed}/{len(tasks)} records ({progress_pct:.1f}%) in {elapsed_so_far:.1f}s")
    
    # Calculate final statistics
    total_tokens = sum(r["tokens_used"] for r in results if isinstance(r, dict))
    elapsed = time.time() - start_time
    clean_results = [r for r in results if isinstance(r, dict)]
    
    error_count = len(results) - len(clean_results)
    if error_count > 0:
        api_logger.warning(f"Batch processing completed with {error_count} errors out of {len(results)} records")
    else:
        api_logger.info(f"Batch processing completed successfully. Processed {len(clean_results)} records in {elapsed:.2f}s")
    
    # Log performance metrics
    avg_time_per_record = elapsed / len(request.Data) if request.Data else 0
    records_per_second = len(request.Data) / elapsed if elapsed > 0 else 0
    api_logger.info(
        f"Performance metrics - Total tokens: {total_tokens:,}, Elapsed: {elapsed:.2f}s, "
        f"Avg time/record: {avg_time_per_record:.2f}s, Throughput: {records_per_second:.1f} records/s"
    )

    # Log rate limiter stats
    limiter_stats = rate_limiter.get_stats()
    api_logger.info(f"Rate limiter stats: {limiter_stats}")
    
    return APIResponse(
        ok=200,
        results=clean_results,
        request_id=request_id,
        error_message="",
        total_tokens=total_tokens,
        elapsed_time=elapsed
    )

@router.post("/validate_prompt_response", response_model=APIResponse)
async def validate_prompt_response(
    validation_request: PromptValidationRequest,
    request: Request,
    auth_info: Dict[str, Union[str, object]] = Depends(verify_authentication)
):
    """
    Validate compliance with a specific prompt version.
    
    Similar to /check_compliance but allows testing against a specific prompt version
    instead of always using the latest. Useful for regression testing and validating
    prompt changes.
    
    Args:
        validation_request: PromptValidationRequest (same as ComplianceRequest + prompt_version)
        request: FastAPI request object (provides request_id)
        auth_info: Authentication info from verify_authentication
        
    Returns:
        APIResponse with results (identical structure to /check_compliance)
    """
    request_id = request.state.request_id
    
    # Log request with appropriate authentication info
    if auth_info["auth_type"] == "jwt":
        api_logger.info(f"Prompt validation request from user '{auth_info['username']}' with {len(validation_request.Data)} records (prompt_version={validation_request.prompt_version})")
    else:
        api_logger.info(f"Prompt validation request from service '{auth_info['client']}' with {len(validation_request.Data)} records (prompt_version={validation_request.prompt_version})")
    api_logger.debug(f"Rules to check: {[rule.ID for rule in validation_request.AIViolationID]}")
    
    if not validation_request.Data:
        api_logger.warning("Empty data list received")
        raise HTTPException(status_code=400, detail="Empty data list")
    
    # Validate CheckColumns against VALID_CHECK_COLUMNS
    for rule in validation_request.AIViolationID:
        rule_id = rule.ID
        check_columns = rule.columns_list()
        
        invalid_check_columns = [col for col in check_columns if col not in VALID_CHECK_COLUMNS]
        if invalid_check_columns:
            api_logger.error(f"Invalid CheckColumns for rule {rule_id}: {invalid_check_columns}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid CheckColumns for rule '{rule_id}': {invalid_check_columns}. Valid columns are: {VALID_CHECK_COLUMNS}"
            )
    
    # Build MLS-scoped rule lookup
    mls_rules_map = {}
    for rule in validation_request.AIViolationID:
        key = (rule.ID, rule.mlsId)
        columns = set(rule.columns_list())
        if key in mls_rules_map:
            mls_rules_map[key].update(columns)
            api_logger.debug(f"Merged duplicate rule entry for {key}: {mls_rules_map[key]}")
        else:
            mls_rules_map[key] = columns
    
    # Validate Data records
    for idx, record in enumerate(validation_request.Data):
        record_mls_id = record.mlsId
        record_fields = set(record.model_dump(exclude_unset=True).keys()) - {"mlsnum", "mlsId"}
        
        applicable_rules = {k: v for k, v in mls_rules_map.items() if k[1] == record_mls_id}
        
        if not applicable_rules:
            api_logger.error(f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) has no matching rules")
            raise HTTPException(
                status_code=400,
                detail=f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) has no matching rules. Available mlsIds in rules: {list(set(k[1] for k in mls_rules_map.keys()))}"
            )
        
        required_columns = set()
        for (rule_id, mls_id), columns in applicable_rules.items():
            required_columns.update(columns)
        
        missing_columns = required_columns - record_fields
        if missing_columns:
            api_logger.error(f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) missing required columns: {missing_columns}")
            raise HTTPException(
                status_code=400,
                detail=f"Record {idx} (mlsnum={record.mlsnum}, mlsId={record_mls_id}) missing required columns: {list(missing_columns)}. Required: {list(required_columns)}"
            )

    api_logger.info("Validation completed successfully")

    # Fetch prompts, potentially using specific version if provided
    api_logger.info(f"Fetching prompts from Langfuse (prompt_version={validation_request.prompt_version})...")
    prompt_manager = get_prompt_manager()

    rule_mls_pairs = list(mls_rules_map.keys())

    try:
        # If specific prompt version requested, use get_prompt_by_version for each pair
        if validation_request.prompt_version is not None:
            api_logger.info(f"Loading specific prompt version: {validation_request.prompt_version}")
            prompts_map = {}
            for rule_id, mls_id in rule_mls_pairs:
                prompt_data = await prompt_manager.get_prompt_by_version(
                    rule_id=rule_id,
                    mls_id=mls_id,
                    version=validation_request.prompt_version
                )
                prompts_map[(rule_id, mls_id)] = prompt_data
        else:
            # Otherwise use normal batch load (latest prompts)
            prompts_map = await prompt_manager.load_batch_prompts(rule_mls_pairs)

        # Check for missing prompts
        missing_prompts = []
        for pair, prompt in prompts_map.items():
            if prompt is None:
                missing_prompts.append(pair)

        if missing_prompts:
            api_logger.warning(f"Missing prompts for: {missing_prompts}")
            missing_details = [
                f"'{rule_id}' (mls_id='{mls_id}')" for rule_id, mls_id in missing_prompts
            ]
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No Langfuse prompts found for: {', '.join(missing_details)}. "
                    f"To add a new rule, create a Langfuse prompt named "
                    f"'<RULE_ID>_violation' (default) or '<MLS_ID>_<RULE_ID>_violation' "
                    f"(MLS-specific)."
                )
            )
        
        loaded_count = sum(1 for p in prompts_map.values() if p is not None)
        api_logger.info(f"Loaded {loaded_count}/{len(rule_mls_pairs)} prompts")
    
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"Error loading prompts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load prompts from Langfuse: {str(e)}"
        )

    try:
        # Process records using the validation request object (not compliance_request)
        result = await process_all_records(validation_request, mls_rules_map=mls_rules_map, prompts_map=prompts_map, request_id=request_id)
        api_logger.info(f"Prompt validation completed successfully. Total tokens: {result.total_tokens}, Elapsed time: {result.elapsed_time:.2f}s")
        return result
    except Exception as e:
        api_logger.error(f"Error during prompt validation: {str(e)}", exc_info=True)
        raise
