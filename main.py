"""Root-level entry point for the API.

This file allows running the API with: uvicorn main:app
Instead of: uvicorn app.main:app
"""
from app.main import app

__all__ = ["app"]
