from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import settings
from .database import initialize_database
from .graph import agent_graph
from .observability import callbacks
from .vector_store import add_documents, add_memory


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield

from dotenv import load_dotenv
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Multi-Agent AI Analyst", version="1.0.0", lifespan=lifespan)

app.add_middleware(       # <-- then this
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class IngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    source: str = Field(default="pasted text", max_length=200)


def _initial_state(request: ChatRequest) -> dict:
    return {
        "question": request.question,
        "session_id": request.session_id,
        "documents": [], "sources": [], "steps": [], "revisions": 0,
        "sql_result": None, "code_result": None, "answer": "", "memory": [],
    }


def _require_key() -> None:
    if not settings.gemini_api_key:
        raise HTTPException(503, "GEMINI_API_KEY is missing. Set it in the root .env before making model calls.")


def _chunks(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    return [cleaned[index:index + size] for index in range(0, len(cleaned), size - overlap)]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "gemini_key_configured": bool(settings.gemini_api_key), "proxy": settings.gemini_base_url}


@app.post("/ingest")
def ingest_text(request: IngestRequest) -> dict:
    _require_key()
    count = add_documents(_chunks(request.text), request.source)
    return {"ingested_chunks": count, "source": request.source}


@app.post("/ingest/file")
async def ingest_file(file: UploadFile = File(...)) -> dict:
    _require_key()
    raw = await file.read()
    name = file.filename or "uploaded file"
    try:
        if name.lower().endswith(".pdf"):
            from pypdf import PdfReader
            import io
            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
        else:
            text = raw.decode("utf-8")
    except Exception as error:
        raise HTTPException(400, f"Could not read {name}: {error}") from error
    count = add_documents(_chunks(text), name)
    return {"ingested_chunks": count, "source": name}


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    _require_key()
    result = await agent_graph.ainvoke(_initial_state(request), config={
        "recursion_limit": settings.max_graph_steps, "callbacks": callbacks(),
        "metadata": {"langfuse_session_id": request.session_id, "langfuse_tags": ["multi-agent-analyst"]},
    })
    add_memory(request.session_id, request.question, result.get("answer", ""))
    return {
        "session_id": request.session_id, "answer": result.get("answer", ""), "steps": result.get("steps", []),
        "sources": result.get("sources", []), "approved": result.get("approved", False),
        "critic_reason": result.get("critic_reason", ""),
    }

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    _require_key()

    async def events():
        final_state = _initial_state(request)
        try:
            async for update in agent_graph.astream(final_state, config={
                "recursion_limit": settings.max_graph_steps, "callbacks": callbacks(),
                "metadata": {"langfuse_session_id": request.session_id, "langfuse_tags": ["multi-agent-analyst"]},
            }):
                for node, values in update.items():
                    final_state.update(values)
                    yield f"event: step\ndata: {json.dumps({'node': node, 'steps': final_state.get('steps', [])})}\n\n"
            add_memory(request.session_id, request.question, final_state.get("answer", ""))
            yield f"event: result\ndata: {json.dumps({'session_id': request.session_id, 'answer': final_state.get('answer', ''), 'steps': final_state.get('steps', []), 'sources': final_state.get('sources', []), 'approved': final_state.get('approved', False), 'critic_reason': final_state.get('critic_reason', '')})}\n\n"
        except Exception as error:
            yield f"event: error\ndata: {json.dumps({'detail': str(error)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
