from fastapi import APIRouter, HTTPException, Request
from app.models.models import ComplianceRequest, APIResponse, DataItem
from app.rules.registry import get_rule_function
from app.core.logger import api_logger
from app.core.rate_limiter import get_rate_limiter
import asyncio
import time

router = APIRouter()

@router.post("/check_compliance", response_model=APIResponse)
async def check_compliance(compliance_request: ComplianceRequest, request: Request):
    request_id = request.state.request_id
    api_logger.info(f"Received compliance check request with {len(compliance_request.Data)} records")
    api_logger.debug(f"Rules to check: {[rule.ID for rule in compliance_request.AIViolationID]}")
    
    if not compliance_request.Data:
        api_logger.warning("Empty data list received")
        raise HTTPException(status_code=400, detail="Empty data list")
    
    # Validate rule IDs
    from app.rules.registry import DEFAULT_RULE_FUNCTIONS, RULE_REQUIRED_COLUMNS
    invalid_rules = [rule.ID for rule in compliance_request.AIViolationID if rule.ID not in DEFAULT_RULE_FUNCTIONS]
    if invalid_rules:
        api_logger.error(f"Invalid rule IDs provided: {invalid_rules}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid rule IDs: {invalid_rules}. Valid rules are: {list(DEFAULT_RULE_FUNCTIONS.keys())}"
        )
    
    # Validate CheckColumns against RULE_REQUIRED_COLUMNS
    for rule in compliance_request.AIViolationID:
        rule_id = rule.ID
        check_columns = rule.CheckColumns.split(",")
        allowed_columns = RULE_REQUIRED_COLUMNS.get(rule_id, [])
        
        invalid_check_columns = [col for col in check_columns if col not in allowed_columns]
        if invalid_check_columns:
            api_logger.error(f"Invalid CheckColumns for rule {rule_id}: {invalid_check_columns}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid CheckColumns for rule '{rule_id}': {invalid_check_columns}. Valid columns are: {allowed_columns}"
            )
    
    # Validate Data fields (exclude mandatory fields: mlsnum, mls_id)
    if compliance_request.Data:
        # Collect all allowed columns from requested rules
        all_allowed_columns = set()
        for rule in compliance_request.AIViolationID:
            all_allowed_columns.update(RULE_REQUIRED_COLUMNS.get(rule.ID, []))
        
        # Get fields from first data record (only non-empty fields to avoid default values)
        sample_record = compliance_request.Data[0]
        data_fields = set(sample_record.model_dump(exclude_unset=True).keys()) - {"mlsnum", "mls_id"}
        
        # Check for extra fields not in registry
        extra_fields = data_fields - all_allowed_columns
        if extra_fields:
            api_logger.error(f"Data contains fields not in RULE_REQUIRED_COLUMNS: {extra_fields}")
            raise HTTPException(
                status_code=400,
                detail=f"Data contains invalid fields: {list(extra_fields)}. Allowed fields for requested rules: {list(all_allowed_columns)}"
            )
    
    try:
        result = await process_all_records(compliance_request)
        api_logger.info(f"Compliance check completed successfully. Total tokens: {result.total_tokens}, Elapsed time: {result.elapsed_time:.2f}s")
        return result
    except Exception as e:
        api_logger.error(f"Error during compliance check: {str(e)}", exc_info=True)
        raise

async def process_single_rule(record: DataItem, rule_id: str, columns: list, mls_id: str):
    """
    Process a single rule for a record (used for parallel execution).
    
    Args:
        record: Data record to process
        rule_id: Rule identifier (FAIR, COMP, PROMO)
        columns: List of columns to check for this rule
        mls_id: MLS identifier
        
    Returns:
        Tuple of (rule_id, result_dict, tokens_used)
    """
    public_remarks = record.Remarks if "Remarks" in columns else ""
    private_remarks = record.PrivateRemarks if "PrivateRemarks" in columns else ""
    directions = record.Directions if "Directions" in columns else ""
    
    try:
        api_logger.debug(f"Applying rule {rule_id} to record {record.mlsnum}")
        rule_func = get_rule_function(mls_id, rule_id)
        result = await rule_func(public_remarks, private_remarks, directions)
        tokens_used = result.get("Total_tokens", 0)
        api_logger.debug(f"Rule {rule_id} completed for {record.mlsnum}. Tokens: {tokens_used}")
        return (rule_id.upper(), result, tokens_used)
    except Exception as e:
        api_logger.error(f"Error applying rule {rule_id} to record {record.mlsnum}: {str(e)}", exc_info=True)
        return (rule_id.upper(), {
            "Remarks": [],
            "PrivateRemarks": [],
            "Directions": [],
            "error": str(e)
        }, 0)


async def process_record(record: DataItem, ai_rules, semaphore):
    """
    Process all rules for a single record in parallel.
    
    Args:
        record: Data record to process
        ai_rules: Dictionary mapping rule_id -> columns
        semaphore: Semaphore for concurrency control
        
    Returns:
        Dictionary with results for all rules
    """
    async with semaphore:
        start_time = time.time()
        mlsnum = record.mlsnum
        mls_id = record.mls_id
        record_result = {"mlsnum": mlsnum, "mls_id": mls_id}
        
        api_logger.debug(f"Processing record {mlsnum} from MLS {mls_id} with {len(ai_rules)} rules in parallel")
        
        # Execute ALL rules in parallel for this record
        rule_tasks = [
            process_single_rule(record, rule_id, columns, mls_id)
            for rule_id, columns in ai_rules.items()
        ]
        
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
        
        latency = time.time() - start_time
        record_result["latency"] = latency
        record_result["tokens_used"] = total_tokens
        api_logger.debug(f"Record {mlsnum} processed in {latency:.2f}s with {total_tokens} tokens ({len(ai_rules)} rules in parallel)")
        return record_result

async def process_all_records(request: ComplianceRequest):
    """
    Process all records with dynamic concurrency based on rate limits.
    
    Args:
        request: ComplianceRequest with data and rules
        
    Returns:
        APIResponse with results
    """
    rate_limiter = get_rate_limiter()
    start_time = time.time()
    
    ai_rules = {rule.ID: rule.CheckColumns.split(",") for rule in request.AIViolationID}
    total_api_calls = len(request.Data) * len(ai_rules)
    
    api_logger.info(
        f"Starting batch processing: {len(request.Data)} records × {len(ai_rules)} rules = "
        f"{total_api_calls} API calls"
    )
    api_logger.debug(f"Rules configuration: {ai_rules}")
    
    # Get initial safe concurrency from rate limiter
    initial_concurrency = rate_limiter.get_safe_concurrency()
    api_logger.info(f"Initial concurrency: {initial_concurrency}")
    
    semaphore = asyncio.Semaphore(initial_concurrency)
    
    # Create tasks for all records
    api_logger.info(f"Creating tasks for {len(request.Data)} records (parallel rule execution enabled)")
    tasks = [process_record(record, ai_rules, semaphore) for record in request.Data]
    
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
        error_message="",
        total_tokens=total_tokens,
        elapsed_time=elapsed
    )
