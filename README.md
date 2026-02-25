# AI Compliance Checker API

A production-ready, async FastAPI application that validates real estate MLS (Multiple Listing Service) listings for compliance violations using OpenAI's Responses API. It supports dynamic rule definitions via Langfuse prompts, MLS-specific rule customization, dual authentication (JWT + API Key), intelligent rate limiting, and per-request observability.

**Version:** 3.0.0
**Python:** 3.10+ (3.13 recommended)

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running the API](#running-the-api)
- [Authentication](#authentication)
- [API Endpoints](#api-endpoints)
- [Prompt-Driven Rule System](#prompt-driven-rule-system)
- [Dynamic Rate Limiting](#dynamic-rate-limiting)
- [Retry & Error Handling](#retry--error-handling)
- [Request Tracing & Logging](#request-tracing--logging)
- [Connection Pooling & Performance](#connection-pooling--performance)
- [Testing](#testing)
- [Docker Deployment](#docker-deployment)
- [Configuration Reference](#configuration-reference)

---

## Architecture Overview

```
Client Request
  |
  v
RequestIDMiddleware          Generate UUID, inject into context & response header
  |
  v
CORS Middleware              Cross-origin request handling
  |
  v
Authentication               Verify JWT Bearer token OR X-API-Key header
  |
  v
Input Validation             Pydantic models validate rules, columns, and data
  |
  v
Prompt Loading               Fetch rule prompts from Langfuse (always fresh, no cache)
  |                           Lookup: {RULE_ID}_{MLS_ID}_violation -> {RULE_ID}_violation
  v
Batch Processing             Process records in chunks with dynamic concurrency
  |
  +---> Per-Record (parallel rules)
  |       |
  |       +---> Rate Limiter check (token budget estimation)
  |       +---> Render Jinja2 prompt template
  |       +---> OpenAI Responses API call (with retry + backoff)
  |       +---> Update rate limiter from response headers
  |       +---> Parse JSON output, map fields to API response
  |
  v
APIResponse                  Results, token counts, elapsed time, request_id
```

---

## Project Structure

```
ai_compliance_check/
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app initialization & lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                  # POST /check_compliance endpoint
│   │   └── auth_routes.py             # Auth endpoints (login, register, refresh, logout, me)
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── api_key_auth.py            # Service-to-service API key auth
│   │   ├── dependencies.py            # FastAPI dependency injection (verify_authentication)
│   │   ├── jwt_handler.py             # JWT token creation & verification
│   │   ├── models.py                  # User/Token models + in-memory user store
│   │   └── password_handler.py        # bcrypt password hashing
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # All configuration & environment variables
│   │   ├── logger.py                  # Async-safe, queue-based logging with per-request files
│   │   ├── middleware.py              # Request ID injection middleware
│   │   ├── prompt_cache.py            # Langfuse prompt manager (always-fresh fetches)
│   │   ├── rate_limiter.py            # Dynamic rate limiter (reads OpenAI response headers)
│   │   └── retry_handler.py           # Exponential backoff with jitter
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py                  # Pydantic request/response schemas
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── base.py                    # Generic prompt-driven rule executor
│   │   └── registry.py               # Rule function lookup & dispatcher
│   └── utils/
│       ├── __init__.py
│       └── utils.py                   # JSON response parser
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Shared pytest fixtures
│   ├── test_api_key_auth.py
│   ├── test_auth.py
│   ├── test_endpoints.py
│   ├── test_integration.py
│   ├── test_prompt_cache.py
│   ├── test_rate_limiter.py
│   ├── test_registry.py
│   ├── test_request_id.py
│   ├── test_rules.py
│   └── test_utils.py
├── test_data/                         # Sample request payloads
│   ├── sample_request_minimal.json
│   ├── sample_request_small.json
│   ├── test.json
│   └── test_ip.json
├── logs/                              # Auto-generated per-request log files
├── main.py                            # Root entry point (imports app/main.py)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml                 # Development configuration
├── docker-compose.prod.yml            # Production configuration
├── API_DOCUMENTATION.md
├── DOCKER_GUIDE.md
├── TEST_SUITE_SUMMARY.md
└── README.md
```

---

## Tech Stack

| Category | Package | Purpose |
|---|---|---|
| **Framework** | FastAPI 0.124.0, Uvicorn 0.38.0 | Async web framework + ASGI server |
| **AI / LLM** | OpenAI SDK 2.20.0, Langfuse 3.14.1 | AsyncOpenAI client + prompt management |
| **Templating** | Jinja2 3.1.6 | Prompt template rendering |
| **Validation** | Pydantic 2.12.5 | Request/response data validation |
| **Auth** | python-jose 3.5.0, bcrypt 5.0.0 | JWT tokens + password hashing |
| **HTTP** | httpx 0.28.1 | Async HTTP client with connection pooling |
| **Observability** | OpenTelemetry SDK 1.39.1 | Distributed tracing & metrics |
| **Testing** | pytest 9.0.2, pytest-asyncio, pytest-cov | Async test framework + coverage |
| **Config** | python-dotenv 1.2.1 | Environment variable loading |

---

## Getting Started

### Prerequisites

- Python 3.10+ (3.13 recommended)
- An OpenAI API key
- A Langfuse account with prompts configured (see [Prompt-Driven Rule System](#prompt-driven-rule-system))

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd ai_compliance_check

# Create and activate virtual environment
python -m venv myenv
# Windows
myenv\Scripts\activate
# Linux/Mac
source myenv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Quick Start

```bash
# 1. Create .env file (see Environment Variables section for all options)
cp .env.example .env   # or create manually

# 2. Run the API
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 3. Open Swagger UI
# http://localhost:8000/docs
```

---

## Environment Variables

Create a `.env` file in the project root:

```env
# === Required ===
OPENAI_API_KEY=sk-your-openai-key
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
SERVICE_API_KEY=sk-service-your-generated-key

# === Optional ===
LANGFUSE_HOST=https://cloud.langfuse.com       # Default: Langfuse Cloud
JWT_SECRET_KEY=your-secure-random-key           # Auto-generated if missing
JWT_ALGORITHM=HS256                             # Default: HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15                  # Default: 15
REFRESH_TOKEN_EXPIRE_DAYS=7                     # Default: 7
FRONTEND_URL=http://localhost:3000              # CORS origin
```

Generate a secure service API key:
```bash
python -c "import secrets; print('sk-service-' + secrets.token_urlsafe(32))"
```

**Priority:** `.env` file values take precedence, then system environment variables.

---

## Running the API

### Development

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker

```bash
# Development (hot-reload enabled)
docker-compose up --build

# Production (multi-worker, no hot-reload)
docker-compose -f docker-compose.prod.yml up -d --build

# View logs
docker-compose logs -f api
```

API available at: `http://localhost:8000/docs` (Swagger UI)

---

## Authentication

The API supports **dual authentication** - every request to `/check_compliance` must include one of the following:

### JWT Bearer Token (for frontend users)

```bash
# 1. Register a user
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "email": "user@example.com", "password": "securepass", "full_name": "My User"}'

# 2. Login to get tokens
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "password": "securepass"}'

# 3. Use the access_token in requests
curl -X POST http://localhost:8000/check_compliance \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d @test_data/sample_request_small.json
```

### API Key (for automated services / cron jobs)

```bash
curl -X POST http://localhost:8000/check_compliance \
  -H "X-API-Key: sk-service-your-key-here" \
  -H "Content-Type: application/json" \
  -d @test_data/sample_request_small.json
```

### Auth Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login, returns access + refresh tokens |
| POST | `/auth/refresh` | Refresh an expired access token |
| POST | `/auth/logout` | Logout (clears refresh token cookie) |
| GET | `/auth/me` | Get current authenticated user info |

> **Note:** The current user store is in-memory (demo). Replace with a real database (PostgreSQL, etc.) for production.

---

## API Endpoints

### `GET /` - Health Check

```bash
curl http://localhost:8000/
```

```json
{"status": "ok", "message": "AI Compliance Checker API is running!"}
```

### `POST /check_compliance` - Compliance Check

**Requires authentication** (JWT or API Key).

**Request:**
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
            "CheckColumns": "Remarks"
        }
    ],
    "Data": [
        {
            "mlsnum": "123456OD",
            "mlsId": "TESTMLS",
            "Remarks": "Beautiful family home in a great neighborhood",
            "PrivateRemarks": "Seller is motivated"
        }
    ]
}
```

**Valid CheckColumns:** `Remarks`, `PrivateRemarks`, `Directions`, `ShowingInstructions`, `ConfidentialRemarks`, `SupplementRemarks`, `Concessions`, `SaleFactors`

**Response:**
```json
{
    "ok": 200,
    "results": [
        {
            "mlsnum": "123456OD",
            "mlsId": "TESTMLS",
            "FAIR": {
                "Remarks": [{"violation": "family", "explanation": "..."}],
                "PrivateRemarks": [],
                "Total_tokens": 628
            },
            "COMP": null,
            "latency": 2.34,
            "tokens_used": 1074
        }
    ],
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "error_message": "",
    "total_tokens": 1074,
    "elapsed_time": 2.34
}
```

**Key behaviors:**
- Each rule in the response is `null` when no violations are found (all field arrays empty).
- Each record's `mlsId` must match at least one rule's `mlsId`.
- Duplicate `(ID, mlsId)` rule entries are merged (column union).
- The `mlsIds` field name is accepted as a typo alias for `mlsId`.

---

## Prompt-Driven Rule System

Rules are defined entirely in **Langfuse** as prompt templates - no custom Python code per rule. To add a new rule, create a Langfuse prompt. To modify a rule, update the prompt in Langfuse.

### Prompt Naming Convention

| Priority | Name Format | Example |
|---|---|---|
| 1 (custom) | `{RULE_ID}_{MLS_ID}_violation` | `FAIR_TESTMLS_violation` |
| 2 (default) | `{RULE_ID}_violation` | `FAIR_violation` |

The system first tries the MLS-specific prompt, then falls back to the default. If neither exists, the request returns a `400` error.

### Prompt Template Variables

Prompts are Jinja2 templates. The following variables are available:

| Variable | Source Field |
|---|---|
| `{{ public_remarks }}` | Remarks |
| `{{ private_agent_remarks }}` | PrivateRemarks |
| `{{ directions }}` | Directions |
| `{{ showing_instructions }}` | ShowingInstructions |
| `{{ confidential_remarks }}` | ConfidentialRemarks |
| `{{ supplement_remarks }}` | SupplementRemarks |
| `{{ concessions }}` | Concessions |
| `{{ sale_factors }}` | SaleFactors |

### Prompt Config

The Langfuse prompt config object controls the OpenAI model parameters:

```json
{
    "model": "gpt-4o",
    "temperature": "0.0",
    "max_output_tokens": "6095",
    "top_p": "1.0"
}
```

### Adding a New Rule

1. Create a prompt in Langfuse named `NEWRULE_violation` (or `NEWRULE_YOURMLS_violation` for MLS-specific).
2. Write the Jinja2 template using the variables above.
3. Set the config with model parameters.
4. Send a request with `"ID": "NEWRULE"` - no code changes needed.

---

## Dynamic Rate Limiting

The rate limiter reads OpenAI's response headers to track token and request budgets in real time, preventing 429 errors through predictive throttling.

### Headers Tracked

- `x-ratelimit-limit-tokens` / `x-ratelimit-remaining-tokens` / `x-ratelimit-reset-tokens`
- `x-ratelimit-limit-requests` / `x-ratelimit-remaining-requests` / `x-ratelimit-reset-requests`

### Concurrency Adjustment

| Remaining Budget | Concurrency |
|---|---|
| > 50% | 200 (aggressive) |
| 20-50% | 10-200 (linear scale) |
| 10-20% | 10 (conservative) |
| < 10% | 5 (critical) |

### Token Estimation

- **Input tokens:** `text_length / 4` (conservative)
- **Output tokens:** 6590 (max budget)
- Processing pauses when remaining tokens drop below 10%

---

## Retry & Error Handling

### Exponential Backoff

Failed API calls are retried with exponential backoff and jitter:

| Attempt | Wait Time |
|---|---|
| 1 | 1-2s |
| 2 | 2-3s |
| 3 | 4-5s |
| Max | Capped at 16s |

### Retryable Errors

- `RateLimitError` (429)
- `APITimeoutError`
- `APIError` (500, 502, 503, 504)
- `ConnectionError`, `TimeoutError`, `OSError`

### Non-Retryable Errors

- Client errors (400, 401, 403, 404) fail immediately.

### Per-Record Error Isolation

A failure in one record does not fail the entire batch. Each record's errors are captured individually and included in the response.

---

## Request Tracing & Logging

### Request ID Middleware

Every request receives a UUID (`X-Request-ID` response header) that:
- Propagates through all async operations via `ContextVar`
- Creates a per-request log file: `logs/request_{uuid}.log`
- Is included in the API response as `request_id`
- Appears in all log entries for that request

### Log Levels

| Level | Usage |
|---|---|
| **INFO** | Request lifecycle, batch stats, startup/shutdown |
| **DEBUG** | Rule execution traces, token counts, prompt versions |
| **WARNING** | Missing mappings, partial failures |
| **ERROR** | Failures with full stack traces |

### Log Output

1. **Console (stdout):** Real-time during development
2. **Per-request files** (`logs/request_{uuid}.log`): Isolated logs per request

### Logger Names

| Logger | Scope |
|---|---|
| `api.routes` | API endpoints & request processing |
| `api.rules` | Rule execution & OpenAI interactions |
| `api.main` | Application lifecycle |
| `prompt` | Langfuse prompt loading |
| `test.api` | Test execution |

---

## Connection Pooling & Performance

### HTTP/2 Connection Pool

The OpenAI client uses a shared `httpx.AsyncClient` with:
- **200** max concurrent connections
- **50** keep-alive connections
- **30s** per-request timeout
- **10 min** total batch timeout

Benefits: TCP connection reuse eliminates handshake overhead under high concurrency.

### Async Processing

- `AsyncOpenAI` for non-blocking API calls
- All rules for a record execute in parallel via `asyncio.gather`
- Records processed in chunks of 100 with dynamic concurrency adjustment between chunks
- `asyncio.Semaphore` controls concurrent API calls

### Performance Metrics

Every response includes:
- `elapsed_time`: Total request processing time
- `total_tokens`: Cumulative tokens across all API calls
- Per-record `latency` and `tokens_used`
- Rate limiter stats logged after each batch

---

## Testing

### Running Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=app --cov-report=term-missing

# Run a specific test file
pytest tests/test_endpoints.py -v
```

### Test Suite

| File | Covers |
|---|---|
| `test_auth.py` | JWT authentication & user management |
| `test_api_key_auth.py` | API key authentication |
| `test_endpoints.py` | API endpoint functionality |
| `test_integration.py` | End-to-end request flows |
| `test_rate_limiter.py` | Dynamic rate limiting logic |
| `test_registry.py` | Rule registry & dispatcher |
| `test_rules.py` | Rule execution & OpenAI interaction |
| `test_prompt_cache.py` | Langfuse prompt loading |
| `test_request_id.py` | Request ID middleware |
| `test_utils.py` | JSON response parser |

**99 tests | 100% pass rate | 89% code coverage**

OpenAI and Langfuse are mocked for reproducible, offline tests.

---

## Docker Deployment

### Development

```bash
docker-compose up --build
```

- Hot-reload enabled (`--reload`)
- Source code mounted as volume
- Logs persisted to `./logs`

### Production

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

- 4 Uvicorn workers (no hot-reload)
- `restart: always`
- Resource limits: 2 CPUs, 4GB RAM
- Only logs volume mounted (no source code)

### Health Check

Both configurations include a health check at `http://localhost:8000/health` (30s interval, 3 retries).

See [DOCKER_GUIDE.md](DOCKER_GUIDE.md) for detailed Docker instructions.

---

## Configuration Reference

All configuration lives in `app/core/config.py`. Key settings:

### Token Settings

| Setting | Default | Description |
|---|---|---|
| `MAX_OUTPUT_TOKENS` | 6590 | Max output tokens per OpenAI response |
| `CHARS_PER_TOKEN` | 4 | Characters per token (estimation) |

### Rate Limiting

| Setting | Default | Description |
|---|---|---|
| `SAFETY_MARGIN` | 0.90 | Use 90% of available limits |
| `MIN_REMAINING_TOKENS_PCT` | 0.10 | Pause at 10% remaining |

### Concurrency

| Setting | Default | Description |
|---|---|---|
| `MIN_CONCURRENCY` | 10 | Conservative mode |
| `MAX_CONCURRENCY` | 200 | Aggressive mode |
| `DEFAULT_CONCURRENCY` | 50 | Starting concurrency |

### Retry

| Setting | Default | Description |
|---|---|---|
| `MAX_RETRIES` | 3 | Max retry attempts |
| `BASE_RETRY_DELAY` | 1.0s | Initial backoff delay |
| `MAX_RETRY_DELAY` | 16.0s | Max backoff cap |
| `JITTER_RANGE` | 1.0s | Random jitter (0-1s) |

### Connection Pool

| Setting | Default | Description |
|---|---|---|
| `MAX_CONNECTIONS` | 200 | Max concurrent HTTP connections |
| `MAX_KEEPALIVE_CONNECTIONS` | 50 | Keep-alive pool size |
| `API_TIMEOUT` | 30.0s | Per-request timeout |
| `REQUEST_TIMEOUT` | 600.0s | Total batch timeout (10 min) |

### Token Budget Thresholds

| Setting | Default | Description |
|---|---|---|
| `HIGH_BUDGET_THRESHOLD` | 0.50 | > 50% remaining: use MAX_CONCURRENCY |
| `MEDIUM_BUDGET_THRESHOLD` | 0.20 | 20-50%: scale linearly |
| `LOW_BUDGET_THRESHOLD` | 0.10 | < 10%: use MIN_CONCURRENCY |
