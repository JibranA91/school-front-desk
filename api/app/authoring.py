"""Operator chat-to-author agent.

`propose`: the LLM (Sonnet) turns a plain-language instruction into precise graph
operations against the current entities; code then looks up the real current
value and deterministically flags conflicts (an update that overwrites a
differing existing value). `apply`: write the confirmed changes to the graph,
re-embed, and append changelog entries.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import models
from app.config import settings


def _norm(s: str) -> str:
    """Loosely normalize a name for near-duplicate detection."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _entity_state(e: models.KbEntity) -> dict:
    """A restorable snapshot of an entity, stored on the changelog for revert."""
    return {
        "type": e.type,
        "name": e.name,
        "attributes": dict(e.attributes or {}),
        "sources": list(e.sources or []),
        "enabled": e.enabled,
    }


def _serialize_graph(db: Session) -> str:
    rows = db.scalars(select(models.KbEntity)).all()
    lines = []
    for e in rows:
        lines.append(f"- id={e.id} | type={e.type} | name={e.name} | attributes={e.attributes}")
    return "\n".join(lines)


def propose(db: Session, instruction: str) -> dict:
    from pydantic import BaseModel, Field

    from app.llm import get_chat_model

    class Operation(BaseModel):
        action: Literal["add", "update"] = Field(
            description="update = change an existing entity's field; add = a brand-new entity."
        )
        entity_id: str = Field(
            description="For update: the exact existing id. For add: a new kebab-case id."
        )
        entity_type: str = Field(description="Holiday, Hours, Tuition, Policy, Meal, Enrollment, …")
        name: str = Field(description="Human-readable entity name.")
        field: str = Field(
            description="The attribute key to set, e.g. 'open', 'monthly', 'date', 'status', 'body'."
        )
        new_value: str = Field(description="The new value, always as a string.")
        body: str = Field(
            description="The complete corrected fact as ONE plain-language sentence a parent "
            "would read. This is the canonical statement the front desk answers from, so it "
            "MUST fully reflect this change and stay consistent with new_value (never leave "
            "prose that contradicts the structured value). Keep any existing detail that "
            "still applies."
        )
        supersedes: str | None = Field(
            default=None,
            description="Set ONLY when this fact corrects/replaces a read-only handbook "
            "entity (id starts 'hb-'): the handbook id being replaced. Use action='add' "
            "with a new id in that case; the handbook fact is disabled, not edited.",
        )
        expires: str | None = Field(
            default=None,
            description="ISO date (YYYY-MM-DD) when a TEMPORARY change stops applying "
            "(a holiday closure, a 'this week' note, etc.). Null for permanent facts.",
        )

    class Proposal(BaseModel):
        summary: str = Field(description="Short label for this change, e.g. 'Weekday opening time'.")
        operations: list[Operation]

    today = datetime.now(timezone.utc).date().isoformat()
    system = (
        "You maintain a childcare center's knowledge graph. Given the operator's plain-language "
        f"instruction and the current entities, output the MINIMAL set of operations to apply. "
        f"Today is {today}.\n"
        "- STRONGLY PREFER updating an existing entity that already covers this topic: use "
        "action='update' with that entity's EXACT id. Scan the current entities for one that is "
        "about the same thing, even if worded differently. Never create a new entity that would "
        "duplicate or contradict an existing one.\n"
        "- HANDBOOK FACTS ARE READ-ONLY. Entities whose id starts with 'hb-' come from the "
        "official handbook and must NEVER be updated. If the instruction corrects or contradicts "
        "a handbook fact, use action='add' with a NEW kebab-case id for the corrected fact and "
        "set `supersedes` to that handbook id — the handbook fact is disabled (kept as the "
        "record) and your new fact takes over.\n"
        "- Use action='add' with a new kebab-case id ONLY for genuinely new information no "
        "existing entity covers (or for a handbook override as above).\n"
        "- If the change is TEMPORARY (a holiday closure, a 'this week' note, anything with an "
        "end date), set `expires` to the ISO date (YYYY-MM-DD) it stops applying. Null otherwise.\n"
        "- `body` is the canonical, parent-facing statement of the fact — our answers to parents "
        "are grounded in it. For EVERY operation, write `body` as a complete sentence stating the "
        "corrected fact, so the wording can never contradict the structured value you set.\n"
        "- new_value is always a string. Be precise; do not invent unrelated changes.\n\n"
        f"CURRENT ENTITIES:\n{_serialize_graph(db)}"
    )
    model = get_chat_model(settings.chat_model).with_structured_output(Proposal)
    proposal = model.invoke([("system", system), ("human", instruction)])

    # Backstop against the model spawning a contradictory near-duplicate: if it
    # emits an "add" whose name matches an existing entity, retarget to update it.
    by_name = {}
    for x in db.scalars(select(models.KbEntity)).all():
        by_name.setdefault(_norm(x.name), x)

    changes: list[dict] = []
    has_conflict = False
    for op in proposal.operations:
        e = db.get(models.KbEntity, op.entity_id)
        if e is None and not op.supersedes:
            twin = by_name.get(_norm(op.name))
            if twin is not None:
                op.entity_id = twin.id
                e = twin
        old_value = (e.attributes or {}).get(op.field) if e is not None else None
        action = "update" if e is not None else "add"
        is_conflict = (
            action == "update"
            and old_value not in (None, "")
            and str(old_value) != op.new_value
        )
        has_conflict = has_conflict or is_conflict
        changes.append(
            {
                "action": action,
                "entity_id": op.entity_id,
                "entity_type": op.entity_type,
                "name": op.name,
                "field": op.field,
                "old_value": None if old_value is None else str(old_value),
                "new_value": op.new_value,
                "body": op.body,
                "is_conflict": is_conflict,
                "source": (e.sources[0] if e and e.sources else None) if e else None,
                "supersedes": op.supersedes,
                "expires": op.expires,
            }
        )
    return {"summary": proposal.summary, "changes": changes, "has_conflict": has_conflict}


def apply(
    db: Session,
    changes: list[dict],
    actor: str,
    summary: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    accept_conflicts: bool = True,
) -> dict:
    """Apply confirmed changes to the graph, re-embed, and log to the changelog
    (one entry per entity, not per field)."""
    from app.embeddings import embed_texts, entity_text

    # Apply all fields; group by entity so the changelog gets one line per change.
    touched: dict[str, models.KbEntity] = {}
    per_entity: dict[str, list[dict]] = {}
    # Pre-change state per entity (None = newly created), for one-click revert.
    before_state: dict[str, dict | None] = {}
    for c in changes:
        if c.get("is_conflict") and not accept_conflicts:
            continue
        eid = c["entity_id"]
        if eid.startswith("hb-"):
            continue  # handbook is immutable; corrections arrive as a new node + `supersedes`
        e = db.get(models.KbEntity, eid)
        if eid not in before_state:
            before_state[eid] = _entity_state(e) if e is not None else None
        if e is None:
            e = models.KbEntity(
                id=c["entity_id"],
                type=c["entity_type"],
                name=c["name"],
                attributes={},
                sources=[f"Set by {actor}"],
            )
            db.add(e)
            db.flush()
        attrs = dict(e.attributes or {})
        attrs[c["field"]] = c["new_value"]
        # Keep the canonical parent-facing `body` in lockstep with the structured
        # change, so the prose the agent reads can never go stale (the bug where
        # status flipped to "open" but body still said "closed").
        if c.get("body"):
            attrs["body"] = c["body"]
        if c.get("expires"):
            attrs["expires"] = c["expires"]
        e.attributes = attrs
        flag_modified(e, "attributes")
        touched[e.id] = e
        per_entity.setdefault(e.id, []).append(c)

    for eid, cs in per_entity.items():
        e = touched[eid]
        # Prefer the field that overwrote an existing value for the diff display.
        rep = next((c for c in cs if c.get("old_value")), cs[0])
        was_add = all(c["action"] == "add" for c in cs)
        db.add(
            models.ChangelogEntry(
                actor=actor,
                actor_user_id=actor_user_id,
                action=summary or (("Added " if was_add else "Updated ") + e.name),
                entity_id=e.id,
                before=rep.get("old_value"),
                after=rep["new_value"],
                is_diff=bool(rep.get("old_value")),
                snapshot={"entity_id": eid, "before": before_state[eid]},
            )
        )

    # Overrides: disable the fact each change replaces (typically a read-only
    # handbook entity) and record a `supersedes` edge, so removing or expiring the
    # override auto-restores what it replaced (see cleanup.restore_superseded).
    for c in changes:
        target_id = c.get("supersedes")
        new_id = c["entity_id"]
        if not target_id or new_id not in touched:
            continue
        target = db.get(models.KbEntity, target_id)
        if target is None:
            continue
        if target.enabled:
            db.add(
                models.ChangelogEntry(
                    actor=actor,
                    actor_user_id=actor_user_id,
                    action=f"Disabled {target.name} (replaced by {touched[new_id].name})",
                    entity_id=target.id,
                    is_diff=False,
                    snapshot={"entity_id": target_id, "before": _entity_state(target)},
                )
            )
            target.enabled = False
        exists = db.scalar(
            select(models.KbRelationship).where(
                models.KbRelationship.rel == "supersedes",
                models.KbRelationship.src_id == new_id,
                models.KbRelationship.dst_id == target_id,
            )
        )
        if exists is None:
            db.add(models.KbRelationship(rel="supersedes", src_id=new_id, dst_id=target_id))

    if touched:  # re-embed changed entities so retrieval stays fresh
        entities = list(touched.values())
        vecs = embed_texts([entity_text(e) for e in entities])
        for e, v in zip(entities, vecs):
            e.embedding = v

    db.commit()
    return {"applied": list(touched.keys())}
