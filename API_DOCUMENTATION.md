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

- **Framework:** FastAPI 0.124.0
- **AI Provider:** OpenAI Responses API (SDK 2.20.0)
- **Prompt Management:** Langfuse 3.14.1
- **Python:** 3.10+ (3.13 recommended)
- **Async Runtime:** asyncio
- **HTTP Client:** httpx 0.28.1 with connection pooling
- **Observability:** prometheus-fastapi-instrumentator 7.0.0, prometheus-client 0.21.0
- **Testing:** pytest 9.0.2 with 107 tests (100% pass rate, 89% coverage)

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
│   │   ├── routes.py              # POST /check_compliance & /validate_prompt_response
│   │   └── auth_routes.py         # Auth endpoints (login, register, refresh, logout, me)
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── api_key_auth.py        # Service-to-service API key auth
│   │   ├── dependencies.py        # FastAPI dependency injection (verify_authentication)
│   │   ├── jwt_handler.py         # JWT token creation & verification
│   │   ├── models.py              # User/Token models + in-memory user store
│   │   └── password_handler.py    # bcrypt password hashing
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Configuration constants & env var loading
│   │   ├── logger.py              # Async-safe, queue-based logging with per-request files
│   │   ├── metrics.py             # Prometheus metrics (counters, histograms, gauges)
│   │   ├── middleware.py          # Request ID middleware
│   │   ├── prompt_cache.py        # Langfuse prompt manager (always-fresh fetches)
│   │   ├── lf_prompt_repo.py      # Langfuse API client
│   │   ├── prompt_replica_store.py # Local SQLite prompt replica/cache
│   │   ├── rate_limiter.py        # Dynamic rate limiting
│   │   └── retry_handler.py       # Retry with backoff
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py              # Pydantic models (ComplianceRequest, PromptValidationRequest, APIResponse)
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── base.py                # Generic prompt-driven rule executor
│   │   └── registry.py            # Rule function lookup & dispatcher
│   ├── utils/
│   │   ├── __init__.py
│   │   └── utils.py               # JSON response parser
│   └── main.py                    # Application entry point
├── tests/
│   ├── conftest.py                # Test fixtures
│   ├── test_api_key_auth.py       # API key auth tests
│   ├── test_auth.py               # JWT auth & user management tests
│   ├── test_endpoints.py          # API endpoint tests
│   ├── test_integration.py        # E2E workflow tests
│   ├── test_metrics.py            # Prometheus metrics tests
│   ├── test_prompt_cache.py       # Langfuse prompt loading tests
│   ├── test_rate_limiter.py       # Rate limiter tests
│   ├── test_registry.py           # Rule registry tests
│   ├── test_request_id.py         # Request ID middleware tests
│   ├── test_rules.py              # Rule function tests
│   └── test_utils.py              # Utility function tests
├── monitoring/
│   ├── prometheus/
│   │   └── prometheus.yml         # Prometheus scrape config
│   └── grafana/
│       ├── dashboards/
│       │   └── compliance-dashboard.json
│       └── provisioning/
│           └── datasources/
│               └── datasource.yml
├── test_data/                     # Sample request payloads
├── logs/                          # Auto-generated per-request log files
├── main.py                        # Root entry point
├── sync_prompts.py                # Standalone prompt sync script
├── compliance_api_check.py        # Integration test script
├── docker-compose.yml             # Dev/prod config with monitoring stack
├── docker-compose.prod.yml        # Production-only configuration
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
  -H "X-API-Key: sk-service-your-key-here" \
  -d '{
    "AIViolationID": [
      {"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks,PrivateRemarks"}
    ],
    "Data": [
      {
        "mlsnum": "ML123456",
        "mlsId": "TESTMLS",
        "Remarks": "Beautiful family home",
        "PrivateRemarks": "Great for families"
      }
    ]
  }'
```

---

## Authentication

The API supports **dual authentication** — every request to `/check_compliance` and `/validate_prompt_response` must include one of:

### API Key (service-to-service)

```bash
curl -X POST http://localhost:8000/check_compliance \
  -H "X-API-Key: sk-service-your-key-here" \
  -H "Content-Type: application/json" \
  -d @request.json
```

### JWT Bearer Token (frontend users)

```bash
# 1. Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "email": "user@example.com", "password": "securepass", "full_name": "My User"}'

# 2. Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "password": "securepass"}'

# 3. Use access_token
curl -X POST http://localhost:8000/check_compliance \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d @request.json
```

### Auth Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login, returns access + refresh tokens |
| POST | `/auth/refresh` | Refresh an expired access token |
| POST | `/auth/logout` | Logout (clears refresh token cookie) |
| GET | `/auth/me` | Get current authenticated user info |

---

## API Endpoints

### 1. Health Check

**Endpoint:** `GET /`

**Description:** Check if the API is running

**Response:**
```json
{
  "status": "ok",
  "message": "AI Compliance Checker API is running!"
}
```

**Status Codes:**
- `200` - Service is healthy

---

### 2. Check Compliance

**Endpoint:** `POST /check_compliance`

**Description:** Validate MLS listings for rule compliance

**Authentication required** — provide either `X-API-Key` header or `Authorization: Bearer <token>`.

#### Request Body

```json
{
  "AIViolationID": [
    {
      "ID": "FAIR",
      "mlsId": "TESTMLS",
      "CheckColumns": "Remarks,PrivateRemarks"
    },
    {
      "ID": "COMP",
      "mlsId": "TESTMLS",
      "CheckColumns": "Remarks,PrivateRemarks"
    }
  ],
  "Data": [
    {
      "mlsnum": "ML123456",
      "mlsId": "TESTMLS",
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
  - `mlsId` (string, required): MLS board identifier this rule applies to
  - `CheckColumns` (string, required): Comma-separated column names

**Data** (array, required)
- List of MLS listings to check
- Each listing must contain:
  - `mlsnum` (string, required): MLS listing number
  - `mlsId` (string, required): MLS board identifier (must match at least one rule's `mlsId`)
  - Additional fields based on `CheckColumns`

#### Valid Rule IDs

Any rule ID is accepted as long as a matching Langfuse prompt exists. Common rule IDs:

| Rule ID | Description |
|---------|-------------|
| `FAIR` | Fair Housing compliance |
| `COMP` | Compensation disclosure |
| `PROMO` | Marketing language |

#### Valid CheckColumns

`Remarks`, `PrivateRemarks`, `Directions`, `ShowingInstructions`, `ConfidentialRemarks`, `SupplementRemarks`, `Concessions`, `SaleFactors`

#### Response

```json
{
  "ok": 200,
  "results": [
    {
      "mlsnum": "ML123456",
      "mlsId": "TESTMLS",
      "FAIR": null,
      "COMP": {
        "Remarks": [
          {
            "violation": "Missing compensation disclosure",
            "explanation": "..."
          }
        ],
        "PrivateRemarks": [],
        "Total_tokens": 145
      },
      "latency": 2.1,
      "tokens_used": 145
    }
  ],
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "error_message": "",
  "total_tokens": 145,
  "elapsed_time": 2.34
}
```

#### Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `ok` | integer | HTTP status code (200 for success) |
| `results` | array | One result object per input listing |
| `results[].mlsnum` | string | MLS listing number |
| `results[].mlsId` | string | MLS board identifier |
| `results[].<RULE_ID>` | object\|null | Rule result; `null` when no violations found |
| `results[].<RULE_ID>.<column>` | array | Violations found in that column |
| `results[].<RULE_ID>.Total_tokens` | integer | Tokens used for this rule check |
| `results[].latency` | float | Processing time for this record (seconds) |
| `results[].tokens_used` | integer | Total tokens for this record across all rules |
| `request_id` | string | UUID for request tracing |
| `error_message` | string | Empty on success; error details on failure |
| `total_tokens` | integer | Total OpenAI tokens consumed across all records |
| `elapsed_time` | float | Total request processing time in seconds |

#### Status Codes

- `200` - Success (may contain rule violations in results)
- `400` - Bad request (missing `mlsId`, invalid columns, missing prompt, etc.)
- `401` - Unauthorized (missing or invalid authentication)
- `422` - Validation error (missing required fields)
- `500` - Internal server error

#### Headers

**Request Headers:**
- `Content-Type: application/json` (required)
- `X-API-Key: <key>` OR `Authorization: Bearer <token>` (required)

**Response Headers:**
- `X-Request-ID`: Unique request identifier for tracking
- `Content-Type: application/json`

### 3. Validate Prompt Response

**Endpoint:** `POST /validate_prompt_response`

**Description:** Same as `/check_compliance` but allows testing against a **specific Langfuse prompt version**. Useful for regression testing before promoting prompt changes to production.

**Authentication required** — same as `/check_compliance`.

#### Additional Request Field

```json
{
  "AIViolationID": [...],
  "Data": [...],
  "prompt_version": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `prompt_version` | integer\|null | Specific Langfuse prompt version. Omit or `null` to use latest (identical to `/check_compliance`). |

When `prompt_version` is provided, prompts are fetched using the `fp_{RULE_ID}_violation` naming convention.

**Response structure is identical to `/check_compliance`.**

```bash
curl -X POST http://localhost:8000/validate_prompt_response \
  -H "X-API-Key: sk-service-your-key-here" \
  -H "Content-Type: application/json" \
  -d @test_data/prompt_validation_example.json
```

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
```
Budget > 50%   → 200 concurrent calls (MAX_CONCURRENCY)
Budget 20-50%  → 10-200 (linear scale)
Budget 10-20%  → 10 concurrent calls (MIN_CONCURRENCY)
Budget < 10%   → 5 concurrent calls (critical)
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

**Langfuse prompt name:** `FAIR_violation` (default) or `FAIR_{MLS_ID}_violation` (MLS-specific)

#### Compensation Rule (COMP)

**Checks for:** Proper compensation disclosure, buyer agent commission information.

**Langfuse prompt name:** `COMP_violation` (default) or `COMP_{MLS_ID}_violation` (MLS-specific)

#### Marketing Rule (PROMO)

**Checks for:** Prohibited marketing language, exaggerations, misleading claims.

**Langfuse prompt name:** `PROMO_violation` (default) or `PROMO_{MLS_ID}_violation` (MLS-specific)

#### Rule Function Signature

All rules use a generic prompt-driven executor. The function accepts any combination of the following named parameters depending on which columns are configured in `CheckColumns`:

```python
async def rule_function(
    public_remarks: str = "",        # Remarks
    private_remarks: str = "",       # PrivateRemarks
    directions: str = "",            # Directions
    ShowingInstructions: str = "",   # ShowingInstructions
    ConfidentialRemarks: str = "",   # ConfidentialRemarks
    SupplementRemarks: str = "",     # SupplementRemarks
    Concessions: str = "",           # Concessions
    SaleFactors: str = "",           # SaleFactors
    prompt_data: dict = None,        # Pre-loaded Langfuse prompt
) -> dict
```

Only parameters accepted by a given rule function's signature are passed — custom rules can accept any subset.

---

### 4. Rule Registry (`app/rules/registry.py`)

**Purpose:** Resolves rule IDs to their executor functions and validates column names.

**Valid Check Columns:**
```python
VALID_CHECK_COLUMNS = [
    "Remarks", "PrivateRemarks", "Directions", "ShowingInstructions",
    "ConfidentialRemarks", "SupplementRemarks", "Concessions", "SaleFactors"
]
```

**Function Lookup:**
```python
func = get_rule_function(mls_id="TESTMLS", rule_id="FAIR")
# Returns the appropriate rule executor for the given MLS ID and rule ID
```

Rules are prompt-driven — no custom Python code is needed per rule. All rules use the generic executor in `app/rules/base.py` which renders the Langfuse Jinja2 template and calls the OpenAI Responses API.

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
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
SERVICE_API_KEY=sk-service-your-generated-key
```

**Optional:**
```bash
LANGFUSE_HOST=https://cloud.langfuse.com      # Default: Langfuse Cloud
JWT_SECRET_KEY=your-secure-random-key          # Auto-generated if missing
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
FRONTEND_URL=http://localhost:3000
PROMPT_SQLITE_PATH=/data/prompt_replica.db     # SQLite path for prompt replica
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc  # Required for multi-worker metrics
```

### Configuration File (`app/core/config.py`)

```python
# OpenAI API Configuration
API_TIMEOUT = 30.0           # Per-request timeout (seconds)
REQUEST_TIMEOUT = 600.0      # Total batch timeout (10 minutes)
MAX_OUTPUT_TOKENS = 6590     # Max output tokens per OpenAI response

# Rate Limiting
CHARS_PER_TOKEN = 4
SAFETY_MARGIN = 0.90
MIN_REMAINING_TOKENS_PCT = 0.10
MIN_CONCURRENCY = 10
MAX_CONCURRENCY = 200
DEFAULT_CONCURRENCY = 50

# Budget Thresholds
HIGH_BUDGET_THRESHOLD = 0.50    # >50% remaining → MAX_CONCURRENCY (200)
MEDIUM_BUDGET_THRESHOLD = 0.20  # 20-50% remaining → linear scale
LOW_BUDGET_THRESHOLD = 0.10     # <10% remaining → MIN_CONCURRENCY (10)

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
  "detail": "Invalid CheckColumns for rule 'FAIR': ['InvalidColumn']. Valid columns are: ['Remarks', 'PrivateRemarks', 'Directions', 'ShowingInstructions', 'ConfidentialRemarks', 'SupplementRemarks', 'Concessions', 'SaleFactors']"
}
```

**Missing Langfuse Prompt:**
```json
{
  "detail": "No Langfuse prompts found for: 'FAIR' (mls_id='TESTMLS'). To add a new rule, create a Langfuse prompt named '<RULE_ID>_violation' (default) or '<RULE_ID>_<MLS_ID>_violation' (MLS-specific)."
}
```

**Empty Data:**
```json
{
  "detail": "Empty data list"
}
```

#### 401 Unauthorized

**Missing Authentication:**
```json
{
  "detail": "Authentication required. Provide either X-API-Key header or Authorization Bearer token."
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

**Coverage:** 89% overall (107 tests, 100% pass rate)

**Test Files:**
- `test_auth.py` - JWT authentication & user management
- `test_api_key_auth.py` - API key authentication
- `test_endpoints.py` - API endpoint functionality + prompt validation endpoint
- `test_integration.py` - E2E workflow tests
- `test_metrics.py` - Prometheus metrics instrumentation
- `test_prompt_cache.py` - Langfuse prompt loading
- `test_rate_limiter.py` - Dynamic rate limiting logic
- `test_registry.py` - Rule registry & dispatcher
- `test_request_id.py` - Request ID middleware
- `test_rules.py` - Rule execution & OpenAI interaction
- `test_utils.py` - JSON response parser

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

The `docker-compose.yml` includes four services:

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI application (4 workers) |
| `prometheus` | 9092 | Metrics collection (scrapes `/metrics` every 15s) |
| `grafana` | 3001 | Dashboards (default login: `admin` / `admin`) |
| `cron` | — | Calls `/prompts/sync` every 5 minutes |

Health check: `GET http://localhost:8000/` (interval: 30s, timeout: 10s, retries: 3)

```bash
# Start all services
docker-compose up -d

# Access
http://localhost:8000/docs    # Swagger UI
http://localhost:8000/metrics # Prometheus metrics
http://localhost:9092         # Prometheus UI
http://localhost:3001         # Grafana (admin/admin)
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
   - Prometheus scrapes `GET /metrics` every 15 seconds
   - Grafana dashboards available at port 3001 (preconfigured via `monitoring/grafana/`)
   - Set `PROMETHEUS_MULTIPROC_DIR` env var when running multiple workers to aggregate metrics correctly
   - Key metrics to alert on: `compliance_openai_errors_total`, `http_request_duration_seconds`, `compliance_records_in_processing`

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

### Version 3.0.0 (Current)

**Major Changes:**
- ✅ Dual authentication: JWT Bearer tokens + X-API-Key (service-to-service)
- ✅ Langfuse prompt-driven rule system (no code changes needed to add rules)
- ✅ `/validate_prompt_response` endpoint for prompt version testing
- ✅ Prometheus + Grafana monitoring stack
- ✅ SQLite prompt replica store with cron-based sync
- ✅ Complete test suite (107 tests, 100% pass rate)
- ✅ 89% code coverage

### Version 2.0.0

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
    ID: str       # Rule identifier, e.g. "FAIR", "COMP", "PROMO"
    mlsId: str    # MLS board identifier (required)
    CheckColumns: str  # Comma-separated column names
```

#### DataItem
```python
class DataItem(BaseModel):
    mlsnum: str
    mlsId: str    # Must match at least one rule's mlsId
    # Optional text fields: Remarks, PrivateRemarks, Directions,
    # ShowingInstructions, ConfidentialRemarks, SupplementRemarks,
    # Concessions, SaleFactors
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
