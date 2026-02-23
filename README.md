# AI Compliance Checker API - Production Ready with Comprehensive Logging

## Overview
This is a production-ready async FastAPI application that checks real estate listing text against multiple compliance rules (Fair Housing, Compensation, Promotions) using OpenAI's Responses API. The API supports MLS-specific rule implementations and includes comprehensive logging throughout.

## Project Structure
```
ai_compliance_check/
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py              # API endpoints
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── base.py                # General rule functions
│   │   ├── testmls.py             # TESTMLS-specific rules
│   │   └── registry.py            # Rule function registry/dispatcher
│   ├── models.py                  # Pydantic models
│   ├── logger.py                  # Logging configuration
│   └── utils.py                   # Utility functions
├── tests/
│   ├── __init__.py
│   └── test_api.py                # API test script
├── logs/                          # Auto-generated log directory
│   └── api.log                    # Rotating log file
├── main.py                        # FastAPI entrypoint
├── requirements.txt
├── Dockerfile
└── README.md
```

## Logging Configuration

### Log Levels
- **INFO**: General information about request/batch processing, completion stats
- **DEBUG**: Detailed trace points (rule application, record processing, function calls)
- **WARNING**: Non-critical issues (missing MLS mappings, errors that don't fail the request)
- **ERROR**: Critical failures with full stack traces

### Log Output
Logs are written to two destinations:

1. **Console (stdout)**: Real-time logs during development
   - Format: `[YYYY-MM-DD HH:MM:SS] - logger_name - LEVEL - message`

2. **File** (`logs/api.log`): Rotating file handler for production
   - Max file size: 10MB
   - Backup count: 5 files
   - Format: `[YYYY-MM-DD HH:MM:SS] - logger_name - LEVEL - function:line - message`

### Logger Names
- `api.routes`: API endpoint and request processing logs
- `api.rules`: Rule execution and OpenAI client interaction logs
- `api.main`: Application lifecycle (startup/shutdown) logs
- `test.api`: Test execution logs

## Key Logging Points

### Startup/Shutdown
```
INFO: FastAPI application starting up
INFO: OpenAI client closed successfully
```

### API Requests
```
INFO: Received compliance check request with X records
DEBUG: Rules to check: [FAIR, COMP, PROMO]
INFO: Starting batch processing with concurrency limit: 10
```

### Record Processing
```
DEBUG: Processing record {mlsnum} from MLS {mls_id}
DEBUG: Applying rule {rule_id} to record {mlsnum}
DEBUG: Rule {rule_id} completed for {mlsnum}. Tokens: 446
DEBUG: Record {mlsnum} processed in 2.34s with 1564 tokens
```

### Batch Completion
```
INFO: Batch processing completed successfully. Processed 2 records in 11.24s
INFO: Batch statistics - Total tokens: 3202, Elapsed time: 11.24s, Average time/record: 5.62s
```

### Error Handling
```
ERROR: Error applying rule {rule_id} to record {mlsnum}: {error_message}
WARNING: Batch processing completed with 1 errors out of 2 records
```

## Running the API

### Environment Setup

The API automatically loads the OpenAI API key from:
1. **`.env` file** (if it exists in project root) - Recommended
2. **System environment variable** (if no .env file)

**Option 1: Using .env file (Recommended)**
```bash
# Create .env file in project root
echo OPENAI_API_KEY=sk-your-key-here > .env
```

**Option 2: Using environment variables**
```powershell
# PowerShell
$env:OPENAI_API_KEY="sk-your-key-here"

# Or permanently in Windows
setx OPENAI_API_KEY "sk-your-key-here"
```

```bash
# Linux/Mac
export OPENAI_API_KEY="sk-your-key-here"
```

### Development
```powershell
# Run with hot reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Testing
```powershell
# In another terminal
python tests/test_api.py
```

### Production (Docker)
```powershell
docker build -t ai_compliance_check:latest .
docker run -p 8000:8000 -e OPENAI_API_KEY="your_key_here" -v logs:/app/logs ai_compliance_check:latest
```

## API Endpoints

### POST `/check_compliance`
Check multiple records against compliance rules.

**Request:**
```json
{
    "AIViolationID": [
        {"ID": "FAIR", "CheckColumns": "Remarks"},
        {"ID": "COMP", "CheckColumns": "Remarks, PrivateRemarks"}
    ],
    "Data": [
        {
            "mlsnum": "123456OD",
            "mls_id": "TESTMLS",
            "Remarks": "Text to check",
            "PrivateRemarks": "Private text"
        }
    ]
}
```

**Response:**
```json
{
    "ok": 200,
    "results": [
        {
            "mlsnum": "123456OD",
            "mls_id": "TESTMLS",
            "FAIR": {"Remarks": [...], "Total_tokens": 628},
            "COMP": {"Remarks": [], "PrivateRemarks": [], "Total_tokens": 446},
            "latency": 2.34,
            "tokens_used": 1074
        }
    ],
    "error_message": "",
    "total_tokens": 1074,
    "elapsed_time": 2.34
}
```

### POST `/validate_prompt_response`
**NEW** - Validate compliance checking with a specific prompt version (instead of latest).

Useful for regression testing after prompt updates, comparing behavior between versions, or validating prompt changes before deploying.

**Key Difference**: Same request format as `/check_compliance` with one optional field: `prompt_version`

**Request:**
```json
{
    "AIViolationID": [
        {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks", "mlsId": "default"}
    ],
    "Data": [
        {
            "mlsnum": "TEST001",
            "mlsId": "default",
            "Remarks": "Beautiful home in family-friendly area",
            "PrivateRemarks": "Owner is 80 years old"
        }
    ],
    "prompt_version": 2
}
```

**Parameters:**
- `prompt_version` (optional): Specific prompt version to load from Langfuse
  - If omitted: Uses latest version (same behavior as `/check_compliance`)
  - If specified: Tests that specific version
  - Example: `2` to test version 2

**Response:**
Identical to `/check_compliance` - Same response structure with results, tokens, elapsed time, etc.

**Use Cases:**
1. **Regression Testing**: Test prompt updates against known test cases
2. **Version Comparison**: Run same data with different versions to compare behavior
3. **Validation**: Verify new prompt version correctness before deploying
4. **MLS Testing**: Test custom MLS-specific prompts by setting `mlsId` in rules

**Example: Comparing Versions**
```bash
# Test with version 2
curl -X POST http://localhost:8000/validate_prompt_response \
  -H "Authorization: Bearer TOKEN" \
  -d '{"AIViolationID": [...], "Data": [...], "prompt_version": 2}'

# Test with version 3
curl -X POST http://localhost:8000/validate_prompt_response \
  -H "Authorization: Bearer TOKEN" \
  -d '{"AIViolationID": [...], "Data": [...], "prompt_version": 3}'

# Compare results to see improvements
```

### GET `/`
Health check endpoint.

## Adding MLS-Specific Rules

1. Create a new module in `app/rules/` (e.g., `app/rules/custom_mls.py`)
2. Implement rule functions (can wrap or override base functions)
3. Register in `app/rules/registry.py`:
   ```python
   RULE_FUNCTIONS = {
       ("CUSTOM_MLS", "FAIR"): get_fair_housing_custom_mls,
       ("DEFAULT", "FAIR"): get_fair_housing_violation_response,
   }
   ```
4. Logs will show which rule function is being used

## Async Architecture

- Uses `AsyncOpenAI` client for non-blocking I/O
- Concurrent record processing with configurable semaphore (default: 10)
- Proper async/await throughout the call chain
- Client lifecycle management (startup/shutdown events)

## Error Handling

- Per-record error capture and reporting (doesn't fail entire batch)
- Detailed exception logging with stack traces
- Graceful degradation on missing rule mappings
- Clear error messages in API responses

## Performance Monitoring

All responses include:
- `elapsed_time`: Total request time
- `total_tokens`: Cumulative tokens used
- `tokens_used` (per record): Individual record token usage
- `latency` (per record): Individual record processing time

Check logs for average metrics and performance trends.

## Dependencies

See `requirements.txt` for full list. Key packages:
- `fastapi`: Web framework
- `openai`: OpenAI API client (async support)
- `pydantic`: Data validation
- `python-dotenv`: Environment configuration
- `uvicorn`: ASGI server

## Future Enhancements

- Prometheus metrics export
- Structured logging (JSON format)
- Rule versioning and A/B testing
- Caching layer for common inputs
- Rate limiting and authentication