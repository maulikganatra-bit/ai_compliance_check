"""
Prompt Cache Manager for Langfuse Integration

Naming convention (no env-var configuration needed):
  - Default prompt : {RULE_ID}_violation          e.g. FAIR_violation
  - Custom prompt  : {RULE_ID}_{MLS_ID}_violation  e.g. FAIR_MIAMI_violation

Lookup strategy (per request):
  1. Check in-memory cache.
  2. On cache-miss: try custom name → fall back to default name.
  3. Cache the result so Langfuse is never hit twice for the same pair.

Cache structure:
  {
      "FAIR": {                        # rule_id is always uppercased
          "default": <prompt_data>,   # real Langfuse prompt object
          "Miami":   <prompt_data>,   # real custom prompt — MLS ID preserved as-is
          "Miami1":  "USE_DEFAULT",   # sentinel: no custom exists, resolve to default
      },
      "COMP": {
          "default": <prompt_data>,
      },
      ...
  }

rule_id  : always uppercased (FAIR, COMP, PRWD …) — controlled by us.
mls_id   : stored EXACTLY as received — case-sensitive, controlled by the caller.
           "Miami" and "MIAMI" are therefore different cache keys.

The "USE_DEFAULT" sentinel is a plain Python string stored in our own dict,
so Langfuse's background refresh thread can never evict it. On every read
the sentinel is resolved to the current default prompt data transparently.
"""

# Sentinel stored in our cache when a custom prompt does not exist in Langfuse.
# Using a string (not None) lets _get_from_cache distinguish "not yet looked up"
# (returns None) from "looked up, no custom exists" (returns _USE_DEFAULT).
_USE_DEFAULT = "USE_DEFAULT"

from typing import Dict, Tuple, Optional, Any
import asyncio
from app.core.logger import api_logger
from app.core.config import LANGFUSE_CLIENT
from app.rules.registry import DEFAULT_RULE_FUNCTIONS


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def _custom_prompt_name(rule_id: str, mls_id: str) -> str:
    """Return the Langfuse prompt name for a custom (MLS-specific) prompt.
    rule_id is uppercased; mls_id is used exactly as provided (case-sensitive).
    """
    return f"{rule_id.upper()}_{mls_id}_violation"


def _default_prompt_name(rule_id: str) -> str:
    """Return the Langfuse prompt name for the default (generic) prompt."""
    return f"{rule_id.upper()}_violation"


# Note: rule_id keys are always uppercased; mls_id keys are stored verbatim.
# The only reserved mls key is the literal string "default" (lowercase).


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class PromptCacheManager:
    """
    Manages prompt loading and caching from Langfuse.

    Cache is a two-level dict:  rule_id (uppercased)  →  mls_id (verbatim)  →  prompt_data
    The reserved mls key "default" (lowercase) holds the fallback prompt.
    MLS IDs are case-sensitive: "Miami" and "MIAMI" are distinct cache entries.

    No environment variables are needed – prompt names are derived
    automatically from the rule/MLS identifiers.
    """

    _instance = None
    _initialized = False

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            # cache: { "FAIR": {"default": {...}, "MIAMI": {...}}, ... }
            self._cache: Dict[str, Dict[str, Any]] = {}
            self._lock = asyncio.Lock()
            PromptCacheManager._initialized = True
            api_logger.info("PromptCacheManager initialised")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_from_cache(self, rule_id: str, mls_id: str) -> Optional[Dict[str, Any]]:
        """
        Return cached prompt data, or None on a true cache-miss.

        rule_id is normalised to uppercase for lookup.
        mls_id is used exactly as provided (case-sensitive).

        Transparently resolves the _USE_DEFAULT sentinel: if the MLS key
        maps to _USE_DEFAULT, the default prompt for that rule is returned
        instead, so callers never see the sentinel.
        """
        value = self._cache.get(rule_id.upper(), {}).get(mls_id)
        if value is _USE_DEFAULT:
            # Sentinel hit: no custom prompt exists — resolve to default
            return self._cache.get(rule_id.upper(), {}).get("default")
        return value

    def _store_in_cache(self, rule_id: str, mls_id: str, prompt_data: Dict[str, Any]) -> None:
        """Write prompt data into the nested cache.
        rule_id is uppercased; mls_id is stored verbatim (case-sensitive).
        """
        rule_key = rule_id.upper()
        if rule_key not in self._cache:
            self._cache[rule_key] = {}
        self._cache[rule_key][mls_id] = prompt_data
        api_logger.debug(f"Cached prompt [{rule_key}][{mls_id}]")

    async def _fetch_from_langfuse(self, prompt_name: str) -> Optional[Any]:
        """Fetch a single prompt object from Langfuse (runs in executor)."""
        loop = asyncio.get_event_loop()
        try:
            prompt = await loop.run_in_executor(
                None,
                lambda: LANGFUSE_CLIENT.get_prompt(prompt_name)
            )
            return prompt
        except Exception as e:
            # Langfuse raises when a prompt is not found – treat as None
            api_logger.debug(f"Langfuse fetch failed for '{prompt_name}': {e}")
            return None

    def _build_prompt_data(
        self, prompt_obj: Any, prompt_name: str, rule_id: str, mls_id: str
    ) -> Dict[str, Any]:
        """Convert a raw Langfuse prompt object into our standard dict."""
        return {
            "name": prompt_name,
            "prompt": prompt_obj.prompt,
            "config": prompt_obj.config,
            "version": getattr(prompt_obj, "version", None),
            "rule_id": rule_id,
            "mls_id": mls_id,
        }

    # ------------------------------------------------------------------
    # Core load logic  (custom → default fallback)
    # ------------------------------------------------------------------

    async def _load_prompt(self, rule_id: str, mls_id: str) -> Optional[Dict[str, Any]]:
        """
        Load one prompt from Langfuse using the auto-discovery strategy:
          1. Try  {RULE_ID}_{mls_id}_violation  (custom, mls_id as-is)
          2. Fall back to  {RULE_ID}_violation  (default)

        The result is stored in the cache before returning.
        rule_id is normalised to uppercase; mls_id is preserved as provided.
        """
        rule_id_upper = rule_id.upper()
        is_default_request = mls_id == "default"

        # --- Step 1: try custom prompt (only when not explicitly asking for default) ---
        if not is_default_request:
            custom_name = _custom_prompt_name(rule_id_upper, mls_id)
            prompt_obj = await self._fetch_from_langfuse(custom_name)
            if prompt_obj:
                prompt_data = self._build_prompt_data(prompt_obj, custom_name, rule_id_upper, mls_id)
                self._store_in_cache(rule_id_upper, mls_id, prompt_data)
                api_logger.info(f"Loaded custom prompt '{custom_name}' for ({rule_id_upper}, {mls_id})")
                return prompt_data

            api_logger.debug(
                f"No custom prompt found for ({rule_id_upper}, {mls_id}), "
                f"falling back to default"
            )
            # Store sentinel so future cache lookups for this MLS key resolve
            # to default WITHOUT ever touching Langfuse again.
            rule_bucket = self._cache.setdefault(rule_id_upper, {})
            rule_bucket[mls_id] = _USE_DEFAULT
            api_logger.debug(f"Stored USE_DEFAULT sentinel [{rule_id_upper}][{mls_id}]")

        # --- Step 2: try / reuse default ---
        # Check if default is already cached (avoids a Langfuse call).
        # The sentinel is already stored above, so _get_from_cache will resolve
        # this MLS key to the default automatically — nothing more to store.
        cached_default = self._get_from_cache(rule_id_upper, "default")
        if cached_default:
            return cached_default

        default_name = _default_prompt_name(rule_id_upper)
        prompt_obj = await self._fetch_from_langfuse(default_name)
        if prompt_obj:
            prompt_data = self._build_prompt_data(prompt_obj, default_name, rule_id_upper, "default")
            # Always cache under the reserved "default" key
            self._store_in_cache(rule_id_upper, "default", prompt_data)
            # Note: MLS key already has the _USE_DEFAULT sentinel stored above,
            # so _get_from_cache will resolve it to this default data automatically.
            api_logger.info(f"Loaded default prompt '{default_name}' for rule '{rule_id_upper}'")
            return prompt_data

        api_logger.error(
            f"No prompt found in Langfuse for rule '{rule_id_upper}' "
            f"(tried: '{_custom_prompt_name(rule_id_upper, mls_id)}' "
            f"and '{default_name}')"
        )
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Warm the cache by preloading default prompts for all known rules.

        Called once at application startup.  Individual MLS-specific prompts
        are loaded on-demand when a request arrives.
        """
        async with self._lock:
            if self._cache:
                api_logger.warning("Prompt cache already initialised – skipping")
                return

            if LANGFUSE_CLIENT is None:
                raise RuntimeError("LANGFUSE_CLIENT is not initialised in config")

            api_logger.info("Warming prompt cache with default prompts …")
            rule_ids = list(DEFAULT_RULE_FUNCTIONS.keys())

            tasks = [self._load_prompt(rule_id, "default") for rule_id in rule_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            ok = sum(1 for r in results if isinstance(r, dict))
            api_logger.info(
                f"Cache warm-up complete: {ok}/{len(rule_ids)} default prompts loaded"
            )

    async def get_prompt(self, rule_id: str, mls_id: str) -> Optional[Dict[str, Any]]:
        """
        Return the prompt for (rule_id, mls_id).

        Cache hit  → returned instantly.
        Cache miss → auto-discovered from Langfuse and cached for next time.
        """
        # Fast path – cache hit
        cached = self._get_from_cache(rule_id, mls_id)
        if cached:
            api_logger.debug(f"Cache hit: ({rule_id.upper()}, {mls_id})")
            return cached

        # Slow path – load from Langfuse
        api_logger.debug(f"Cache miss: ({rule_id.upper()}, {mls_id}) – fetching from Langfuse")
        return await self._load_prompt(rule_id, mls_id)

    async def load_batch_prompts(
        self,
        rule_mls_pairs: list[Tuple[str, str]],
    ) -> Dict[Tuple[str, str], Optional[Dict[str, Any]]]:
        """
        Ensure prompts for all (rule_id, mls_id) pairs are in cache.

        Pairs already cached are returned immediately; missing ones are
        fetched from Langfuse concurrently.

        Returns:
            { (rule_id, mls_id): prompt_data_or_None }
        """
        api_logger.info(f"Batch-loading {len(rule_mls_pairs)} prompts")
        api_logger.info(f"Cache state: {self.get_cache_stats()['cache']}")

        # Separate cache hits from misses
        to_load = [
            pair for pair in rule_mls_pairs
            if self._get_from_cache(*pair) is None
        ]

        if to_load:
            api_logger.debug(f"Fetching {len(to_load)} prompts from Langfuse")
            tasks = [self._load_prompt(rule_id, mls_id) for rule_id, mls_id in to_load]
            await asyncio.gather(*tasks, return_exceptions=True)

        return {pair: self._get_from_cache(*pair) for pair in rule_mls_pairs}

    async def refresh_prompt(self, rule_id: str, mls_id: str) -> Optional[Dict[str, Any]]:
        """Force-reload a specific prompt from Langfuse (bypasses cache).
        mls_id must be provided exactly as it was originally cached (case-sensitive).
        """
        api_logger.info(f"Refreshing prompt: ({rule_id.upper()}, {mls_id})")

        # Evict from cache (mls_id used verbatim)
        rule_key = rule_id.upper()
        if rule_key in self._cache:
            self._cache[rule_key].pop(mls_id, None)

        return await self._load_prompt(rule_id, mls_id)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return a snapshot of cache contents for observability."""
        cache_view: Dict[str, Any] = {}
        total_real = 0
        total_sentinel = 0
        print("-"*60)
        print(self._cache)
        print("-"*60)
        for rule_id, mls_map in self._cache.items():
            real = [k for k, v in mls_map.items() if v is not _USE_DEFAULT]
            sentinel = [k for k, v in mls_map.items() if v is _USE_DEFAULT]
            cache_view[rule_id] = {"loaded": real, "uses_default": sentinel}
            total_real += len(real)
            total_sentinel += len(sentinel)
        return {
            "total_prompts_cached": total_real,
            "total_sentinel_entries": total_sentinel,
            "cache": cache_view,
        }

    def clear_cache(self) -> None:
        """Evict all cached prompts (useful for testing)."""
        api_logger.info("Clearing prompt cache")
        self._cache.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_prompt_cache_manager = PromptCacheManager()


def get_prompt_cache_manager() -> PromptCacheManager:
    """Return the global PromptCacheManager singleton."""
    return _prompt_cache_manager