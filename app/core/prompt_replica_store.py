import sqlite3
import json
from typing import Optional
from app.core.config import SQLITE_PATH
from app.core.logger import api_logger, prompt_logger


class PromptStore:
    """Encapsulates SQLite access for prompt replication.

    Usage:
        store = PromptStore(sqlite_path)
        store.init_db()
        store.store_if_new(name, version, text, updated_at)
    """

    def __init__(self, sqlite_path: Optional[str] = None):
        self.sqlite_path = sqlite_path or SQLITE_PATH
        self.logger = prompt_logger or api_logger

    def _get_conn(self):
        return sqlite3.connect(self.sqlite_path)

    def init_db(self) -> None:
        """Create the prompt_replica table if missing."""
        self.logger.info(f"Initializing prompt store DB at {self.sqlite_path}")
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_replica (
                prompt_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                prompt_text TEXT NOT NULL,
                updated_at TEXT,
                created_at TEXT,
                labels TEXT,
                config TEXT,
                created_by TEXT,
                commit_message TEXT,
                PRIMARY KEY (prompt_name, version)
            )
            """
        )
        conn.commit()
        cur.close()
        conn.close()
        self.logger.info("Prompt store DB initialized")

    def store_if_new(
        self,
        prompt_name: str,
        version: int,
        prompt_text: str,
        updated_at: Optional[str],
        labels: Optional[str] = None,
        config: Optional[str] = None,
        created_by: Optional[str] = None,
        created_at: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> bool:
        """Insert the prompt/version only if it's not already present.

        Additional metadata fields are optional. Returns True if inserted,
        False if skipped due to existing version.
        """
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM prompt_replica WHERE prompt_name = ? AND version = ?",
                (prompt_name, version),
            )
            exists = cur.fetchone()
            if exists:
                self.logger.debug(f"Prompt already exists: {prompt_name} v{version}")
                cur.close()
                conn.close()
                return False

            cur.execute(
                "INSERT INTO prompt_replica (prompt_name, version, prompt_text, updated_at, labels, config, created_by, created_at, commit_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (prompt_name, version, prompt_text, updated_at, labels, config, created_by, created_at, commit_message),
            )
            conn.commit()
            cur.close()
            conn.close()
            self.logger.info(f"Inserted prompt: {prompt_name} v{version}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store prompt {prompt_name} v{version}: {e}")
            raise

    def list_all_entries(self) -> set:
        """Return a set of (prompt_name, version) tuples currently stored."""
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT prompt_name, version FROM prompt_replica")
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return set((r[0], int(r[1])) for r in rows)
        except Exception as e:
            self.logger.error(f"Failed to list prompt entries: {e}")
            raise

    def delete_entry(self, prompt_name: str, version: int) -> None:
        """Delete a specific prompt/version from the store."""
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM prompt_replica WHERE prompt_name = ? AND version = ?",
                (prompt_name, version),
            )
            conn.commit()
            cur.close()
            conn.close()
            self.logger.info(f"Deleted prompt from store: {prompt_name} v{version}")
        except Exception as e:
            self.logger.error(f"Failed to delete prompt {prompt_name} v{version}: {e}")
            raise

    def get_latest_prompt(self, prompt_name: str) -> Optional[dict]:
        """Return the highest-version prompt for `prompt_name` that has label 'production'.

        The `labels` column may store a JSON array, a comma-separated string,
        or other text. We parse it robustly and return the first (highest
        version) row where one of the labels equals 'production' (case-insensitive).
        Returns None if no production-labelled row exists.
        """
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT version, prompt_text, updated_at, labels, config, created_by, created_at, commit_message FROM prompt_replica WHERE prompt_name = ? ORDER BY version DESC",
                (prompt_name,)
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows:
                return None

            for row in rows:
                labels_raw = row[3]
                labels_list = []
                try:
                    if labels_raw is None:
                        labels_list = []
                    elif isinstance(labels_raw, (list, tuple)):
                        labels_list = list(labels_raw)
                    elif isinstance(labels_raw, str):
                        s = labels_raw.strip()
                        if s.startswith("[") or s.startswith("{"):
                            try:
                                labels_list = json.loads(s)
                            except Exception:
                                # try forgiving single-quote JSON
                                try:
                                    labels_list = json.loads(s.replace("'", '"'))
                                except Exception:
                                    # fallback to CSV-style parsing
                                    labels_list = [p.strip() for p in s.strip('[]').split(',') if p.strip()]
                        else:
                            labels_list = [p.strip() for p in s.split(',') if p.strip()]
                    else:
                        labels_list = []
                except Exception:
                    labels_list = []

                # Normalize and check for production label
                try:
                    found = any(str(lbl).strip().lower() == "production" for lbl in labels_list)
                except Exception:
                    found = False

                if found:
                    return {
                        "version": int(row[0]),
                        "prompt": row[1],
                        "updated_at": row[2],
                        "labels": row[3],
                        "config": row[4],
                        "created_by": row[5],
                        "created_at": row[6],
                        "commit_message": row[7],
                    }

            # No production-labelled row found
            return None
        except Exception as e:
            self.logger.error(f"Failed to read latest prompt {prompt_name}: {e}")
            raise

    def get_prompt_version(self, prompt_name: str, version: int) -> Optional[dict]:
        """Return a specific version row for a prompt_name as a dict, or None."""
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT version, prompt_text, updated_at, labels, config, created_by, created_at, commit_message FROM prompt_replica WHERE prompt_name = ? AND version = ? LIMIT 1",
                (prompt_name, version),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if not row:
                return None
            return {
                "version": int(row[0]),
                "prompt": row[1],
                "updated_at": row[2],
                "labels": row[3],
                "config": row[4],
                "created_by": row[5],
                "created_at": row[6],
                "commit_message": row[7],
            }
        except Exception as e:
            self.logger.error(f"Failed to read prompt {prompt_name} v{version}: {e}")
            raise


__all__ = ["PromptStore"]
