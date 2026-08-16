from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    session_id: str
    plan: Literal["retriever", "web", "data", "code", "finish"]
    # Annotated with operator.add so each specialist's results are appended to
    # the existing list instead of replacing it (LangGraph's default merge
    # behavior for un-annotated keys is overwrite, not accumulate).
    documents: Annotated[list[str], operator.add]
    sources: Annotated[list[str], operator.add]
    sql_result: str | None
    code_result: str | None
    answer: str
    steps: list[str]
    revisions: int
    approved: bool
    critic_reason: str
    memory: list[str]
