from __future__ import annotations

from .config import settings


def callbacks() -> list:
    """Return Langfuse tracing callbacks only when credentials are configured."""
    if not (settings.langfuse_secret_key and settings.langfuse_public_key):
        return []
    from langfuse.langchain import CallbackHandler
    return [CallbackHandler()]
