from __future__ import annotations

import re
from typing import Literal

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from .database import database_schema, execute_readonly_sql
from .llm import supervisor_llm, worker_llm
from .sandbox import run_safe_python
from .state import AgentState
from .vector_store import search_documents, search_memory


class Route(BaseModel):
    next: Literal["retriever", "web", "data", "code", "finish"] = Field(description="The next graph node")


class Verdict(BaseModel):
    ok: bool
    reason: str


def _steps(state: AgentState, step: str) -> list[str]:
    return [*state.get("steps", []), step]


def load_memory(state: AgentState) -> dict:
    memory = search_memory(state["session_id"], state["question"])
    return {"memory": memory, "steps": _steps(state, "memory")}



def _fallback_route(state: AgentState) -> Route:
    done = " ".join(state.get("steps", []))
    q = state["question"].lower()
    if not any(x in done for x in ("data(sql)",)) and any(word in q for word in ("how many", "count", "average", "total", "revenue", "customer", "churn")):
        return Route(next="data")
    if not any(x in done for x in ("code",)) and any(word in q for word in ("calculate", "percent", "percentage", "median", "ratio", "math")):
        return Route(next="code")
    if not any(x in done for x in ("retriever",)):
        return Route(next="retriever")
    if not any(x in done for x in ("web",)) and any(word in q for word in ("latest", "today", "current", "news", "web")):
        return Route(next="web")
    return Route(next="finish")
    

def supervisor(state: AgentState) -> dict:
    # A hard budget guarantees termination even if a provider returns a poor route.
    actions = sum(step.startswith(("retriever", "web", "data", "code")) for step in state.get("steps", []))
    if actions >= 4:
        decision = Route(next="finish")
    else:
        doc_preview = "\n---\n".join(doc[:400] for doc in state.get("documents", [])) or "none retrieved yet"
        prompt = f"""You are a supervisor routing a business analyst question.
Question: {state['question']}
Past relevant conversation (context only, NOT usable as evidence for this answer): {state.get('memory', [])}
Completed steps this turn: {state.get('steps', [])}
Retrieved documents so far (private knowledge base and/or web results):
{doc_preview}
SQL evidence: {state.get('sql_result') or 'none'}
Code evidence: {state.get('code_result') or 'none'}

Routing priority:
1. If 'retriever' has not run yet this turn, prefer it first for any question that could be answered from private documents.
2. Only route to 'web' if the retrieved documents above are empty, or clearly leave a specific part of the question unanswered that needs current/external information. Do not use web to answer something the documents already cover.
3. If the documents already fully answer the question, choose finish instead of also calling web.
4. Use 'data' for database facts, 'code' for arithmetic.
5. Do not repeat a completed specialist unless revising needs it.
You may only choose finish if there is at least one non-empty source above, OR the question is purely conversational (e.g. asking to rephrase or clarify a prior answer with no new facts needed)."""
        try:
            decision = supervisor_llm().with_structured_output(Route).invoke(prompt)
            has_evidence = bool(state.get("documents") or state.get("sql_result") or state.get("code_result"))
            if decision.next == "finish" and actions == 0 and not has_evidence:
                decision = _fallback_route(state)
        except Exception:
          decision = _fallback_route(state)
    return {"plan": decision.next, "steps": _steps(state, f"supervisor->{decision.next}")}





def retriever_agent(state: AgentState) -> dict:
    docs = search_documents(state["question"])
    return {
        "documents": [doc.page_content for doc in docs],
        "sources": [str(doc.metadata.get("source", "uploaded document")) for doc in docs],
        "steps": _steps(state, "retriever"),
    }


def web_agent(state: AgentState) -> dict:
    from .config import settings
    if not settings.tavily_api_key:
        return {"steps": _steps(state, "web(skipped: TAVILY_API_KEY unset)")}
    try:
        from tavily import TavilyClient
        hits = TavilyClient(api_key=settings.tavily_api_key).search(state["question"], max_results=4).get("results", [])
        return {
            "documents": [hit.get("content", "") for hit in hits],
            "sources": [hit.get("url", "web result") for hit in hits],
            "steps": _steps(state, "web"),
        }
    except Exception as error:
        return {"steps": _steps(state, f"web(error: {type(error).__name__})")}


def _clean_code_fence(text: str) -> str:
    return re.sub(r"^```(?:sql|python)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)


def data_agent(state: AgentState) -> dict:
    prompt = f"""Write exactly one SQLite SELECT query for this question: {state['question']}
Schema:
{database_schema()}
Return SQL only. Never modify data."""
    try:
        sql = _clean_code_fence(worker_llm().invoke(prompt).content)
        result = execute_readonly_sql(sql)
        return {"sql_result": f"{sql}\n=> {result}", "steps": _steps(state, "data(sql)")}
    except Exception as error:
        return {"sql_result": f"SQL agent could not produce a safe result: {error}", "steps": _steps(state, "data(sql-error)")}


def code_agent(state: AgentState) -> dict:
    prompt = f"""Write short Python for an exact calculation answering: {state['question']}
Use literals and basic built-ins only. No imports, files, network, input, eval, exec, classes, or functions. End with print(result). Return Python only."""
    try:
        code = _clean_code_fence(worker_llm().invoke(prompt).content)
        output = run_safe_python(code)
        return {"code_result": f"{code}\n=> {output}", "steps": _steps(state, "code")}
    except Exception as error:
        return {"code_result": f"Code agent could not safely execute: {error}", "steps": _steps(state, "code(error)")}


def generate_answer(state: AgentState) -> dict:
    docs = state.get("documents", [])
    srcs = state.get("sources", [])
    evidence = "\n\n".join([
        *(f"Source ({src}): {doc}" for doc, src in zip(docs, srcs)),
        f"SQL result: {state.get('sql_result') or 'none'}",
        f"Code result: {state.get('code_result') or 'none'}",
        *(f"Memory: {item}" for item in state.get("memory", [])),
    ])
    prompt = f"""Answer the question using only the evidence below. When multiple sources are present, treat the one most directly relevant to the question (e.g. a database result for a factual count, an uploaded document for a policy question) as the primary claim, and use the others only to add context or fill gaps — never let a supporting source override the primary one. If evidence came from the user's own uploaded documents versus the web, say so where relevant. Be concise, state uncertainty or missing evidence plainly, and never invent a source.
Question: {state['question']}
Evidence:
{evidence or 'No evidence was collected.'}
Previous critic feedback: {state.get('critic_reason', 'none')}"""
    try:
        answer = worker_llm().invoke(prompt).content
    except Exception as error:
        answer = f"I could not generate an answer because the model request failed: {type(error).__name__}."
    return {"answer": answer, "approved": False, "steps": _steps(state, "generate")}


def critic(state: AgentState) -> dict:
    prompt = f"""You are a strict answer verifier. Approve only if the answer is directly supported by the evidence.
Question: {state['question']}
Evidence: documents={state.get('documents', [])}; SQL={state.get('sql_result')}; code={state.get('code_result')}
Answer: {state.get('answer', '')}"""
    try:
        verdict = supervisor_llm().with_structured_output(Verdict).invoke(prompt)
    except Exception:
        # A provider failure cannot bypass the quality gate.
        verdict = Verdict(ok=False, reason="Critic model unavailable; answer requires revision.")
    revisions = state.get("revisions", 0) + (0 if verdict.ok else 1)
    return {"approved": verdict.ok, "critic_reason": verdict.reason, "revisions": revisions, "steps": _steps(state, f"critic({'approved' if verdict.ok else 'revise'})")}


def route_from_supervisor(state: AgentState) -> str:
    return state.get("plan", "finish")


def route_after_critic(state: AgentState) -> str:
    return "finish" if state.get("approved") or state.get("revisions", 0) >= 2 else "revise"


def build_graph(with_critic: bool = True):
    graph = StateGraph(AgentState)
    graph.add_node("memory", load_memory)
    graph.add_node("supervisor", supervisor)
    graph.add_node("retriever", retriever_agent)
    graph.add_node("web", web_agent)
    graph.add_node("data", data_agent)
    graph.add_node("code", code_agent)
    graph.add_node("generate", generate_answer)
    if with_critic:
        graph.add_node("critic", critic)
    graph.add_edge(START, "memory")
    graph.add_edge("memory", "supervisor")
    graph.add_conditional_edges("supervisor", route_from_supervisor, {
        "retriever": "retriever", "web": "web", "data": "data", "code": "code", "finish": "generate",
    })
    for agent in ("retriever", "web", "data", "code"):
        graph.add_edge(agent, "supervisor")
    if with_critic:
        graph.add_edge("generate", "critic")
        graph.add_conditional_edges("critic", route_after_critic, {"finish": END, "revise": "supervisor"})
    else:
        graph.add_edge("generate", END)
    return graph.compile()


agent_graph = build_graph()
