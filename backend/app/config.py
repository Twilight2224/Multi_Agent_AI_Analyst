from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

# Resolve the root .env regardless of whether the API starts from /backend or root.
load_dotenv(PROJECT_DIR / ".env")


class Settings:
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_base_url = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    database_url = os.getenv("DATABASE_URL", "sqlite:///data/company.db")
    qdrant_path = os.getenv("QDRANT_PATH", "storage/qdrant")
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    max_graph_steps = int(os.getenv("MAX_GRAPH_STEPS", "18"))

    gemini_base_url = "https://saidazam-litellm-proxy.hf.space/v1"

    @property
    def database_path(self) -> Path:
        raw_path = self.database_url.removeprefix("sqlite:///")
        return (BACKEND_DIR / raw_path).resolve()

    @property
    def qdrant_directory(self) -> Path:
        return (BACKEND_DIR / self.qdrant_path).resolve()

    def require_gemini_key(self) -> None:
        if not self.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to the root .env file.")


settings = Settings()
