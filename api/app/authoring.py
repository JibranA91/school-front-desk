"""Operator chat-to-author agent.

`propose`: the LLM (Sonnet) turns a plain-language instruction into precise graph
operations against the current entities; code then looks up the real current
value and deterministically flags conflicts (an update that overwrites a
differing existing value). `apply`: write the confirmed changes to the graph,
re-embed, and append changelog entries.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import models
from app.config import settings


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

    class Proposal(BaseModel):
        summary: str = Field(description="Short label for this change, e.g. 'Weekday opening time'.")
        operations: list[Operation]

    system = (
        "You maintain a childcare center's knowledge graph. Given the operator's plain-language "
        "instruction and the current entities, output the MINIMAL set of operations to apply.\n"
        "- To change an existing fact, use action='update' with that entity's exact id and the "
        "attribute field to change.\n"
        "- For genuinely new information not covered by any entity, use action='add' with a new "
        "kebab-case id and an appropriate type.\n"
        "- new_value is always a string. Be precise; do not invent unrelated changes.\n\n"
        f"CURRENT ENTITIES:\n{_serialize_graph(db)}"
    )
    model = get_chat_model(settings.bedrock_chat_model).with_structured_output(Proposal)
    proposal = model.invoke([("system", system), ("human", instruction)])

    changes: list[dict] = []
    has_conflict = False
    for op in proposal.operations:
        e = db.get(models.KbEntity, op.entity_id)
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
                "is_conflict": is_conflict,
                "source": (e.sources[0] if e and e.sources else None) if e else None,
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
    for c in changes:
        if c.get("is_conflict") and not accept_conflicts:
            continue
        e = db.get(models.KbEntity, c["entity_id"])
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
            )
        )

    if touched:  # re-embed changed entities so retrieval stays fresh
        entities = list(touched.values())
        vecs = embed_texts([entity_text(e) for e in entities])
        for e, v in zip(entities, vecs):
            e.embedding = v

    db.commit()
    return {"applied": list(touched.keys())}
