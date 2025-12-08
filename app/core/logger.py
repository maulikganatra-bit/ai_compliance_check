"""Logging infrastructure with request ID tracking and per-request log files.

This module provides:
1. RequestIDFilter - Injects request UUID into all log records
2. RequestFileHandler - Creates separate log file for each request
3. setup_logger() - Configures loggers with console + file output

Log structure:
- Console: All logs with request_id included
- Per-request files: logs/request_{uuid}.log (one per request)

Usage:
    from app.core.logger import api_logger
    api_logger.info("Processing request")
"""

import logging
import logging.handlers
import sys
from pathlib import Path

class RequestIDFilter(logging.Filter):
    """Logging filter to inject request_id into log records.
    
    This filter adds a 'request_id' attribute to every log record.
    The request_id comes from the context variable set by RequestIDMiddleware.
    
    Benefits:
    - Trace all logs for a specific request
    - Correlate logs across multiple async operations
    - Enable per-request log file creation
    """
    
    def filter(self, record):
        """Add request_id to the log record.
        
        Args:
            record: LogRecord to modify
            
        Returns:
            True (always allow record to be logged)
        """
        from app.core.middleware import get_request_id
        # Get request_id from context variable, default to "no-request-id" if not set
        # "no-request-id" occurs during startup/shutdown when no request is active
        record.request_id = get_request_id() or "no-request-id"
        return True

class RequestFileHandler(logging.Handler):
    """Custom handler that creates a separate log file for each request.
    
    How it works:
    1. Each request gets a unique UUID from RequestIDMiddleware
    2. First log for a request creates logs/request_{uuid}.log
    3. All subsequent logs for that request append to same file
    4. File handlers are cached in memory for performance
    
    Benefits:
    - Easy debugging: All logs for one request in one file
    - Parallel processing: No log interleaving issues
    - Request tracing: Find all operations for a specific request
    """
    
    def __init__(self, log_dir: Path, level=logging.INFO):
        """Initialize the request file handler.
        
        Args:
            log_dir: Directory to store log files (e.g., Path("logs"))
            level: Minimum log level to capture
        """
        super().__init__(level)
        self.log_dir = log_dir
        self.log_dir.mkdir(exist_ok=True)  # Create logs/ directory if missing
        self.file_handlers = {}  # Cache: {request_id: FileHandler}
        
        # Set formatter for all request log files
        formatter = logging.Formatter(
            '[%(asctime)s] - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.setFormatter(formatter)
    
    def emit(self, record):
        """Write log record to request-specific file.
        
        Args:
            record: LogRecord to write
        """
        try:
            # Extract request_id from log record (added by RequestIDFilter)
            request_id = getattr(record, 'request_id', 'no-request-id')
            
            # Skip creating files for no-request-id (startup/shutdown logs)
            # These logs only go to console
            if request_id == "no-request-id":
                return
            
            # Create or get file handler for this request
            if request_id not in self.file_handlers:
                # Create new file: logs/request_{uuid}.log
                log_file = self.log_dir / f"request_{request_id}.log"
                file_handler = logging.FileHandler(log_file, mode='a')  # Append mode
                file_handler.setFormatter(self.formatter)
                # Cache handler for subsequent logs from same request
                self.file_handlers[request_id] = file_handler
            
            # Write to request-specific file
            self.file_handlers[request_id].emit(record)
            
        except Exception:
            # Handle errors gracefully (don't crash app due to logging issues)
            self.handleError(record)
    
    def close(self):
        """Close all file handlers on shutdown."""
        for handler in self.file_handlers.values():
            handler.close()
        super().close()

def setup_logger(name: str, log_level=logging.INFO):
    """Configure and return a logger instance with both console and file handlers.
    
    Creates a logger with:
    1. RequestIDFilter - Adds request_id to all log records
    2. Console handler - Outputs to stdout with request_id
    3. RequestFileHandler - Creates per-request log files
    
    Args:
        name: Logger name (e.g., 'api.routes')
        log_level: Minimum log level (default: INFO)
        
    Returns:
        Configured logger instance
        
    Example:
        logger = setup_logger('my_module', logging.DEBUG)
        logger.info("This will appear in console and logs/request_{uuid}.log")
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Add request ID filter to inject request_id into all records
    logger.addFilter(RequestIDFilter())
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Console handler - outputs to terminal with request_id
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '[%(asctime)s] - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Request-specific file handler - creates logs/request_{uuid}.log
    request_file_handler = RequestFileHandler(log_dir, level=log_level)
    
    # Add handlers to logger (only if not already added)
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(request_file_handler)
    
    return logger

# ============================================================================
# MODULE-LEVEL LOGGERS
# ============================================================================
# Pre-configured loggers for different parts of the application
# Import these in other modules instead of creating new loggers

api_logger = setup_logger('api.routes', logging.INFO)      # For routes.py
rules_logger = setup_logger('api.rules', logging.INFO)     # For rule functions
app_logger = setup_logger('api.main', logging.INFO)        # For main.py
