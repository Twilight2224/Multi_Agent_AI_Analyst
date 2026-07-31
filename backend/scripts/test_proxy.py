"""Small, non-secret-bearing Gemini proxy smoke test."""
from app.config import settings
from app.llm import worker_llm


def main() -> None:
    settings.require_gemini_key()
    response = worker_llm().invoke("Reply with exactly: proxy-ok")
    if "proxy-ok" not in response.content.lower():
        raise RuntimeError("Proxy responded, but the smoke-test response was unexpected.")
    print("Gemini proxy smoke test passed.")


if __name__ == "__main__":
    main()
