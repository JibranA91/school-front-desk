"""Golden-set eval for the knowledge-hygiene ("Clean") engine.

Plants known-bad fixtures — an identical duplicate, a same-topic field
contradiction, and an expired override that supersedes a disabled node — runs
the real CleanupEngine (deterministic Quick tier, no LLM), and asserts:

  * the expired override is auto-swept, and the node it superseded is restored;
  * the duplicate is flagged (redundancy);
  * the contradiction is flagged (contradiction).

Every fixture is removed afterwards (try/finally), so the DB is left untouched.

It also stages LIVE demo fixtures for a UI walkthrough (kept out of the default
seed so parents never see broken data):

    uv run python evals/cleanup_evals.py            # run the golden eval
    uv run python evals/cleanup_evals.py --plant    # stage demo-* fixtures (live)
    uv run python evals/cleanup_evals.py --cleanup  # remove the demo-* fixtures

Inside the api container (has the app env + DB):
    docker compose exec api uv run --no-dev python /app/evals/cleanup_evals.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, "..", "api"), os.path.join(HERE, "..")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.db import SessionLocal  # noqa: E402
from app import cleanup, models  # noqa: E402


def _today():
    return datetime.now(timezone.utc).date()


def _entity(eid, etype, name, attrs, *, enabled=True, source="eval"):
    return models.KbEntity(
        id=eid, type=etype, name=name, attributes=attrs, sources=[source], enabled=enabled
    )


def _remove(db, ids):
    """Delete fixtures, their edges, and any changelog rows about them (by FK or
    by the restorable snapshot's entity_id). Leaves no trace — including the
    sweep's own 'Removed expired…' / 'Re-enabled…' entries for these fixtures."""
    from sqlalchemy import or_

    db.query(models.KbRelationship).filter(
        models.KbRelationship.src_id.in_(ids) | models.KbRelationship.dst_id.in_(ids)
    ).delete(synchronize_session=False)
    db.query(models.ChangelogEntry).filter(
        or_(
            models.ChangelogEntry.entity_id.in_(ids),
            models.ChangelogEntry.snapshot["entity_id"].astext.in_(ids),
        )
    ).delete(synchronize_session=False)
    db.query(models.KbEntity).filter(models.KbEntity.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


# --------------------------------------------------------------------------- #
# Golden eval
# --------------------------------------------------------------------------- #

EVAL_IDS = [
    "eval-dup-a", "eval-dup-b", "eval-con-a", "eval-con-b",
    "eval-hb-target", "eval-override",
]


def _plant_eval(db):
    past = (_today() - timedelta(days=3)).isoformat()
    dup_body = "Sunscreen is applied to every child before outdoor play."
    db.add_all([
        # identical name + body -> deterministic redundancy
        _entity("eval-dup-a", "Health", "Eval Sunscreen", {"body": dup_body}),
        _entity("eval-dup-b", "Health", "Eval Sunscreen", {"body": dup_body}),
        # same type + topic, shared field differs -> deterministic contradiction
        _entity("eval-con-a", "EvalPolicy", "Eval Late Fee", {"fee": "$1/min", "body": "Late fee is $1/min."}),
        _entity("eval-con-b", "EvalPolicy", "Eval Late Fee", {"fee": "$0", "body": "There is no late fee."}),
        # an expired override that superseded a disabled node
        _entity("eval-hb-target", "EvalHours", "Eval Hours source", {"body": "Open 7am."}, enabled=False),
        _entity("eval-override", "EvalHours", "Eval Hours override", {"body": "Open 8am.", "expires": past}),
    ])
    db.flush()
    db.add(models.KbRelationship(rel="supersedes", src_id="eval-override", dst_id="eval-hb-target"))
    db.commit()


def run_eval() -> int:
    db = SessionLocal()
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    try:
        _remove(db, EVAL_IDS)  # clean slate in case a prior run aborted
        _plant_eval(db)

        result = cleanup.CleanupEngine().scan(db, mode="quick")
        swept, findings = result["swept"], result["findings"]

        check("expired override auto-swept", "eval-override" in swept["removed"],
              f"removed={swept['removed']}")

        tgt = db.get(models.KbEntity, "eval-hb-target")
        check("superseded node restored",
              "eval-hb-target" in swept["restored"] and tgt is not None and tgt.enabled,
              f"restored={swept['restored']} enabled={getattr(tgt, 'enabled', None)}")

        dup = [f for f in findings if f["kind"] == "redundancy"
               and set(f["entities"]) == {"eval-dup-a", "eval-dup-b"}]
        check("duplicate flagged (redundancy)", dup,
              f"redundancy findings={[f['id'] for f in findings if f['kind'] == 'redundancy']}")

        con = [f for f in findings if f["kind"] == "contradiction"
               and set(f["entities"]) == {"eval-con-a", "eval-con-b"}]
        check("contradiction flagged", con,
              f"contradiction findings={[f['id'] for f in findings if f['kind'] == 'contradiction']}")
    finally:
        _remove(db, EVAL_IDS)  # always leave the DB as we found it
        db.close()

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{'=' * 56}\nCLEANUP ENGINE EVAL (deterministic Quick tier)\n{'=' * 56}")
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if not ok else ""))
    print(f"\n  {passed}/{len(checks)} checks passed.\n")

    with open(os.path.join(HERE, "cleanup_report.md"), "w", encoding="utf-8") as f:
        f.write(f"# Cleanup engine eval\n\n**{passed}/{len(checks)} checks passed.**\n\n")
        for name, ok, detail in checks:
            f.write(f"- {'✅' if ok else '❌'} {name}" + (f" — {detail}" if not ok else "") + "\n")
    return 0 if passed == len(checks) else 1


# --------------------------------------------------------------------------- #
# Live demo staging (opt-in; never in the default seed)
# --------------------------------------------------------------------------- #

DEMO_IDS = ["demo-dup-a", "demo-dup-b", "demo-con-older", "demo-con-newer", "demo-expiring"]


def plant_demo(db):
    from app.embeddings import embed_texts, entity_text

    _remove(db, DEMO_IDS)
    now = datetime.now(timezone.utc)
    soon = (_today() + timedelta(days=2)).isoformat()
    snack = "Afternoon snack is served at 3:00 PM every day."
    ents = [
        # A clean identical duplicate -> shows up in a Quick scan.
        _entity("demo-dup-a", "Meal", "Snack Time", {"body": snack}, source="Set by Demo"),
        _entity("demo-dup-b", "Meal", "Snack Time", {"body": snack}, source="Set by Demo"),
        # A same-topic conflict with distinct ages so the newer-vs-older
        # recommendation is meaningful (Deep scan flags it as a contradiction).
        _entity("demo-con-older", "Hours", "Friday Hours", {"body": "On Fridays the center closes at 5:00 PM."}, source="Set by Demo"),
        _entity("demo-con-newer", "Hours", "Updated Friday Hours", {"body": "On Fridays the center now closes at 3:00 PM."}, source="Set by Demo"),
        # A temporary fact expiring in 2 days -> "Expiring soon", and the sweep
        # will auto-remove it once the date passes.
        _entity("demo-expiring", "Holiday", "Book Fair Week", {"body": "During Book Fair week, drop-off moves to the gym.", "expires": soon}, source="Set by Demo"),
    ]
    for e in ents:
        db.add(e)
    # Make the conflict genuinely newer-vs-older.
    ents[2].created_at = now - timedelta(days=12)
    ents[3].created_at = now
    db.flush()
    vecs = embed_texts([entity_text(e) for e in ents])
    for e, v in zip(ents, vecs):
        e.embedding = v
    db.commit()
    print(
        "Planted demo fixtures (live): snack duplicate, a newer-vs-older Friday-hours "
        f"conflict, and one fact expiring {soon}.\n"
        "These are enabled + embedded, so run a scan to see them. Remove with --cleanup."
    )


def main():
    if "--plant" in sys.argv:
        db = SessionLocal()
        try:
            plant_demo(db)
        finally:
            db.close()
        return
    if "--cleanup" in sys.argv:
        db = SessionLocal()
        try:
            _remove(db, DEMO_IDS)
            print(f"Removed demo fixtures: {DEMO_IDS}")
        finally:
            db.close()
        return
    sys.exit(run_eval())


if __name__ == "__main__":
    main()
