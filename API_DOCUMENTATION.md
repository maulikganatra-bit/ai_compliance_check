# AI Compliance Check API - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Getting Started](#getting-started)
4. [API Endpoints](#api-endpoints)
5. [Core Components](#core-components)
6. [Configuration](#configuration)
7. [Error Handling](#error-handling)
8. [Rate Limiting](#rate-limiting)
9. [Testing](#testing)
10. [Deployment](#deployment)
11. [Troubleshooting](#troubleshooting)

---

## Overview

### What is AI Compliance Check API?

The AI Compliance Check API is a FastAPI-based service that validates MLS (Multiple Listing Service) real estate listings for compliance with industry rules using OpenAI's AI models. It checks listings for:

- **Fair Housing violations (FAIR)** - Ensures no discriminatory language
- **Compensation violations (COMP)** - Validates proper compensation disclosure
- **Marketing violations (PROMO)** - Checks marketing language compliance

### Key Features

✅ **Intelligent Rate Limiting** - Dynamically adjusts to OpenAI rate limits  
✅ **Automatic Retries** - Handles transient failures with exponential backoff  
✅ **Batch Processing** - Check multiple listings in parallel  
✅ **Request Tracking** - Unique request IDs for debugging  
✅ **Comprehensive Logging** - Structured logging with correlation IDs  
✅ **High Performance** - Connection pooling and concurrent processing  
✅ **Robust Error Handling** - Graceful degradation on failures  

### Technology Stack

- **Framework:** FastAPI 0.122.0
- **AI Provider:** OpenAI Responses API
- **Python:** 3.13+
- **Async Runtime:** asyncio
- **HTTP Client:** httpx with connection pooling
- **Testing:** pytest with 99 tests (100% pass rate, 89% coverage)

---

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Application                    │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/JSON
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Middleware  │─▶│   Routes     │─▶│  Rule Registry  │  │
│  │  (Request ID)│  │ (Validation) │  │  (Rule Lookup)  │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌────────────┐  ┌──────────┐
    │  Rate    │  │   Retry    │  │  Rule    │
    │ Limiter  │  │  Handler   │  │Functions │
    └─────┬────┘  └─────┬──────┘  └─────┬────┘
          │             │               │
          └─────────────┼───────────────┘
                        ▼
              ┌──────────────────┐
              │  OpenAI API      │
              │ (Responses API)  │
              └──────────────────┘
```

### Component Flow

1. **Client** sends POST request to `/check_compliance`
2. **Middleware** adds unique request ID
3. **Routes** validates request data and rules
4. **Rate Limiter** checks if request can proceed
5. **Rule Functions** call OpenAI with retry logic
6. **Response** parsed and returned to client

### Directory Structure

```
ai_compliance_check/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py              # API endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Configuration constants
│   │   ├── logger.py              # Structured logging
│   │   ├── middleware.py          # Request ID middleware
│   │   ├── rate_limiter.py        # Dynamic rate limiting
│   │   └── retry_handler.py       # Retry with backoff
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py              # Pydantic models
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── base.py                # Rule functions
│   │   ├── registry.py            # Rule registration
│   │   └── custom_rules/          # MLS-specific rules
│   ├── utils/
│   │   ├── __init__.py
│   │   └── utils.py               # Utility functions
│   └── main.py                    # Application entry point
├── tests/
│   ├── conftest.py                # Test fixtures
│   ├── test_endpoints.py          # API tests
│   ├── test_integration.py        # E2E tests
│   ├── test_rate_limiter.py       # Rate limiter tests
│   ├── test_registry.py           # Registry tests
│   ├── test_rules.py              # Rule function tests
│   └── test_utils.py              # Utility tests
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.13 or higher
- OpenAI API key
- pip or pipenv for package management

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/maulikganatra-bit/ai_compliance_check.git
cd ai_compliance_check
```

2. **Create virtual environment:**
```bash
python -m venv myenv
# Windows
myenv\Scripts\activate
# Linux/Mac
source myenv/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Set environment variables:**
```bash
# Windows PowerShell
$env:OPENAI_API_KEY="sk-your-key-here"

# Linux/Mac
export OPENAI_API_KEY="sk-your-key-here"
```

### Running the API

**Development mode:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Production mode:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Using Docker:**
```bash
docker-compose up -d
```

### Quick Test

```bash
curl -X POST http://localhost:8000/check_compliance \
  -H "Content-Type: application/json" \
  -d '{
    "AIViolationID": [
      {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}
    ],
    "Data": [
      {
        "mlsnum": "ML123456",
        "mls_id": "TESTMLS",
        "Remarks": "Beautiful family home",
        "PrivateRemarks": "Great for families"
      }
    ]
  }'
```

---

## API Endpoints

### 1. Health Check

**Endpoint:** `GET /health`

**Description:** Check if the API is running

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-12-02T10:30:00Z"
}
```

**Status Codes:**
- `200` - Service is healthy

---

### 2. Check Compliance

**Endpoint:** `POST /check_compliance`

**Description:** Validate MLS listings for rule compliance

#### Request Body

```json
{
  "AIViolationID": [
    {
      "ID": "FAIR",
      "CheckColumns": "Remarks,PrivateRemarks"
    },
    {
      "ID": "COMP",
      "CheckColumns": "Remarks,PrivateRemarks"
    }
  ],
  "Data": [
    {
      "mlsnum": "ML123456",
      "mls_id": "TESTMLS",
      "Remarks": "Beautiful home near excellent schools",
      "PrivateRemarks": "Commission: 3%",
      "Directions": "Take Main St to Oak Ave"
    }
  ]
}
```

#### Request Schema

**AIViolationID** (array, required)
- List of rules to check against
- Each rule contains:
  - `ID` (string, required): Rule identifier (`FAIR`, `COMP`, `PROMO`)
  - `CheckColumns` (string, required): Comma-separated column names

**Data** (array, required)
- List of MLS listings to check
- Each listing must contain:
  - `mlsnum` (string, required): MLS listing number
  - `mls_id` (string, required): MLS board identifier
  - Additional fields based on `CheckColumns`

#### Valid Rule IDs

| Rule ID | Description | Required Columns |
|---------|-------------|------------------|
| `FAIR` | Fair Housing compliance | Remarks, PrivateRemarks, Directions |
| `COMP` | Compensation disclosure | Remarks, PrivateRemarks, Directions |
| `PROMO` | Marketing language | Remarks, PrivateRemarks, Directions |

#### Response

```json
{
  "ok": 200,
  "results": [
    {
      "FAIR": {
        "Remarks": [],
        "PrivateRemarks": [],
        "Total_tokens": 150
      },
      "COMP": {
        "Remarks": [
          {
            "violation": "Missing compensation disclosure",
            "field": "Remarks",
            "suggestion": "Add compensation information"
          }
        ],
        "PrivateRemarks": [],
        "Total_tokens": 145
      }
    }
  ],
  "error_message": "",
  "total_tokens": 295,
  "elapsed_time": 2.34
}
```

#### Response Schema

**ok** (integer)
- HTTP status code (200 for success)

**results** (array)
- Array of result objects (one per listing)
- Each result contains rule results keyed by rule ID
- Each rule result contains:
  - `Remarks` (array): Violations found in Remarks field
  - `PrivateRemarks` (array): Violations in PrivateRemarks field
  - `Total_tokens` (integer): Tokens used for this rule check

**error_message** (string)
- Empty string if successful
- Error description if failed

**total_tokens** (integer)
- Total OpenAI tokens consumed

**elapsed_time** (float)
- Total processing time in seconds

#### Status Codes

- `200` - Success (may contain rule violations in results)
- `400` - Bad request (invalid rule ID, invalid columns, etc.)
- `422` - Validation error (missing required fields)
- `500` - Internal server error

#### Headers

**Request Headers:**
- `Content-Type: application/json` (required)

**Response Headers:**
- `X-Request-ID`: Unique request identifier for tracking
- `Content-Type: application/json`

---

## Core Components

### 1. Rate Limiter (`app/core/rate_limiter.py`)

**Purpose:** Dynamically manages OpenAI API rate limits to prevent 429 errors.

**Key Features:**
- Reads actual limits from OpenAI response headers
- Tracks token and request budgets in real-time
- Adjusts concurrency dynamically (10-200 concurrent calls)
- Auto-pauses when approaching limits (90% safety margin)
- Model-agnostic (works with any OpenAI model)

**How It Works:**

1. **Before API Call:**
```python
rate_limiter = get_rate_limiter()
estimated = rate_limiter.estimate_tokens("Some text")
await rate_limiter.wait_if_needed(estimated)
```

2. **After API Call:**
```python
await rate_limiter.update_from_headers(response)
```

**Configuration:**
- `SAFETY_MARGIN`: 0.9 (use 90% of available budget)
- `MIN_CONCURRENCY`: 10
- `MAX_CONCURRENCY`: 200
- `DEFAULT_CONCURRENCY`: 50

**Token Estimation:**
```python
# Estimates tokens: characters / 4
estimated_tokens = len(text) / CHARS_PER_TOKEN
```

**Dynamic Concurrency:**
```python
Budget > 80% → 200 concurrent calls
Budget 60-80% → 150 concurrent calls
Budget 40-60% → 100 concurrent calls
Budget 20-40% → 50 concurrent calls
Budget < 20% → 10 concurrent calls
```

---

### 2. Retry Handler (`app/core/retry_handler.py`)

**Purpose:** Automatically retries failed API calls with exponential backoff.

**Retry Strategy:**
- Attempt 1: Wait 1s + jitter
- Attempt 2: Wait 2s + jitter
- Attempt 3: Wait 4s + jitter
- Max delay capped at 16s

**What Gets Retried:**
- ✅ `RateLimitError` (429) - Rate limit hit
- ✅ `APITimeoutError` - Request timeout
- ✅ `APIError` (5xx) - Server errors (500, 502, 503, 504)
- ✅ `ConnectionError` - Network connection issues
- ✅ `TimeoutError` - Socket timeout
- ✅ `OSError` - Network-level errors

**What Doesn't Get Retried:**
- ❌ `APIError` (4xx) - Client errors (400, 401, 403, 404)
- ❌ Programming errors
- ❌ Validation errors

**Usage:**
```python
@retry_with_backoff(max_retries=3, base_delay=1.0)
async def my_api_call():
    response = await client.responses.create(...)
    return response
```

**Jitter:**
Random delay (0-1s) added to prevent thundering herd problem when multiple requests retry simultaneously.

---

### 3. Rule Functions (`app/rules/base.py`)

**Purpose:** Core logic for checking each rule type against listing data.

#### Fair Housing Rule (FAIR)

**Checks for:** Discriminatory language related to race, religion, national origin, familial status, disability, sex.

**API Prompt:** `pmpt_68c29d3553688193b6d064d556ebc3c7039d675dbb8aefa0`

**Function:**
```python
async def get_fair_housing_violation_response(
    public_remarks: str,
    private_remarks: str,
    directions: str = None
) -> dict
```

#### Compensation Rule (COMP)

**Checks for:** Proper compensation disclosure, buyer agent commission information.

**API Prompt:** `pmpt_50fcb3dae4b83eb7f45b51636b0e9f2cd0ea45c8603745f3`

**Function:**
```python
async def get_comp_violation_response(
    public_remarks: str,
    private_remarks: str,
    directions: str = None
) -> dict
```

#### Marketing Rule (PROMO)

**Checks for:** Prohibited marketing language, exaggerations, misleading claims.

**API Prompt:** `pmpt_1f51cccaf7b2889e03d64c03a4e0e87bf6c5f18963a68e86`

**Function:**
```python
async def get_marketing_rule_violation_response(
    public_remarks: str,
    private_remarks: str,
    directions: str = None
) -> dict
```

---

### 4. Rule Registry (`app/rules/registry.py`)

**Purpose:** Maps rule IDs to their implementations and manages custom rule loading.

**Default Rules:**
```python
DEFAULT_RULE_FUNCTIONS = {
    "FAIR": get_fair_housing_violation_response,
    "COMP": get_comp_violation_response,
    "PROMO": get_marketing_rule_violation_response
}
```

**Required Columns:**
```python
RULE_REQUIRED_COLUMNS = {
    "FAIR": ["Remarks", "PrivateRemarks", "Directions"],
    "COMP": ["Remarks", "PrivateRemarks", "Directions"],
    "PROMO": ["Remarks", "PrivateRemarks", "Directions"]
}
```

**Custom Rules:**

MLS-specific rules can be added by creating files in `app/rules/custom_rules/`:

Filename format: `{MLS_ID}_{RULE_ID}.py`

Example: `TESTMLS_FAIR.py`

```python
async def get_fair_housing_violation_response(
    public_remarks: str,
    private_remarks: str,
    directions: str = None
) -> dict:
    # Custom implementation for TESTMLS
    return {"Remarks": [], "PrivateRemarks": [], "Total_tokens": 0}
```

**Function Lookup:**
```python
func = get_rule_function(mls_id="TESTMLS", rule_id="FAIR")
# Returns custom rule if exists, otherwise default rule
```

---

### 5. Middleware (`app/core/middleware.py`)

**Purpose:** Add request ID to all incoming requests for tracking.

**Implementation:**
```python
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

**Usage:** Every log entry includes the request ID for correlation.

---

### 6. Response Parser (`app/utils/utils.py`)

**Purpose:** Extract and parse JSON from OpenAI responses.

**Handles:**
- ✅ JSON in markdown code blocks: `` ```json {...} ``` ``
- ✅ JSON with leading/trailing text
- ✅ Plain JSON objects
- ✅ Nested brackets

**Algorithm:**
1. Try to find `` ```json...``` `` fenced blocks
2. Extract and parse JSON from fence
3. If not found, search for first `{` or `[`
4. Match brackets and extract JSON
5. Parse and return dictionary

**Example:**
```python
input = "Here's the result:\n```json\n{\"violations\": []}\n```\nDone!"
output = response_parser(input)
# Returns: {"violations": []}
```

---

## Configuration

### Environment Variables

**Required:**
```bash
OPENAI_API_KEY=sk-your-key-here
```

**Optional:**
```bash
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
API_TIMEOUT=60.0                  # OpenAI API timeout (seconds)
MAX_RETRIES=3                     # Max retry attempts
BASE_RETRY_DELAY=1.0              # Base delay for retries (seconds)
MAX_RETRY_DELAY=16.0              # Max delay cap (seconds)
```

### Configuration File (`app/core/config.py`)

```python
# OpenAI API Configuration
API_TIMEOUT = 60.0
MAX_OUTPUT_TOKENS = 4096

# Rate Limiting
CHARS_PER_TOKEN = 4
SAFETY_MARGIN = 0.9
MIN_CONCURRENCY = 10
MAX_CONCURRENCY = 200
DEFAULT_CONCURRENCY = 50

# Budget Thresholds
HIGH_BUDGET_THRESHOLD = 0.8
MEDIUM_BUDGET_THRESHOLD = 0.6
LOW_BUDGET_THRESHOLD = 0.4
CRITICAL_BUDGET_THRESHOLD = 0.2

# Retry Configuration
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 16.0
JITTER_RANGE = 1.0

# Connection Pooling
MAX_CONNECTIONS = 200
MAX_KEEPALIVE_CONNECTIONS = 50
```

---

## Error Handling

### Error Response Format

All errors return JSON with consistent structure:

```json
{
  "detail": "Error description",
  "error_code": "ERROR_CODE",
  "request_id": "uuid-here"
}
```

### Common Errors

#### 400 Bad Request

**Invalid Rule ID:**
```json
{
  "detail": "Invalid rule IDs: ['INVALID']. Valid rules are: ['FAIR', 'COMP', 'PROMO']"
}
```

**Invalid CheckColumns:**
```json
{
  "detail": "Invalid CheckColumns for rule 'FAIR': ['InvalidColumn']. Valid columns are: ['Remarks', 'PrivateRemarks', 'Directions']"
}
```

**Empty Data:**
```json
{
  "detail": "Empty data list"
}
```

#### 422 Validation Error

**Missing Required Fields:**
```json
{
  "detail": [
    {
      "loc": ["body", "Data", 0, "mlsnum"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

#### 500 Internal Server Error

**OpenAI API Failure:**
```json
{
  "ok": 200,
  "results": [],
  "error_message": "OpenAI API error: Rate limit exceeded",
  "total_tokens": 0,
  "elapsed_time": 1.5
}
```

---

## Rate Limiting

### How Rate Limiting Works

1. **Initialization:**
   - Rate limiter starts with no knowledge of limits
   - First API call returns limits in headers

2. **Header Parsing:**
   ```
   x-ratelimit-limit-tokens: 10000000
   x-ratelimit-remaining-tokens: 9999850
   x-ratelimit-reset-tokens: 6ms
   x-ratelimit-limit-requests: 10000
   x-ratelimit-remaining-requests: 9999
   x-ratelimit-reset-requests: 6ms
   ```

3. **Budget Tracking:**
   - Token budget: `remaining / limit = 99.998%`
   - Request budget: `remaining / limit = 99.99%`
   - Overall budget: `min(token_budget, request_budget)`

4. **Wait Logic:**
   ```python
   if estimated_tokens > (remaining * SAFETY_MARGIN):
       await asyncio.sleep(reset_time)
   ```

5. **Dynamic Concurrency:**
   - Adjusts based on budget percentage
   - More budget = more concurrent calls
   - Less budget = fewer concurrent calls

### Rate Limit Statistics

Get current stats:
```python
rate_limiter = get_rate_limiter()
stats = rate_limiter.get_stats()
```

Returns:
```python
{
    "total_tokens_used": 12500,
    "total_requests_made": 45,
    "remaining_tokens": 9987500,
    "remaining_requests": 9955,
    "token_limit": 10000000,
    "request_limit": 10000,
    "current_concurrency": 150,
    "paused": False,
    "uptime_seconds": 3600.5
}
```

---

## Testing

### Test Suite Overview

**Coverage:** 89% overall (99 tests, 100% pass rate)

**Test Files:**
- `test_endpoints.py` - API endpoint tests (14 tests)
- `test_integration.py` - E2E workflow tests (9 tests)
- `test_rate_limiter.py` - Rate limiter tests (23 tests)
- `test_registry.py` - Rule registry tests (22 tests)
- `test_rules.py` - Rule function tests (12 tests)
- `test_utils.py` - Utility function tests (19 tests)

### Running Tests

**All tests:**
```bash
python -m pytest tests/ -v
```

**Specific file:**
```bash
python -m pytest tests/test_endpoints.py -v
```

**With coverage:**
```bash
python -m pytest tests/ --cov=app --cov-report=html
```

**Quiet mode:**
```bash
python -m pytest tests/ -q
```

### Test Coverage by Module

| Module | Coverage | Status |
|--------|----------|--------|
| app/rules/base.py | 100% | ✅ |
| app/models/models.py | 100% | ✅ |
| app/core/middleware.py | 100% | ✅ |
| app/core/config.py | 100% | ✅ |
| app/main.py | 94% | ✅ |
| app/utils/utils.py | 93% | ✅ |
| app/api/routes.py | 90% | ✅ |
| app/core/logger.py | 90% | ✅ |
| app/core/rate_limiter.py | 87% | ✅ |
| app/core/retry_handler.py | 67% | ⚠️ |
| app/rules/registry.py | 69% | ⚠️ |

---

## Deployment

### Docker Deployment

**Build image:**
```bash
docker build -t ai-compliance-api .
```

**Run container:**
```bash
docker run -d \
  -p 8000:8000 \
  -e OPENAI_API_KEY=sk-your-key \
  --name compliance-api \
  ai-compliance-api
```

**Using Docker Compose:**
```bash
docker-compose up -d
```

### Docker Compose Configuration

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LOG_LEVEL=INFO
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Production Considerations

1. **Workers:**
   - Use multiple workers for high load
   - Recommend: `workers = (2 * CPU cores) + 1`
   ```bash
   uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
   ```

2. **Reverse Proxy:**
   - Use Nginx or Caddy in front of API
   - Enable SSL/TLS
   - Set up load balancing

3. **Environment Variables:**
   - Never commit API keys
   - Use secrets management (AWS Secrets Manager, Azure Key Vault)

4. **Monitoring:**
   - Set up health check endpoint monitoring
   - Track response times
   - Monitor rate limiter stats
   - Alert on error rates

5. **Logging:**
   - Centralize logs (ELK, CloudWatch, etc.)
   - Use request IDs for tracing
   - Set appropriate log levels

---

## Troubleshooting

### Common Issues

#### Issue: Rate Limit Errors (429)

**Symptoms:**
```
OpenAI API error: Rate limit exceeded
```

**Solutions:**
1. Check rate limiter is enabled
2. Verify safety margin is appropriate (0.9 = 90%)
3. Reduce concurrent requests
4. Upgrade OpenAI tier

**Check rate limiter stats:**
```python
rate_limiter = get_rate_limiter()
print(rate_limiter.get_stats())
```

---

#### Issue: Timeout Errors

**Symptoms:**
```
APITimeoutError: Request timed out
```

**Solutions:**
1. Increase timeout in config
2. Check network connectivity
3. Verify OpenAI API status
4. Reduce text length being sent

**Configuration:**
```python
API_TIMEOUT = 120.0  # Increase to 2 minutes
```

---

#### Issue: JSON Parsing Errors

**Symptoms:**
```
JSONDecodeError: Expecting value
```

**Solutions:**
1. Check OpenAI response format
2. Verify prompt returns valid JSON
3. Check response_parser logs
4. Try updating response_parser logic

**Debug:**
```python
# Add logging to see raw response
rules_logger.debug(f"Raw response: {response.output_text}")
```

---

#### Issue: Connection Pool Exhausted

**Symptoms:**
```
Too many open connections
```

**Solutions:**
1. Increase MAX_CONNECTIONS
2. Reduce concurrent requests
3. Check for connection leaks
4. Increase MAX_KEEPALIVE_CONNECTIONS

**Configuration:**
```python
MAX_CONNECTIONS = 300
MAX_KEEPALIVE_CONNECTIONS = 100
```

---

#### Issue: Memory Issues

**Symptoms:**
- High memory usage
- OOM errors
- Slow performance

**Solutions:**
1. Reduce batch sizes
2. Decrease MAX_CONCURRENCY
3. Add request size limits
4. Monitor memory usage

**Monitor:**
```bash
# Linux
free -h
# Windows
Get-Process python | Select-Object WS
```

---

### Debugging Tips

1. **Enable Debug Logging:**
```python
LOG_LEVEL = "DEBUG"
```

2. **Check Request ID:**
Every request has unique ID in `X-Request-ID` header. Use it to trace logs.

3. **Test with Single Request:**
Isolate issues by testing one listing at a time.

4. **Check OpenAI Status:**
Visit [status.openai.com](https://status.openai.com)

5. **Verify API Key:**
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

6. **Review Logs:**
All logs include request ID and module context.

---

## API Best Practices

### Request Optimization

1. **Batch Requests:**
   - Send multiple listings in one request
   - API processes them in parallel
   - Reduces network overhead

2. **Appropriate Rules:**
   - Only check rules you need
   - Each rule = one OpenAI API call
   - 3 rules × 10 listings = 30 API calls

3. **Field Selection:**
   - Only include necessary CheckColumns
   - Reduces token usage
   - Faster processing

### Error Handling

1. **Retry Logic:**
   - Client should implement retries for 5xx errors
   - Don't retry 4xx errors (client errors)
   - Use exponential backoff

2. **Request IDs:**
   - Save request IDs from responses
   - Include in support requests
   - Use for debugging

3. **Validation:**
   - Validate data client-side before sending
   - Check required fields exist
   - Verify rule IDs are valid

### Performance Tips

1. **Connection Reuse:**
   - Use HTTP/1.1 keep-alive
   - Reuse connections when possible

2. **Compression:**
   - Enable gzip compression
   - Reduces payload size

3. **Timeouts:**
   - Set reasonable timeouts
   - Don't set too low (min 30s recommended)

---

## Changelog

### Version 2.0.0 (Current)

**Major Changes:**
- ✅ Complete test suite (99 tests, 100% pass rate)
- ✅ Enhanced retry handler with network error handling
- ✅ Improved response parser with bracket matching
- ✅ Fixed rate limiter edge cases
- ✅ 89% code coverage

**Bug Fixes:**
- Fixed retry handler to handle APIError without status_code
- Added network error retry (ConnectionError, TimeoutError, OSError)
- Fixed parse_reset_time to return 60.0 on error
- Enhanced response_parser for JSON with leading/trailing text
- Fixed HTTP client teardown in shutdown

**Testing:**
- Added comprehensive integration tests
- Fixed all mock structures for OpenAI Responses API
- Updated test assertions to match actual implementation
- Added pytest-cov for coverage reporting

### Version 1.0.0

**Initial Release:**
- FastAPI-based REST API
- OpenAI Responses API integration
- Dynamic rate limiting
- Retry with exponential backoff
- FAIR, COMP, PROMO rule checking
- Request ID tracking
- Structured logging

---

## Support & Contact

### Getting Help

1. **Documentation:** This file
2. **Test Suite:** See `TEST_SUITE_SUMMARY.md`
3. **Issues:** GitHub Issues
4. **Logs:** Check application logs with request ID

### Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new features
4. Ensure all tests pass
5. Submit pull request

### License

[Add your license here]

---

## Appendix

### A. Pydantic Models Reference

#### ComplianceRequest
```python
class ComplianceRequest(BaseModel):
    AIViolationID: List[RuleConfig]
    Data: List[DataItem]
```

#### RuleConfig
```python
class RuleConfig(BaseModel):
    ID: str  # "FAIR", "COMP", or "PROMO"
    CheckColumns: str  # Comma-separated column names
```

#### DataItem
```python
class DataItem(BaseModel):
    mlsnum: str
    mls_id: str
    # Additional fields are dynamic based on CheckColumns
```

#### APIResponse
```python
class APIResponse(BaseModel):
    ok: int
    results: List
    error_message: str
    total_tokens: Optional[int] = 0
    elapsed_time: Optional[float] = 0.0
```

### B. Logging Format

All logs follow this format:
```
[timestamp] - [request-id] - module - LEVEL - message
```

Example:
```
[2025-12-02 22:32:06] - [c51da8d4-10f5-4e91-ab38-51744921309e] - api.routes - INFO - Received compliance check request with 5 records
```

### C. Performance Benchmarks

**Single Listing, Single Rule:**
- Average: ~2-3 seconds
- Tokens: ~150-200

**10 Listings, 3 Rules (30 API calls):**
- Average: ~15-20 seconds (parallel)
- Tokens: ~4,500-6,000

**Rate Limiter Overhead:**
- < 1ms per check
- Negligible impact on performance

---

*Last Updated: December 2, 2025*  
*Version: 2.0.0*  
*API Status: Production Ready ✅*
