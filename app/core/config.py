"""Configuration settings for rate limiting and OpenAI API.

This module centralizes all configurable parameters for:
- OpenAI token estimation and limits
- Rate limiting safety margins
- Concurrency control
- Retry behavior
- Connection pooling
- Performance thresholds

Modify these values to tune performance based on your OpenAI tier and requirements.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ============================================================================
# OPENAI API KEY CONFIGURATION
# ============================================================================
# Load API key from .env file if it exists, otherwise use environment variable

def get_openai_api_key() -> str:
    """Get OpenAI API key from .env file or environment variable.
    
    Priority:
    1. If .env file exists, load from there
    2. Otherwise, use OS environment variable
    
    Returns:
        str: OpenAI API key
        
    Raises:
        ValueError: If API key is not found in either location
    """
    # Check if .env file exists in project root
    env_file = Path(__file__).parent.parent.parent / ".env"
    
    if env_file.exists():
        # Load from .env file
        load_dotenv(env_file)
    
    # Get API key from environment (works for both .env and OS env vars)
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY not found. Please set it in:\n"
            "  1. .env file in project root, OR\n"
            "  2. System environment variable\n"
            "Example: OPENAI_API_KEY=sk-your-key-here"
        )
    
    return api_key

# Load and validate API key on module import
OPENAI_API_KEY = get_openai_api_key()

# ============================================================================
# OPENAI TOKEN SETTINGS
# ============================================================================
# These settings control token estimation for rate limiting

MAX_OUTPUT_TOKENS = 6590  # Maximum output tokens (set in OpenAI playground)
                          # Used to estimate total tokens per request
CHARS_PER_TOKEN = 4       # Conservative estimate: 4 characters ≈ 1 token
                          # Used for input token estimation

# ============================================================================
# RATE LIMIT SAFETY SETTINGS
# ============================================================================
# These prevent hitting OpenAI rate limits by staying below thresholds

SAFETY_MARGIN = 0.90              # Use only 90% of available limits
                                   # Leaves 10% buffer for safety
MIN_REMAINING_TOKENS_PCT = 0.10   # Pause processing when below 10% remaining
                                   # Prevents exhausting token budget

# ============================================================================
# CONCURRENCY SETTINGS
# ============================================================================
# Controls how many API calls run simultaneously
# Higher concurrency = faster processing but more aggressive

MIN_CONCURRENCY = 10       # Minimum concurrent API calls (conservative mode)
MAX_CONCURRENCY = 200      # Maximum concurrent API calls (aggressive mode)
DEFAULT_CONCURRENCY = 50   # Starting concurrency (moderate mode)

# Note: Actual concurrency adjusts dynamically based on remaining rate limit budget

# ============================================================================
# RETRY SETTINGS
# ============================================================================
# Exponential backoff retry configuration for failed API calls

MAX_RETRIES = 3           # Maximum retry attempts per request
BASE_RETRY_DELAY = 1.0    # Base delay in seconds (1s → 2s → 4s → 8s)
MAX_RETRY_DELAY = 16.0    # Cap maximum delay at 16 seconds
JITTER_RANGE = 1.0        # Add random jitter (0-1s) to prevent thundering herd

# ============================================================================
# TIMEOUT SETTINGS
# ============================================================================

API_TIMEOUT = 30.0         # Timeout per individual API call (30 seconds)
REQUEST_TIMEOUT = 600.0    # Total request timeout (10 minutes for large batches)

# ============================================================================
# CONNECTION POOL SETTINGS
# ============================================================================
# HTTP/2 connection pooling for efficient connection reuse

MAX_CONNECTIONS = 200              # Maximum concurrent HTTP connections
MAX_KEEPALIVE_CONNECTIONS = 50     # Number of connections to keep alive
                                    # Benefits: Reduces TCP handshake overhead

# ============================================================================
# WAVE-BASED PROCESSING (Future Enhancement)
# ============================================================================
# Settings for processing large batches in waves

WAVE_SIZE = 1200           # Number of API calls per wave
WAVE_CHECK_INTERVAL = 5    # Check rate limits every 5 seconds

# ============================================================================
# TOKEN BUDGET THRESHOLDS
# ============================================================================
# Dynamic concurrency adjustment based on remaining token budget

HIGH_BUDGET_THRESHOLD = 0.50    # >50% remaining → Use MAX_CONCURRENCY (200)
MEDIUM_BUDGET_THRESHOLD = 0.20  # 20-50% remaining → Scale linearly
LOW_BUDGET_THRESHOLD = 0.10     # <10% remaining → Use MIN_CONCURRENCY (10)
