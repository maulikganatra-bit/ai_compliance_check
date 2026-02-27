"""
Prompt Manager for Langfuse Integration

Naming convention (no env-var configuration needed):
  - Default prompt : {RULE_ID}_violation          e.g. FAIR_violation
  - Custom prompt  : {RULE_ID}_{MLS_ID}_violation  e.g. FAIR_MIAMI_violation

Lookup strategy (per request):
  1. Try custom name -> fall back to default name.
  2. Returns prompt data directly -- no caching.

Every request fetches fresh prompts from Langfuse to ensure the latest
version is always used.  This eliminates cache staleness, TTL management,
and admin cache endpoints at the cost of one Langfuse API call per
(rule, mls) pair per request.

rule_id  : always uppercased (FAIR, COMP, PRWD ...) -- controlled by us.
mls_id   : used EXACTLY as received -- case-sensitive, controlled by the caller.
           "Miami" and "MIAMI" are therefore different lookups.
"""

from typing import Dict, Tuple, Optional, Any
import asyncio
from app.core.logger import api_logger, prompt_logger
from app.core.config import LANGFUSE_CLIENT
from app.core.prompt_replica_store import PromptStore
import json


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


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class PromptManager:
    """
    Manages prompt loading from Langfuse.

    Every call fetches prompts directly from Langfuse -- no caching.
    This guarantees the latest prompt version is always used.

    Lookup strategy per (rule_id, mls_id) pair:
      1. Try custom prompt: {RULE_ID}_{mls_id}_violation
      2. Fall back to default: {RULE_ID}_violation
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
            PromptManager._initialized = True
            api_logger.info("PromptManager initialised (no-cache mode)")
            # initialize local prompt store for Langfuse fallback
            try:
                self._store = PromptStore()
                self._store.init_db()
            except Exception as e:
                api_logger.error(f"Failed to initialize PromptStore for fallback: {e}")
                self._store = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
            api_logger.debug(f"Langfuse fetch failed for '{prompt_name}': {e}")
            # Fall back to local PromptStore if available
            if getattr(self, "_store", None) is not None:
                try:
                    local = self._store.get_latest_prompt(prompt_name)
                    if local:
                        # convert to a simple dict-like object
                        api_logger.info(f"Using local prompt replica for '{prompt_name}' v{local.get('version')}")
                        return local
                except Exception as ex:
                    api_logger.error(f"PromptStore fallback failed for '{prompt_name}': {ex}")
            return None

    def _build_prompt_data(
        self, prompt_obj: Any, prompt_name: str, rule_id: str, mls_id: str
    ) -> Dict[str, Any]:
        """Convert a raw Langfuse prompt object into our standard dict."""
        # support both Langfuse objects (attributes) and local dicts (keys)
        if isinstance(prompt_obj, dict):
            raw_prompt = prompt_obj.get("prompt")
            raw_config = prompt_obj.get("config")
            raw_version = prompt_obj.get("version")
        else:
            # fallback to attribute access for Langfuse SDK objects
            raw_prompt = getattr(prompt_obj, "prompt", None)
            raw_config = getattr(prompt_obj, "config", None)
            raw_version = getattr(prompt_obj, "version", None)

        # Normalize prompt to a string suitable for Jinja2 Template
        prompt_val = None
        try:
            if isinstance(raw_prompt, (list, dict)):
                prompt_val = json.dumps(raw_prompt)
            elif raw_prompt is None:
                prompt_val = ""
            else:
                prompt_val = str(raw_prompt)
        except Exception:
            prompt_val = str(raw_prompt) if raw_prompt is not None else ""

        # Normalize config to a dict (Template expects dict-like access later)
        config_val = {}
        try:
            if isinstance(raw_config, dict):
                config_val = raw_config
            elif isinstance(raw_config, str):
                try:
                    config_val = json.loads(raw_config)
                except Exception:
                    config_val = {}
            elif raw_config is None:
                config_val = {}
            else:
                # unknown type, attempt to convert
                config_val = dict(raw_config)
        except Exception:
            config_val = {}

        return {
            "name": prompt_name,
            "prompt": prompt_val,
            "config": config_val,
            "version": raw_version,
            "rule_id": rule_id,
            "mls_id": mls_id,
        }

    # ------------------------------------------------------------------
    # Core load logic  (custom -> default fallback)
    # ------------------------------------------------------------------

    async def _load_prompt(self, rule_id: str, mls_id: str) -> Optional[Dict[str, Any]]:
        """
        Load one prompt from Langfuse:
          1. Try  {RULE_ID}_{mls_id}_violation  (custom, mls_id as-is)
          2. Fall back to  {RULE_ID}_violation  (default)

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
                prompt_logger.info(
                    "Loaded custom prompt '%s' v%s for (%s, %s)",
                    custom_name, prompt_data.get('version'), rule_id_upper, mls_id,
                )
                return prompt_data

            api_logger.debug(
                f"No custom prompt found for ({rule_id_upper}, {mls_id}), "
                f"falling back to default"
            )

        # --- Step 2: load default ---
        default_name = _default_prompt_name(rule_id_upper)
        prompt_obj = await self._fetch_from_langfuse(default_name)
        if prompt_obj:
            prompt_data = self._build_prompt_data(prompt_obj, default_name, rule_id_upper, "default")
            prompt_logger.info(
                "Loaded default prompt '%s' v%s for rule '%s'",
                default_name, prompt_data.get('version'), rule_id_upper,
            )
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
        Validate that the Langfuse client is available.

        Called once at application startup.  All prompt loading happens
        on-demand via `load_batch_prompts()` when each request arrives.
        """
        if LANGFUSE_CLIENT is None:
            raise RuntimeError("LANGFUSE_CLIENT is not initialised in config")

        api_logger.info(
            "Prompt manager ready -- prompts fetched fresh from Langfuse per request"
        )

    async def get_prompt(self, rule_id: str, mls_id: str) -> Optional[Dict[str, Any]]:
        """
        Return the prompt for (rule_id, mls_id) fetched fresh from Langfuse.
        """
        api_logger.debug(f"Fetching prompt: ({rule_id.upper()}, {mls_id})")
        return await self._load_prompt(rule_id, mls_id)

    async def get_prompt_by_version(
        self,
        rule_id: str,
        mls_id: str,
        version: int
    ) -> Optional[Dict[str, Any]]:
        """
        Return a specific version of a prompt from Langfuse.
        
        Attempts to load the custom prompt first, then falls back to default.
        If a specific version is requested, it will try to fetch that version
        from Langfuse.
        
        Args:
            rule_id: Rule identifier (uppercased internally)
            mls_id: MLS identifier (case-sensitive)
            version: Specific version number to fetch
            
        Returns:
            Dict with prompt data including version, or None if not found
        """
        prompt_name = f"fp_{rule_id.upper()}_violation"
        
        api_logger.info(f"Fetching prompt version {version}: ({prompt_name}, {mls_id})")

        try:
            loop = asyncio.get_event_loop()
            # Attempt to fetch specific version from Langfuse
            prompt_obj = await loop.run_in_executor(
                None,
                lambda: LANGFUSE_CLIENT.get_prompt(prompt_name, version=version)
            )
            if not prompt_obj:
                api_logger.debug(
                    "Langfuse: prompt not found: '%s' (version=%s)",
                    prompt_name, version
                )
            else:
                prompt_data = self._build_prompt_data(
                    prompt_obj,
                    prompt_name,
                    rule_id.upper(),
                    "default"
                )

                prompt_logger.info(
                    "Loaded prompt '%s' v%s",
                    prompt_name,
                    prompt_data.get("version")
                )

                return prompt_data

        except Exception as e:
            api_logger.debug(
                f"Failed to fetch custom prompt version from Langfuse for ({prompt_name}, {version}, {mls_id}): {e}"
            )

        # Langfuse missing or failed — attempt local store fallback (specific version)
        if getattr(self, "_store", None) is not None:
            try:
                local = self._store.get_prompt_version(prompt_name, int(version))
                if local:
                    api_logger.info(f"Using local prompt replica for '{prompt_name}' v{local.get('version')}")
                    return self._build_prompt_data(local, prompt_name, rule_id.upper(), "default")
            except Exception as ex:
                api_logger.error(f"PromptStore fallback failed for '{prompt_name}' v{version}: {ex}")

        return None


    async def load_batch_prompts(
        self,
        rule_mls_pairs: list[Tuple[str, str]],
    ) -> Dict[Tuple[str, str], Optional[Dict[str, Any]]]:
        """
        Fetch prompts for all (rule_id, mls_id) pairs from Langfuse concurrently.

        Returns:
            { (rule_id, mls_id): prompt_data_or_None }
            
        NOTE: Returns the snapshot of loaded prompts WITHOUT re-checking cache,
              to prevent TTL race conditions where entries expire between load
              and return.
        """
        api_logger.info(f"Fetching {len(rule_mls_pairs)} prompts from Langfuse")

        tasks = [self._load_prompt(rule_id, mls_id) for rule_id, mls_id in rule_mls_pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        prompts_map: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {}
        for pair, result in zip(rule_mls_pairs, results):
            if isinstance(result, Exception):
                api_logger.error(f"Error fetching prompt for {pair}: {result}")
                prompts_map[pair] = None
            else:
                prompts_map[pair] = result

        loaded_count = sum(1 for v in prompts_map.values() if v is not None)
        api_logger.info(f"Fetched {loaded_count}/{len(rule_mls_pairs)} prompts successfully")

        return prompts_map


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_prompt_manager = PromptManager()


def get_prompt_manager() -> PromptManager:
    """Return the global PromptManager singleton."""
    return _prompt_manager
