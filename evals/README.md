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

## Menu-accuracy eval (`menu_evals.py`)

A second, focused harness for the **live lunch menu** across days — the one place
the front desk gives a *live, changing* fact where a wrong answer has a concrete
cost (a parent packs the wrong food, or skips packing). Where `run_evals.py`
scores the escalation *decision*, this scores answer *content*:

- `menu_dataset.json` — cases for **today, tomorrow, each weekday (Mon–Fri), the
  whole week, and the weekend**. `today`/`tomorrow` are date-relative, so the
  runner resolves each `target` to a concrete date at run time and reads the
  **actual seeded menu from the DB** as ground truth — the eval is correct on
  whatever day (including a weekend) it runs.
- `menu_evals.py` — runs each case through the real agent and checks:
  1. **Right day** — the answer names the dish actually posted for that day.
  2. **No cross-day leak** — it must not mention *another* day's signature dish
     (serving Wednesday's pasta for a Friday question is a correctness failure).
  3. **Weekend honesty** — with no menu posted, the agent must not fabricate one.
     Fabrication is the safety failure; a plain "closed weekends" is ideal; a
     safe escalation to staff scores 🟡 (safe but improvable).
- `menu_report.md` — the latest run, including every raw answer for eyeballing.

Run (same as above):
```
api/.venv/Scripts/python.exe evals/menu_evals.py
```
The current week's menu is seeded idempotently at the start, so the set is
self-contained. It seeds only `menu_days` and calls `answer_question`
in-process, so it does **not** touch the knowledge graph or the operator inbox.

## Notes / known limitations
- The LLM path is **non-deterministic**: borderline answerable questions (e.g.
  snow-day, toy-guns) can flip between a grounded answer and a hand-off across
  runs. Expect ±1–2 cases of variance. Sensitive escalation is deterministic
  (a code-level safety net, not the model).
- This is a thin harness (decision + citation validity). Faithfulness /
  answer-correctness via LLM-as-judge is described in `.plans/spec.md` as the
  next step. The menu eval is a first step in that direction — it validates
  answer *content* (which day's dish) for the one live-data source.
