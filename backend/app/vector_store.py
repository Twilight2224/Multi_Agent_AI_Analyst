from __future__ import annotations

from functools import lru_cache

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from .config import settings
from .llm import embeddings


KNOWLEDGE_COLLECTION = "knowledge_base"
MEMORY_COLLECTION = "conversation_memory"


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    settings.qdrant_directory.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(settings.qdrant_directory))


def _store(collection_name: str) -> QdrantVectorStore:
    client = _client()
    embedding_model = embeddings()
    if not client.collection_exists(collection_name):
        # Deriving dimensions from the configured API prevents a model/collection mismatch.
        dimensions = len(embedding_model.embed_query("collection dimension probe"))
        client.create_collection(
            collection_name,
            vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
        )
    return QdrantVectorStore(client=client, collection_name=collection_name, embedding=embedding_model)


def add_documents(texts: list[str], source: str) -> int:
    docs = [Document(page_content=text, metadata={"source": source}) for text in texts if text.strip()]
    if not docs:
        return 0
    _store(KNOWLEDGE_COLLECTION).add_documents(docs)
    return len(docs)


def search_documents(question: str, k: int = 4) -> list[Document]:
    try:
        return _store(KNOWLEDGE_COLLECTION).similarity_search(question, k=k)
    except Exception:  # Empty collection should not make the entire graph fail.
        return []


def add_memory(session_id: str, question: str, answer: str) -> None:
    _store(MEMORY_COLLECTION).add_documents([Document(
        page_content=f"Question: {question}\nAnswer: {answer}", metadata={"session_id": session_id}
    )])


def search_memory(session_id: str, question: str, k: int = 3) -> list[str]:
    try:
        docs = _store(MEMORY_COLLECTION).similarity_search(
            question, k=k,
            filter=models.Filter(must=[models.FieldCondition(key="metadata.session_id", match=models.MatchValue(value=session_id))]),
        )
        return [doc.page_content for doc in docs]
    except Exception:
        return []
