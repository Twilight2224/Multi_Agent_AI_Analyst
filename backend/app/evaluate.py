"""Run a repeatable 10-question evaluation with an LLM judge and optional RAGAS."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .config import settings
from .graph import agent_graph, build_graph
from .llm import supervisor_llm
from .llm import embeddings, worker_llm


EVALUATION_SET = [
    {"question": "How many customers churned in Q1 2025?", "reference": "4"},
    {"question": "Which churn reason occurred most often?", "reference": "Missing integration"},
    {"question": "What is the average monthly revenue of active customers?", "reference": "1305"},
    {"question": "How many SMB customers churned?", "reference": "3"},
    {"question": "What was the revenue of the churned Mid-market customer?", "reference": "640"},
    {"question": "List churn reasons in Q1 2025.", "reference": "Missing integration, Price sensitivity, Slow support response"},
    {"question": "How many active Enterprise customers are there?", "reference": "3"},
    {"question": "What percentage of customers churned?", "reference": "50%"},
    {"question": "Which month had the most churn events?", "reference": "March 2025"},
    {"question": "What are the two most common stated churn reasons?", "reference": "Missing integration, Price sensitivity or Slow support response"},
]


async def judge(question: str, reference: str, answer: str) -> int:
    prompt = f"""Score this answer from 1 to 5 for factual correctness against the reference. Reply with one integer only.
Question: {question}\nReference: {reference}\nAnswer: {answer}"""
    try:
        score = int(supervisor_llm().invoke(prompt).content.strip()[0])
        return min(5, max(1, score))
    except Exception:
        return 1


async def run() -> list[dict]:
    settings.require_gemini_key()
    results = []
    graph_without_critic = build_graph(with_critic=False)
    for index, item in enumerate(EVALUATION_SET):
        initial = {"question": item["question"], "session_id": f"evaluation-{index}", "documents": [], "sources": [], "steps": [], "revisions": 0}
        state = await agent_graph.ainvoke(initial)
        baseline = await graph_without_critic.ainvoke(initial)
        score = await judge(item["question"], item["reference"], state.get("answer", ""))
        baseline_score = await judge(item["question"], item["reference"], baseline.get("answer", ""))
        results.append({
            **item, "answer": state.get("answer", ""), "judge_score_with_critic": score,
            "answer_without_critic": baseline.get("answer", ""), "judge_score_without_critic": baseline_score,
            "steps": state.get("steps", []),
        })
    report = {
        "results": results, "ragas": run_ragas(results),
        "mean_judge_score_with_critic": sum(x["judge_score_with_critic"] for x in results) / len(results),
        "mean_judge_score_without_critic": sum(x["judge_score_without_critic"] for x in results) / len(results),
    }
    output = Path(__file__).resolve().parents[1] / "evaluation_results.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return results


def run_ragas(results: list[dict]) -> dict:
    """Use RAGAS when its optional metric APIs are available; retain judge results otherwise."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, faithfulness
        dataset = Dataset.from_list([{
            "question": item["question"], "answer": item["answer"],
            "contexts": ["SQL and agent evidence were collected during this run."],
            "ground_truth": item["reference"],
        } for item in results])
        scores = evaluate(
            dataset, metrics=[faithfulness, answer_relevancy, context_precision],
            llm=worker_llm(), embeddings=embeddings(),
        )
        return {"available": True, "scores": str(scores)}
    except Exception as error:
        return {"available": False, "detail": f"RAGAS was not completed: {type(error).__name__}: {error}"}


if __name__ == "__main__":
    report = asyncio.run(run())
    print(json.dumps({
        "questions": len(report),
        "mean_judge_score_with_critic": sum(x["judge_score_with_critic"] for x in report) / len(report),
        "mean_judge_score_without_critic": sum(x["judge_score_without_critic"] for x in report) / len(report),
    }, indent=2))
