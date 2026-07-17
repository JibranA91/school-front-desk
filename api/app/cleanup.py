"""Knowledge-hygiene lifecycle: supersession + the deterministic expiry sweep.

Kept independent of app.main (main imports this) to avoid an import cycle, so
entity mutations here go straight through the models. The pluggable detection
engine (Check / CleanupEngine) will also live in this module in a later phase.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _snapshot(e: models.KbEntity) -> dict:
    """Restorable pre-change state for the changelog (mirrors main._entity_state)."""
    return {
        "type": e.type,
        "name": e.name,
        "attributes": dict(e.attributes or {}),
        "sources": list(e.sources or []),
        "enabled": e.enabled,
    }


def restore_superseded(db: Session, override: models.KbEntity, actor: str = "Auto-sync") -> list[str]:
    """Re-enable every node this override disabled (its outgoing `supersedes`
    edges). Call this BEFORE removing an override, so a lapsed temporary fact
    hands control back to the handbook fact it replaced. Logs a revertable entry
    per restored node; does not commit. Returns the restored entity ids."""
    edges = db.scalars(
        select(models.KbRelationship).where(
            models.KbRelationship.rel == "supersedes",
            models.KbRelationship.src_id == override.id,
        )
    ).all()
    restored: list[str] = []
    for edge in edges:
        target = db.get(models.KbEntity, edge.dst_id)
        if target is None or target.enabled:
            continue
        before = _snapshot(target)
        target.enabled = True
        db.add(
            models.ChangelogEntry(
                actor=actor,
                action=f"Re-enabled {target.name} (override '{override.name}' removed)",
                entity_id=target.id,
                is_diff=False,
                snapshot={"entity_id": target.id, "before": before},
            )
        )
        restored.append(target.id)
    return restored


def _remove(db: Session, e: models.KbEntity, actor: str) -> None:
    """Delete an entity + its incident edges; keep changelog history (unlinked);
    log a revertable removal. Self-contained twin of main._delete_entity_cascade
    (avoids importing app.main)."""
    before = _snapshot(e)
    eid, name = e.id, e.name
    db.query(models.KbRelationship).filter(
        (models.KbRelationship.src_id == eid) | (models.KbRelationship.dst_id == eid)
    ).delete(synchronize_session=False)
    db.query(models.ChangelogEntry).filter(
        models.ChangelogEntry.entity_id == eid
    ).update({models.ChangelogEntry.entity_id: None}, synchronize_session=False)
    db.delete(e)
    db.add(
        models.ChangelogEntry(
            actor=actor,
            action=f"Removed expired {name}",
            entity_id=None,
            is_diff=False,
            snapshot={"entity_id": eid, "before": before},
        )
    )


def sweep_expired(db: Session, actor: str = "Auto-sync") -> dict:
    """Deterministically clear expired overrides and restore what they
    superseded. An entity is expired when its `attributes.expires` (ISO date
    string) is before today. Authored/seed expired facts are removed; an expired
    handbook fact is only disabled (handbook is never deleted). Restoration runs
    first, so a lapsed override hands back to the handbook fact it replaced.

    No LLM, no operator round-trip — the operator consented to the date when the
    fact was authored. Runs on startup and before each scan (the seed of the
    future scheduled clean). Returns {"removed": [...], "restored": [...]}."""
    today = today_iso()
    entities = db.scalars(select(models.KbEntity)).all()
    expired = [
        e
        for e in entities
        if isinstance((e.attributes or {}).get("expires"), str)
        and (e.attributes or {})["expires"] < today
    ]
    removed: list[str] = []
    restored: list[str] = []
    for e in expired:
        restored += restore_superseded(db, e, actor=actor)
        if e.id.startswith("hb-"):
            if e.enabled:
                before = _snapshot(e)
                e.enabled = False
                db.add(
                    models.ChangelogEntry(
                        actor=actor,
                        action=f"Disabled expired {e.name}",
                        entity_id=e.id,
                        is_diff=False,
                        snapshot={"entity_id": e.id, "before": before},
                    )
                )
        else:
            _remove(db, e, actor)
        removed.append(e.id)
    if expired:
        db.commit()
    return {"removed": removed, "restored": restored}
