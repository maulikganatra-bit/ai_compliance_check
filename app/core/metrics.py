"""Prometheus metrics definitions for the AI Compliance Checker API.

This module centralizes all metric objects:
- Automatic HTTP metrics via prometheus-fastapi-instrumentator
- Custom domain-specific counters, histograms, and gauges
"""

from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator

# --------------------------------------------------------------------------
# Automatic HTTP Metrics (via prometheus-fastapi-instrumentator)
# --------------------------------------------------------------------------
# Automatically tracks:
# - http_requests_total (counter by method, handler, status)
# - http_request_duration_seconds (histogram by handler)
# - http_requests_in_progress (gauge)

instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    excluded_handlers=["/metrics"],
    inprogress_name="http_requests_in_progress",
    inprogress_labels=True,
)

# --------------------------------------------------------------------------
# Custom Domain Metrics
# --------------------------------------------------------------------------

# Counter: Track APIResponse.ok custom status codes
# Codes: 200, 400, 401, 429, 500, 601 (prompt not found),
#         602 (OpenAI timeout), 603 (OpenAI rate limit), 604 (parse error)
COMPLIANCE_STATUS_COUNTER = Counter(
    "compliance_response_status_total",
    "Count of compliance API responses by custom status code",
    ["code", "endpoint"],
)

# Counter: Total tokens consumed
TOKEN_USAGE_COUNTER = Counter(
    "compliance_tokens_used_total",
    "Total OpenAI tokens consumed",
    ["endpoint"],
)

# Histogram: Token usage distribution per request
TOKEN_USAGE_HISTOGRAM = Histogram(
    "compliance_tokens_per_request",
    "Distribution of tokens used per compliance request",
    ["endpoint"],
    buckets=[100, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000],
)

# Counter: OpenAI-specific error conditions
OPENAI_ERROR_COUNTER = Counter(
    "compliance_openai_errors_total",
    "Count of OpenAI API errors by type",
    ["error_type"],  # timeout, rate_limit, parse_error, api_error
)

# Gauge: Records currently being processed
RECORDS_IN_PROCESSING = Gauge(
    "compliance_records_in_processing",
    "Number of MLS records currently being processed",
)

# Histogram: Per-record processing latency
RECORD_LATENCY_HISTOGRAM = Histogram(
    "compliance_record_processing_seconds",
    "Time to process a single MLS record",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
