# Evals — parent front-desk agent

Offline golden-set eval for the parent agent, grounded in the seeded graph +
the ingested handbook. The headline metric is **safety**, not raw accuracy: the
agent must never give a confident, grounded answer to a **sensitive** or
**unknown / out-of-scope** question. A safe escalation is an acceptable miss; a
confident wrong answer is the failure that sinks trust.

## Files
- `dataset.json` — labeled cases. Each has an `expected` decision:
  - `answer` — a grounded, cited answer is expected (incl. grounded *negative*
    answers to "do you offer X?" from the authoritative roster).
  - `escalate_sensitive` — must escalate (health, medication, allergy, safety,
    billing dispute, custody), even if a policy exists.
  - `escalate_gap` — not in the knowledge base; hand off, don't guess.
  - `decline_oos` — out of scope for a daycare front desk.
  - `greeting` — small talk; warm reply, not logged.
- `run_evals.py` — runs each case through `agent.answer_question` in-process
  (real retrieval + escalation path; does NOT log to the operator inbox), scores
  it, prints a summary, and writes `report.md`.
- `report.md` — the latest run.

## Run
DB up + AWS creds present (for the real agent):
```
./.venv/Scripts/python.exe evals/run_evals.py
```
Without creds it runs the mock agent (retrieval + keyword), useful as a smoke
test but not representative of the shipped behavior.

## What it scores
- **Safety gate** — wrongful confident answers on sensitive/unknown/out-of-scope
  (target **0**).
- **Escalation decision accuracy** — answer vs escalate vs hand-off.
- **Grounding** — answered questions carry a real citation.
- **Over-escalation** — answerable questions that were punted (the *safe* error).
- **Latency** — avg / p95 per query.

## Notes / known limitations
- The LLM path is **non-deterministic**: borderline answerable questions (e.g.
  snow-day, toy-guns) can flip between a grounded answer and a hand-off across
  runs. Expect ±1–2 cases of variance. Sensitive escalation is deterministic
  (a code-level safety net, not the model).
- This is a thin harness (decision + citation validity). Faithfulness /
  answer-correctness via LLM-as-judge is described in `.plans/spec.md` as the
  next step.
