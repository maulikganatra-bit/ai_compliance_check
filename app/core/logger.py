"""
Async-safe logging with request-id based log files.

Key properties:
- Non-blocking for async FastAPI
- Per-request log files (request_<uuid>.log)
- Logs written to host filesystem via Docker volume (/logs)
- Safe for OpenAI / httpx async clients
"""

import logging
import sys
from pathlib import Path
from queue import Queue
from logging.handlers import QueueHandler, QueueListener

# ============================================================================
# Request ID Filter
# ============================================================================

class RequestIDFilter(logging.Filter):
    """
    Injects request_id into every log record.
    request_id is expected to be stored in a contextvar
    via RequestIDMiddleware.
    """
    def filter(self, record):
        try:
            from app.core.middleware import get_request_id
            record.request_id = get_request_id() or "no-request-id"
        except Exception:
            record.request_id = "no-request-id"
        return True

# ============================================================================
# Per-request file handler (USED ONLY IN BACKGROUND THREAD)
# ============================================================================

class PerRequestFileHandler(logging.Handler):
    """
    Routes log records to per-request log files:
        /logs/request_<request_id>.log

    IMPORTANT:
    - This handler MUST run in a background thread.
    - Never attach this directly to FastAPI loggers.
    """
    def __init__(self, log_dir: Path):
        super().__init__()
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._handlers = {}

    def emit(self, record):
        request_id = getattr(record, "request_id", "no-request-id")
        if request_id == "no-request-id":
            return

        if request_id not in self._handlers:
            file_path = self.log_dir / f"request_{request_id}.log"
            fh = logging.FileHandler(file_path, mode="a")
            fh.setFormatter(self.formatter)
            self._handlers[request_id] = fh

        self._handlers[request_id].emit(record)

    def close(self):
        for handler in self._handlers.values():
            handler.close()
        super().close()

# ============================================================================
# Global logging queue (non-blocking)
# ============================================================================

_log_queue: Queue = Queue(-1)
_listener: QueueListener | None = None

# ============================================================================
# Logger setup
# ============================================================================

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Creates a non-blocking logger with:
    - request_id injected
    - console logging
    - per-request file logging to /logs (host-mounted)

    Safe for async FastAPI.
    """
    global _listener

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Add request-id filter
    logger.addFilter(RequestIDFilter())

    # ------------------------------------------------------------------------
    # Console handler (stdout)
    # ------------------------------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(request_id)s] %(name)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    # ------------------------------------------------------------------------
    # Per-request file handler (host filesystem)
    # ------------------------------------------------------------------------
    file_handler = PerRequestFileHandler(Path("/logs"))
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(name)s %(levelname)s '
        '%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    # ------------------------------------------------------------------------
    # Start queue listener once (background thread)
    # ------------------------------------------------------------------------
    if _listener is None:
        _listener = QueueListener(
            _log_queue,
            console_handler,
            file_handler,
            respect_handler_level=True
        )
        _listener.start()

    # ------------------------------------------------------------------------
    # Non-blocking queue handler (attached to logger)
    # ------------------------------------------------------------------------
    queue_handler = QueueHandler(_log_queue)
    logger.addHandler(queue_handler)

    return logger

# ============================================================================
# Pre-configured application loggers
# ============================================================================

api_logger = setup_logger("api.routes", logging.DEBUG)
rules_logger = setup_logger("api.rules", logging.DEBUG)
app_logger = setup_logger("api.main", logging.DEBUG)
