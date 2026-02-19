"""
Admin routes for prompt-cache management.

Endpoints (all require authentication via API Key or JWT):
  POST /admin/cache/refresh  — Refresh specific or all cached prompts
  POST /admin/cache/clear    — Clear the entire prompt cache
  GET  /admin/cache/stats    — View cache statistics and TTL info
"""

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from typing import Any, Dict, Optional

from app.auth.dependencies import verify_authentication
from app.core.prompt_cache import get_prompt_cache_manager
from app.core.logger import api_logger

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_authentication)],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CacheRefreshRequest(BaseModel):
    """Optional body for ``POST /admin/cache/refresh``.

    - Omit both fields (or send ``{}``) to refresh **all** cached prompts.
    - Provide ``rule_id`` alone to refresh every MLS entry for that rule.
    - Provide ``rule_id`` + ``mls_id`` to refresh a single prompt.
    """
    rule_id: Optional[str] = None
    mls_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/cache/refresh")
async def refresh_cache(
    body: Optional[CacheRefreshRequest] = Body(default=None),

) -> Dict[str, Any]:
    """Refresh cached prompts from Langfuse.

    - **No body / empty body** → refresh ALL cached prompts.
    - **rule_id only** → refresh every MLS entry for that rule.
    - **rule_id + mls_id** → refresh one specific prompt.
    """
    cache = get_prompt_cache_manager()

    if body and body.rule_id and body.mls_id:
        # Single prompt refresh
        result = await cache.refresh_prompt(body.rule_id, body.mls_id)
        api_logger.info(
            f"Admin refresh: ({body.rule_id.upper()}, {body.mls_id}) — "
            f"found={result is not None}"
        )
        return {
            "message": f"Refreshed prompt ({body.rule_id.upper()}, {body.mls_id})",
            "found": result is not None,
            "stats": cache.get_cache_stats(),
        }

    if body and body.rule_id:
        # Refresh all entries under a specific rule
        stats = await cache.refresh_rule(body.rule_id)
        api_logger.info(f"Admin refresh: all entries for rule {body.rule_id.upper()}")
        return {
            "message": f"Refreshed all prompts for rule {body.rule_id.upper()}",
            "stats": stats,
        }

    # Refresh everything
    stats = await cache.refresh_all_prompts()
    api_logger.info("Admin refresh: all cached prompts")
    return {
        "message": "Refreshed all cached prompts",
        "stats": stats,
    }


@router.post("/cache/clear")
async def clear_cache() -> Dict[str, Any]:
    """Clear the entire prompt cache.

    Prompts will be re-fetched from Langfuse on the next compliance request.
    """
    cache = get_prompt_cache_manager()
    cache.clear_cache()
    api_logger.info("Admin action: prompt cache cleared")
    return {
        "message": "Cache cleared successfully",
        "stats": cache.get_cache_stats(),
    }


@router.get("/cache/stats")
async def cache_stats() -> Dict[str, Any]:
    """Return current prompt-cache statistics including TTL configuration."""
    cache = get_prompt_cache_manager()
    return cache.get_cache_stats()
