from langfuse import Langfuse
from typing import List, Any
from app.core.logger import api_logger, prompt_logger


class LangfusePromptFetcher:
    """Class responsible for fetching prompts and their versions from Langfuse.

    Example:
        fetcher = LangfusePromptFetcher(langfuse_client)
        entries = fetcher.fetch_all_prompt_versions()
    """

    def __init__(self, client: Langfuse, page_size: int = 50):
        self.client = client
        self.page_size = page_size
        self.logger = prompt_logger or api_logger

    def fetch_all_prompts(self) -> List[Any]:
        prompts = []
        page = 1
        limit = self.page_size

        self.logger.info("Listing prompts from Langfuse (paginated)")
        while True:
            resp = self.client.api.prompts.list(page=page, limit=limit)
            data = getattr(resp, "data", []) or []
            prompts.extend(data)

            meta = getattr(resp, "meta", None)
            total = getattr(meta, "total_items", None) if meta is not None else None
            if total is None:
                if not data:
                    break
            else:
                if page * limit >= int(total):
                    break

            page += 1

        self.logger.info(f"Found {len(prompts)} prompts in Langfuse")
        return prompts

    def fetch_prompt_versions(self, prompt_name: str) -> List[Any]:
        versions = []
        version_number = 1
        self.logger.debug(f"Fetching versions for prompt: {prompt_name}")

        while True:
            try:
                prompt = self.client.api.prompts.get(prompt_name, version=version_number)
                versions.append(prompt)
                version_number += 1
            except Exception:
                break

        self.logger.info(f"Found {len(versions)} versions for prompt: {prompt_name}")
        return versions

    def fetch_all_prompt_versions(self) -> List[dict]:
        """Return flattened list of {name, version_obj} for all prompt versions."""
        results: List[dict] = []
        prompts = self.fetch_all_prompts()
        for meta in prompts:
            name = getattr(meta, "name", None) or getattr(meta, "id", None)
            if not name:
                continue
            try:
                versions = self.fetch_prompt_versions(name)
            except Exception as e:
                self.logger.error(f"Failed fetching versions for {name}: {e}")
                continue

            for v in versions:
                results.append({"name": name, "version_obj": v})

        self.logger.info(f"Total prompt versions to ingest: {len(results)}")
        return results


__all__ = ["LangfusePromptFetcher"]

