from __future__ import annotations

from typing import Literal, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    session_id: str
    plan: Literal["retriever", "web", "data", "code", "finish"]
    documents: list[str]
    sources: list[str]
    sql_result: str | None
    code_result: str | None
    answer: str
    steps: list[str]
    revisions: int
    approved: bool
    critic_reason: str
    memory: list[str]
