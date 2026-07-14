"""Deterministic eval for the sensitive-topic classifier.

`app.escalation.classify_sensitive` is the code-level safety net that
force-escalates sensitive questions (health, medication, allergy, safety,
billing, custody) regardless of the model. It's the highest-leverage piece of
the "escalate rather than guess" guarantee — and, because it's a keyword
matcher, it's exactly where a subtle bug hides: matching keywords as raw
substrings once mis-escalated "what will be for lunch tomorrow?" as health
("will" contains "ill") and "is the daycare licensed?" ("licensed" → "lice").

This harness pins that behavior with a golden set — no LLM, no DB, runs in
milliseconds — so both directions are guarded:
  * SENSITIVE questions still classify to the right category (no false negative
    weakens the safety net), and
  * BENIGN questions — including substring TRAPS — return None (no false
    positive turns a routine question into a staff escalation).

Writes evals/escalation_report.md and prints a summary. Exits non-zero on any
failure, so it can gate CI.

Run:
    api/.venv/Scripts/python.exe evals/escalation_evals.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, "..", "api"), os.path.join(HERE, "..")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app import escalation  # noqa: E402


def main() -> int:
    with open(os.path.join(HERE, "escalation_dataset.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    rows = []
    for c in cases:
        expected = c.get("expected")  # str category or None
        got = escalation.classify_sensitive(c["text"])
        ok = got == expected
        kind = "trap" if c.get("trap") else ("sensitive" if expected else "benign")
        rows.append({
            "id": c["id"], "text": c["text"], "expected": expected, "got": got,
            "ok": ok, "kind": kind, "trap": c.get("trap"),
        })

    return write_report(rows)


def write_report(rows: list[dict]) -> int:
    total = len(rows)
    passed = sum(1 for r in rows if r["ok"])
    failed = [r for r in rows if not r["ok"]]

    sensitive = [r for r in rows if r["kind"] == "sensitive"]
    traps = [r for r in rows if r["kind"] == "trap"]
    benign = [r for r in rows if r["kind"] == "benign"]

    # The two failure modes that matter, named explicitly.
    false_negatives = [r for r in sensitive if not r["ok"]]  # missed a sensitive topic
    false_positives = [r for r in (traps + benign) if not r["ok"]]  # escalated a benign one

    def cnt(group):
        g = list(group)
        return f"{sum(1 for r in g if r['ok'])}/{len(g)}"

    lines: list[str] = []
    lines.append("# Escalation classifier — eval report")
    lines.append("")
    lines.append(f"- Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("- Target: `app.escalation.classify_sensitive` (deterministic, no LLM)")
    lines.append(f"- Cases: {total}")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(f"- **False negatives — missed a sensitive topic: {len(false_negatives)} (target 0)** "
                 f"{'✅' if not false_negatives else '❌'}")
    lines.append(f"- **False positives — escalated a benign question: {len(false_positives)} (target 0)** "
                 f"{'✅' if not false_positives else '❌'}")
    lines.append(f"- Passed: **{passed}/{total}**")
    lines.append(f"- Sensitive (right category): {cnt(sensitive)}")
    lines.append(f"- Substring traps (stay None): {cnt(traps)}")
    lines.append(f"- Benign (stay None): {cnt(benign)}")
    lines.append("")

    if failed:
        lines.append("## ❌ Failures")
        lines.append("")
        for r in failed:
            lines.append(f"- `{r['id']}` — \"{r['text']}\" → got `{r['got']}`, expected `{r['expected']}`")
        lines.append("")

    lines.append("## All cases")
    lines.append("")
    lines.append("| ✓ | id | kind | text | expected | got | note |")
    lines.append("|---|----|------|------|----------|-----|------|")
    for r in rows:
        t = r["text"].replace("|", "\\|")
        note = (r["trap"] or "").replace("|", "\\|")
        lines.append(
            f"| {'✅' if r['ok'] else '❌'} | {r['id']} | {r['kind']} | {t} | "
            f"{r['expected']} | {r['got']} | {note} |"
        )
    lines.append("")

    with open(os.path.join(HERE, "escalation_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Console summary
    print(f"\n{'='*60}")
    print("ESCALATION CLASSIFIER EVAL")
    print(f"{'='*60}")
    print(f"  False negatives (missed sensitive): {len(false_negatives)}  (target 0)  "
          f"{'PASS' if not false_negatives else 'FAIL'}")
    print(f"  False positives (escalated benign): {len(false_positives)}  (target 0)  "
          f"{'PASS' if not false_positives else 'FAIL'}")
    print(f"  Passed:            {passed}/{total}")
    print(f"  Sensitive:         {cnt(sensitive)}")
    print(f"  Substring traps:   {cnt(traps)}")
    print(f"  Benign:            {cnt(benign)}")
    print(f"\n  Report written to evals/escalation_report.md")
    for r in failed:
        print(f"    [FAIL] {r['id']}: got {r['got']}, expected {r['expected']}  ({r['text']!r})")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
