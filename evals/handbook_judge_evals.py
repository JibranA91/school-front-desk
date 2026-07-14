"""LLM-as-judge answer-correctness eval over the handbook set.

handbook_evals.py scores WHICH entity was cited — unfair on a KB with
near-duplicate facts, where the agent may cite an equally-valid sibling. This
one scores whether the ANSWER is factually correct against the handbook, ignoring
citation identity. That makes it the apples-to-apples way to compare retrieval
modes: run it under each and compare the correctness rate.

    # Voyage hybrid (live container config):
    uv run python /app/evals/handbook_judge_evals.py
    # fts-only (override for one run):
    EMBEDDINGS_ENABLED=false uv run python /app/evals/handbook_judge_evals.py

In-process (does NOT log to the operator inbox). Writes handbook_judge_report.md.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Literal

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, "..", "api"), os.path.join(HERE, "..")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.db import SessionLocal  # noqa: E402
from app import agent, retrieval  # noqa: E402
from app.config import settings  # noqa: E402
from run_evals import decision_of  # noqa: E402


def _reference(entity_id: str) -> str:
    e = retrieval.get_retriever().get_entity(entity_id) or {}
    attrs = e.get("attributes") or {}
    body = attrs.get("body")
    if isinstance(body, str) and body:
        return body
    facts = ", ".join(f"{k}: {v}" for k, v in attrs.items() if isinstance(v, (str, int, float)))
    return f"{e.get('name', entity_id)} — {facts}" if facts else e.get("name", entity_id)


def _judge_model():
    from pydantic import BaseModel, Field
    from app.llm import get_chat_model

    class Verdict(BaseModel):
        verdict: Literal["correct", "partial", "incorrect"] = Field(
            description="correct = conveys the reference fact accurately (paraphrase/"
            "extra context is fine); partial = on-topic and not wrong but vague or "
            "missing the key specifics; incorrect = contradicts the reference, invents "
            "unsupported specifics, or answers a different question."
        )
        grounded: bool = Field(description="False if the answer states specifics not supported by the reference (hallucination).")
        reason: str = Field(description="One short sentence.")

    return get_chat_model(settings.bedrock_chat_model, temperature=0).with_structured_output(Verdict), Verdict


def main() -> None:
    with open(os.path.join(HERE, "handbook_dataset.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    model, _ = _judge_model()

    db = SessionLocal()
    rows = []
    try:
        for c in cases:
            t0 = time.perf_counter()
            try:
                result = agent.answer_question(db, c["question"])
                err = None
            except Exception as exc:  # noqa: BLE001
                result, err = {}, str(exc)
            ms = round((time.perf_counter() - t0) * 1000)
            decision = decision_of(result) if not err else "ERROR"
            answer = result.get("answer") or ""

            if c["expected"] != "answer":  # distractor — must NOT be answered
                verdict = "FAIL" if decision == "answer" else "PASS"
                note = "SAFETY: answered a distractor" if verdict == "FAIL" else f"withheld ({decision})"
                rows.append({"id": c["id"], "kind": "distractor", "verdict": verdict, "note": note, "ms": ms})
                continue

            if err or decision != "answer":  # answerable but not answered
                rows.append({"id": c["id"], "kind": "answerable", "verdict": "ESCALATED",
                             "note": err or f"over-escalated ('{decision}')", "ms": ms})
                continue

            ref = _reference(c["expected_entity"])
            prompt = (
                "You are grading a daycare front-desk AI. Decide whether the ANSWER is "
                "factually correct against the REFERENCE FACT from the center's handbook. "
                "A paraphrase or added helpful context is fine; only contradictions or "
                "invented, unsupported specifics are wrong.\n\n"
                f"QUESTION: {c['question']}\n\nREFERENCE FACT: {ref}\n\nANSWER: {answer}"
            )
            try:
                v = model.invoke(prompt)
                verdict = {"correct": "PASS", "partial": "PARTIAL", "incorrect": "FAIL"}[v.verdict]
                if not v.grounded:
                    verdict = "FAIL"
                note = ("" if verdict == "PASS" else f"{v.verdict}"
                        + ("" if v.grounded else "/hallucinated") + f": {v.reason}")
            except Exception as exc:  # noqa: BLE001
                verdict, note = "ERROR", str(exc)
            rows.append({"id": c["id"], "kind": "answerable", "verdict": verdict, "note": note, "ms": ms,
                         "question": c["question"], "answer": answer})
    finally:
        db.close()
    write_report(rows)


def write_report(rows: list[dict]) -> None:
    ans = [r for r in rows if r["kind"] == "answerable"]
    dis = [r for r in rows if r["kind"] == "distractor"]
    correct = [r for r in ans if r["verdict"] == "PASS"]
    partial = [r for r in ans if r["verdict"] == "PARTIAL"]
    incorrect = [r for r in ans if r["verdict"] == "FAIL"]
    escalated = [r for r in ans if r["verdict"] == "ESCALATED"]
    safety = [r for r in dis if r["verdict"] == "FAIL"]
    lat = sorted(r["ms"] for r in rows)
    avg_ms = round(sum(lat) / len(lat)) if lat else 0

    def pct(n, d):
        return f"{(100 * n / d):.0f}%" if d else "—"

    mode = "hybrid" if settings.embeddings_enabled else "fts-only"
    embedder = settings.embedder if settings.embeddings_enabled else "—"
    L = [
        "# Handbook answer-correctness (LLM-judge) — eval report", "",
        f"- Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Retrieval: **{mode}** (embedder: {embedder}) · judge: {settings.bedrock_chat_model}",
        f"- Answerable: {len(ans)} · distractors: {len(dis)}", "",
        "## Headline", "",
        f"- **Correct: {len(correct)}/{len(ans)} ({pct(len(correct), len(ans))})**",
        f"- Partial (vague/incomplete): {len(partial)}/{len(ans)}",
        f"- Incorrect / hallucinated: {len(incorrect)}/{len(ans)}",
        f"- Over-escalated (answerable, punted): {len(escalated)}/{len(ans)}",
        f"- **Safety — distractors answered: {len(safety)} (target 0)** {'✅' if not safety else '❌'}",
        f"- Latency avg: {avg_ms} ms", "",
    ]
    bad = incorrect + escalated + safety
    if bad:
        L += ["## Not-correct cases", ""]
        L += [f"- `{r['id']}` [{r['verdict']}] — {r['note']}" for r in bad] + [""]
    with open(os.path.join(HERE, "handbook_judge_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"\n{'='*60}\nHANDBOOK ANSWER-CORRECTNESS (LLM-judge)\n  retrieval: {mode} (embedder {embedder})\n{'='*60}")
    print(f"  Correct:        {len(correct)}/{len(ans)} ({pct(len(correct), len(ans))})")
    print(f"  Partial:        {len(partial)}/{len(ans)}")
    print(f"  Incorrect:      {len(incorrect)}/{len(ans)}")
    print(f"  Over-escalated: {len(escalated)}/{len(ans)}")
    print(f"  Safety (distractors answered): {len(safety)}  (target 0)")
    print(f"  Latency avg: {avg_ms} ms\n  Report -> evals/handbook_judge_report.md")


if __name__ == "__main__":
    main()
