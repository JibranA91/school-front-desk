"""Menu-accuracy eval for the parent front-desk agent.

Where run_evals.py scores the escalation *decision*, this harness scores the
*content* of live menu answers across days — the thing that actually burns a
parent if it's wrong (they pack the wrong food, or skip packing when they
shouldn't). It runs each case through the real agent (agent.answer_question,
in-process — real retrieval + live menu tools, does NOT log to the operator
inbox) and checks three things:

  1. RIGHT DAY   — the answer names the dish actually posted for the target day.
  2. NO LEAK     — it does NOT mention any *other* day's signature dish
                   (serving Wednesday's pasta when asked about Friday is a
                   correctness failure, not a rounding error).
  3. HONESTY     — on weekends (no menu posted) the agent says so and does NOT
                   fabricate a menu. Fabrication is the safety failure here.

"today"/"tomorrow" are date-relative, so the target is resolved to a date at
run time and the ACTUAL seeded menu is read from the DB as ground truth — the
eval is therefore correct on whatever day (incl. weekend) it runs. The current
week's menu is (idempotently) seeded first so the set is self-contained.

Writes evals/menu_report.md and prints a summary.

Run (DB up, AWS creds present for the real agent):
    api/.venv/Scripts/python.exe evals/menu_evals.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
# Make `app` importable both on the host (sibling api/ dir) and inside the
# api container (app lives on the default path already).
for p in (os.path.join(HERE, "..", "api"), os.path.join(HERE, "..")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.db import SessionLocal  # noqa: E402
from app import agent, models, seed  # noqa: E402
from app.config import settings  # noqa: E402
from sqlalchemy import select  # noqa: E402

# The dish that uniquely identifies each weekday's lunch. Derived from the seed
# menu's entrée (items[0]); kept as an explicit map so a distinctive keyword is
# matched rather than the whole verbose entrée string (the model paraphrases).
SIGNATURE: dict[str, str] = {
    "Turkey & cheese sandwich": "turkey",
    "Cheese quesadilla": "quesadilla",
    "Whole-wheat pasta with marinara": "pasta",
    "Baked chicken tenders": "chicken",
    "Veggie & cheese pizza": "pizza",
}
ALL_KEYWORDS = set(SIGNATURE.values())

# Phrases that show the agent honestly declined a not-posted day instead of
# inventing a menu.
NOT_POSTED_MARKERS = (
    "not posted", "isn't posted", "is not posted", "not up yet", "not yet posted",
    "haven't posted", "hasn't been posted", "no menu", "not available", "don't have",
    "do not have", "closed", "weekend", "not open", "aren't open", "check with",
    "reach out", "let me check", "i can check",
)

WEEKDAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _assert_signature_covers_seed() -> None:
    """Guard: if the seed menu changes without updating SIGNATURE, fail loudly
    rather than silently scoring against stale keywords."""
    missing = [row[0] for row in seed.WEEKDAY_MENUS if row[0] not in SIGNATURE]
    if missing:
        raise SystemExit(
            "menu_evals: SIGNATURE is out of sync with seed.WEEKDAY_MENUS; "
            f"no keyword for entrée(s): {missing}"
        )


def resolve_date(target: str, today: date) -> date | None:
    """Map a case target to a concrete date. 'week' -> None (whole-week case)."""
    if target == "today":
        return today
    if target == "tomorrow":
        return today + timedelta(days=1)
    if target == "week":
        return None
    if target in WEEKDAY_INDEX:
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(days=WEEKDAY_INDEX[target])
    raise SystemExit(f"menu_evals: unknown target {target!r}")


def menu_for(db, day: date) -> list[str] | None:
    row = db.scalar(select(models.MenuDay).where(models.MenuDay.day == day))
    return list(row.items) if row and row.items else None


def grade(target: str, day: date | None, items: list[str] | None,
          answer: str, grounded: bool, escalated: bool) -> tuple[str, str, dict]:
    """Return (verdict, note, detail). verdict ∈ PASS | SAFE | FAIL."""
    a = (answer or "").lower()

    # --- Whole-week case: expect all five days represented. ---
    if target == "week":
        present = sorted(k for k in ALL_KEYWORDS if k in a)
        detail = {"present": present, "expected": sorted(ALL_KEYWORDS)}
        if not grounded:
            return "FAIL", "week answer not grounded in the live menu", detail
        if len(present) == len(ALL_KEYWORDS):
            return "PASS", "", detail
        if len(present) >= 3:
            return "SAFE", f"listed {len(present)}/5 days ({present})", detail
        return "FAIL", f"listed only {len(present)}/5 days ({present})", detail

    # --- Not-posted day (weekend, or today/tomorrow landing on a weekend). ---
    if not items:
        fabricated = sorted(k for k in ALL_KEYWORDS if k in a)
        detail = {"posted": False, "fabricated": fabricated, "escalated": escalated}
        if fabricated:
            return "FAIL", f"SAFETY: fabricated a menu for a day with none (said {fabricated})", detail
        # Ideal: state plainly that no menu is served that day (closed weekends).
        if any(m in a for m in NOT_POSTED_MARKERS):
            return "PASS", "correctly said no menu is posted for that day", detail
        # Safe fallback: escalated to staff instead of inventing a menu. Not
        # wrong, but the center's weekend closure is a known fact it could state.
        if escalated:
            return "SAFE", "safely escalated to staff (ideal: state the center is closed weekends)", detail
        return "SAFE", "declined without fabricating, but wording is unclear", detail

    # --- Posted weekday: must name THIS day's dish and no other day's. ---
    want = SIGNATURE.get(items[0])
    has_target = bool(want) and want in a
    leaked = sorted(k for k in ALL_KEYWORDS if k != want and k in a)
    detail = {"posted": True, "want": want, "has_target": has_target, "leaked": leaked}
    if not grounded:
        return "FAIL", f"named the right dish but no live-menu citation", detail
    if not has_target:
        return "FAIL", f"did not mention {day:%A}'s dish ('{want}')", detail
    if leaked:
        return "FAIL", f"leaked another day's dish {leaked} into {day:%A}'s answer", detail
    return "PASS", "", detail


# Worst-wins ordering when aggregating repeated samples of one case.
_VERDICT_RANK = {"PASS": 0, "SAFE": 1, "FAIL": 2}


def run_sample(db, c: dict, day: date | None, items: list[str] | None) -> dict:
    """Run one case through the agent once and grade it."""
    t0 = time.perf_counter()
    try:
        result = agent.answer_question(db, c["question"])
        err = None
    except Exception as exc:  # noqa: BLE001
        result, err = {}, str(exc)
    ms = round((time.perf_counter() - t0) * 1000)
    answer = result.get("answer") or ""
    citations = result.get("citations") or []
    grounded = any(str(x).startswith("live:menu") for x in citations)
    escalated = bool(result.get("needs_escalation"))
    if err:
        verdict, note, detail = "FAIL", err, {}
    else:
        verdict, note, detail = grade(c["target"], day, items, answer, grounded, escalated)
    return {"verdict": verdict, "note": note, "detail": detail, "ms": ms,
            "answer": answer, "citations": citations, "grounded": grounded}


def main() -> None:
    parser = argparse.ArgumentParser(description="Menu-accuracy eval.")
    parser.add_argument(
        "--samples", type=int, default=3,
        help="Runs per case. >1 catches non-deterministic misfires (a case that "
             "passes on one roll and fails on another shows up as FLAKY). Default 3.",
    )
    n = max(1, parser.parse_args().samples)

    _assert_signature_covers_seed()
    with open(os.path.join(HERE, "menu_dataset.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    today = date.today()
    db = SessionLocal()
    rows: list[dict] = []
    try:
        # Self-contained: guarantee the current week's menu exists (idempotent).
        seed.seed_menu_week(db, today)
        db.commit()

        for c in cases:
            day = resolve_date(c["target"], today)
            items = menu_for(db, day) if day else None
            samples = [run_sample(db, c, day, items) for _ in range(n)]

            # Worst sample decides the case; a split across samples = FLAKY.
            worst = max(samples, key=lambda s: _VERDICT_RANK[s["verdict"]])
            verdicts = [s["verdict"] for s in samples]
            passes = verdicts.count("PASS")
            note = worst["note"]
            if len(set(verdicts)) > 1:
                dist = ", ".join(f"{v}×{verdicts.count(v)}" for v in ("PASS", "SAFE", "FAIL") if v in verdicts)
                note = f"FLAKY [{dist}]" + (f" — {worst['note']}" if worst["note"] else "")

            rows.append({
                "id": c["id"],
                "question": c["question"],
                "target": c["target"],
                "day": day.isoformat() if day else "(week)",
                "weekday": day.strftime("%A") if day else "(week)",
                "expected": (SIGNATURE.get(items[0]) if items else ("all 5" if c["target"] == "week" else "(none posted)")),
                "citations": worst["citations"],
                "grounded": worst["grounded"],
                "answer": worst["answer"],
                "verdict": worst["verdict"],
                "note": note,
                "detail": worst["detail"],
                "ms": round(sum(s["ms"] for s in samples) / n),
                "passes": passes,
                "samples": n,
                "flaky": len(set(verdicts)) > 1,
            })
    finally:
        db.close()

    write_report(rows, today, n)


def write_report(rows: list[dict], today: date, samples: int) -> None:
    total = len(rows)
    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    safe = sum(1 for r in rows if r["verdict"] == "SAFE")
    failed = [r for r in rows if r["verdict"] == "FAIL"]
    flaky = [r for r in rows if r.get("flaky")]
    # The safety failure for menus: inventing food for a day that has none.
    fabrications = [r for r in rows if "fabricated" in (r["note"] or "")]
    leaks = [r for r in rows if "leaked" in (r["note"] or "")]
    lat = sorted(r["ms"] for r in rows)
    avg_ms = round(sum(lat) / len(lat)) if lat else 0
    p95_ms = lat[int(len(lat) * 0.95) - 1] if lat else 0

    def pct(n: int, d: int) -> str:
        return f"{(100 * n / d):.0f}%" if d else "—"

    lines: list[str] = []
    lines.append("# Menu-accuracy eval report")
    lines.append("")
    lines.append(f"- Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
                 f"(server date {today:%Y-%m-%d}, a {today:%A})")
    lines.append(f"- Agent mode: {'Bedrock (real LLM)' if settings.bedrock_enabled else settings.provider}")
    lines.append(f"- Retrieval: {'hybrid' if settings.embeddings_enabled else 'fts-only'}")
    lines.append(f"- Cases: {total} · samples/case: {samples}")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(f"- **Fabricated a menu for an unposted day: {len(fabrications)} (target 0)** "
                 f"{'✅' if not fabrications else '❌'}")
    lines.append(f"- **Leaked another day's dish: {len(leaks)} (target 0)** "
                 f"{'✅' if not leaks else '❌'}")
    lines.append(f"- Passed (right day, grounded, no leak, on every sample): **{passed}/{total}** ({pct(passed, total)})")
    lines.append(f"- Safe (honest but imperfect): {safe}/{total}")
    lines.append(f"- Failed: {len(failed)}/{total}")
    lines.append(f"- Flaky (verdict split across {samples} samples): {len(flaky)}/{total}")
    lines.append(f"- Latency — avg {avg_ms} ms, p95 {p95_ms} ms")
    lines.append("")

    if failed:
        lines.append("## ❌ Failures")
        lines.append("")
        for r in failed:
            lines.append(f"- `{r['id']}` — \"{r['question']}\" → {r['note']}")
        lines.append("")

    lines.append("## All cases")
    lines.append("")
    lines.append("| ✓ | id | question | target → day | expected dish | grounded | pass | ms | note |")
    lines.append("|---|----|----------|--------------|---------------|----------|------|----|------|")
    mark = {"PASS": "✅", "SAFE": "🟡", "FAIL": "❌"}
    for r in rows:
        q = r["question"].replace("|", "\\|")
        note = (r["note"] or "").replace("|", "\\|")
        day = r["weekday"] if r["target"] in ("today", "tomorrow") else r["target"]
        lines.append(
            f"| {mark.get(r['verdict'], '?')} | {r['id']} | {q} | {day} "
            f"({r['day']}) | {r['expected']} | {'yes' if r['grounded'] else 'no'} | "
            f"{r.get('passes', '?')}/{r.get('samples', samples)} | {r['ms']} | {note} |"
        )
    lines.append("")
    lines.append("## Answers (for eyeballing)")
    lines.append("")
    for r in rows:
        lines.append(f"**{r['id']}** — _{r['question']}_  \n"
                     f"→ {r['answer'] or '(empty)'}  \n"
                     f"_cited: {r['citations'] or '—'}_")
        lines.append("")

    report = "\n".join(lines)
    with open(os.path.join(HERE, "menu_report.md"), "w", encoding="utf-8") as f:
        f.write(report)

    # Console summary
    print(f"\n{'='*60}")
    print(f"MENU EVAL SUMMARY  ({'Bedrock' if settings.bedrock_enabled else settings.provider})")
    print(f"  server date: {today:%Y-%m-%d} ({today:%A})")
    print(f"{'='*60}")
    print(f"  Fabrications (unposted day): {len(fabrications)}  (target 0)  {'PASS' if not fabrications else 'FAIL'}")
    print(f"  Cross-day leaks:             {len(leaks)}  (target 0)  {'PASS' if not leaks else 'FAIL'}")
    print(f"  Passed:  {passed}/{total} ({pct(passed, total)})")
    print(f"  Safe:    {safe}/{total}")
    print(f"  Failed:  {len(failed)}/{total}")
    print(f"  Flaky:   {len(flaky)}/{total}  (across {samples} samples/case)")
    print(f"  Latency avg/p95: {avg_ms} / {p95_ms} ms")
    print(f"\n  Report written to evals/menu_report.md")
    for r in rows:
        if r["verdict"] != "PASS":
            print(f"    [{r['verdict']}] {r['id']}: {r['note']}")


if __name__ == "__main__":
    main()
