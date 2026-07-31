"""All model access goes through the class LiteLLM proxy, never Google directly."""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .config import settings


def worker_llm() -> ChatOpenAI:
    """Low-cost model for specialist agents and answer drafting."""
    settings.require_gemini_key()
    return ChatOpenAI(
        base_url=settings.gemini_base_url,
        api_key=settings.gemini_api_key,
        model="gemini-flash-lite",
        temperature=0,
    )


def supervisor_llm() -> ChatOpenAI:
    """Higher-capability model reserved for routing and criticism."""
    settings.require_gemini_key()
    return ChatOpenAI(
        base_url=settings.gemini_base_url,
        api_key=settings.gemini_api_key,
        model="gemini-flash-lite",
        temperature=0,
    )


def embeddings() -> OpenAIEmbeddings:
    settings.require_gemini_key()
    return OpenAIEmbeddings(
        base_url=settings.gemini_base_url,
        api_key=settings.gemini_api_key,
        model="gemini-embedding",
    )
