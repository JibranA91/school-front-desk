"""Ingest a family-handbook PDF into the knowledge graph.

A real center's source of truth is usually a long PDF handbook, not a tidy set
of facts. This turns that PDF into the same typed graph the operator edits by
hand: parse -> page-grouped chunks -> an extraction agent pulls the distinct,
parent-relevant policy facts out of each chunk -> each becomes a new `hb-` typed
entity with a page-cited source, an embedding, and a changelog entry.

Design choices:
- Ingested nodes get an `hb-` id prefix and never overwrite existing entities,
  so the curated demo center stays intact ("uploading your handbook" adds a
  fresh collection rather than merging).
- Bedrock present  -> Sonnet reads each chunk and writes clean, quotable facts.
  Mock (no creds)  -> a deterministic heuristic splits sections into entities so
  the pipeline still runs and is demoable offline.

Run against the bundled handbook (DB up):
    uv run python -m app.ingest
Or a specific file:
    uv run python -m app.ingest /path/to/handbook.pdf --label "Family Handbook 2024"
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import settings

# Entity types the extractor may assign. Superset of the seed vocabulary plus a
# few common handbook sections; keeps the graph's type facets coherent.
ENTITY_TYPES = (
    "Hours",
    "Tuition",
    "Enrollment",
    "Health",
    "Meal",
    "Attendance",
    "Safety",
    "Behavior",
    "Communication",
    "Supplies",
    "Curriculum",
    "Policy",
    "Program",
    "Holiday",
    "General",
)

PAGES_PER_CHUNK = 3  # ~6-7k chars/chunk: enough context, small enough to extract well
DEFAULT_HANDBOOK = (
    Path(__file__).resolve().parents[2]
    / ".plans"
    / "2019-division-of-child-and-family-development-family-handbook-final.pdf"
)

_SMART = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "�": " ",
}


@dataclass
class Chunk:
    text: str
    page_start: int  # 1-indexed, human-friendly
    page_end: int


@dataclass
class Extracted:
    type: str
    name: str
    body: str
    page: int
    keywords: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# PDF -> text -> chunks
# --------------------------------------------------------------------------- #
def _clean(text: str) -> str:
    for bad, good in _SMART.items():
        text = text.replace(bad, good)
    # Drop private-use glyphs (wingding bullets etc.) and control chars.
    text = "".join(
        ch if (ch in "\n\t" or (ord(ch) >= 32 and not 0xE000 <= ord(ch) <= 0xF8FF)) else " "
        for ch in text
    )
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [_clean(p.extract_text() or "") for p in reader.pages]


def chunk_pages(pages: list[str], size: int = PAGES_PER_CHUNK) -> list[Chunk]:
    chunks: list[Chunk] = []
    for start in range(0, len(pages), size):
        group = pages[start : start + size]
        text = "\n\n".join(group).strip()
        if len(text) < 40:  # skip near-empty (cover pages, blanks)
            continue
        chunks.append(Chunk(text=text, page_start=start + 1, page_end=start + len(group)))
    return chunks


# --------------------------------------------------------------------------- #
# Extraction — Bedrock (Sonnet) with a deterministic heuristic fallback
# --------------------------------------------------------------------------- #
_EXTRACT_SYSTEM = (
    "You are building a searchable knowledge base for a childcare center's front "
    "desk from its family handbook, so staff and an AI assistant can answer parent "
    "questions accurately.\n\n"
    "From the handbook excerpt, extract the distinct, PARENT-RELEVANT facts as "
    "entities. Good topics: hours & schedules, tuition/fees/payment, "
    "enrollment/registration/withdrawal, health & illness/exclusion, "
    "immunizations/medication, attendance & absences, arrival/pickup/late policy, "
    "meals & nutrition, safety & emergencies, behavior/guidance/discipline, "
    "clothing & supplies, communication, and holidays/closures.\n\n"
    "Rules:\n"
    "- Each entity: a concise `name` (the topic), a `type` from the allowed set, and "
    "a `body` of 1-4 sentences stating the fact plainly enough to answer a parent "
    "directly. Prefer specifics (times, dollar amounts, day counts, temperatures).\n"
    "- Split unrelated facts into separate entities; do not merge a whole page into one.\n"
    "- SKIP boilerplate: welcome letters, mission/philosophy prose, staff bios, lists "
    "of other centers' addresses/phones, the table of contents, and accreditation "
    "filler. If the excerpt has no parent-relevant facts, return an empty list.\n"
    f"- `type` must be one of: {', '.join(ENTITY_TYPES)}."
)


def _extract_bedrock(chunk: Chunk) -> list[Extracted]:
    from pydantic import BaseModel, Field

    from app.llm import get_chat_model

    class Entity(BaseModel):
        type: Literal[ENTITY_TYPES] = Field(description="Entity type from the allowed set.")  # type: ignore[valid-type]
        name: str = Field(description="Concise topic title, e.g. 'Illness Exclusion Policy'.")
        body: str = Field(description="1-4 sentence factual answer a front desk could quote.")
        keywords: list[str] = Field(default_factory=list, description="Optional search aliases.")

    class Extraction(BaseModel):
        # Default to empty: when a chunk has no parent-relevant facts the model
        # returns `{}`, which must validate rather than raise.
        entities: list[Entity] = Field(default_factory=list)

    # Dense policy pages produce many entities; 1024 tokens truncates the tool
    # call and yields an empty result, so give extraction a larger budget.
    model = get_chat_model(settings.bedrock_chat_model, max_tokens=4096).with_structured_output(
        Extraction
    )
    human = f"Handbook excerpt (pages {chunk.page_start}-{chunk.page_end}):\n\n{chunk.text}"
    result = model.invoke([("system", _EXTRACT_SYSTEM), ("human", human)])
    return [
        Extracted(
            type=e.type,
            name=e.name.strip(),
            body=e.body.strip(),
            page=chunk.page_start,
            keywords=[k.strip() for k in (e.keywords or []) if k.strip()],
        )
        for e in result.entities
        if e.name.strip() and e.body.strip()
    ]


# Keyword -> type hints for the offline heuristic path.
_TYPE_HINTS = [
    ("Hours", ("hours of operation", "open ", "opening", "closing", "drop off", "pick up", "pick-up")),
    ("Tuition", ("tuition", "fee", "payment", "co-pay", "sliding fee", "cost")),
    ("Enrollment", ("enroll", "registration", "waitlist", "withdraw", "eligibility", "application")),
    ("Health", ("illness", "sick", "fever", "immuniz", "medication", "medical", "allergy", "health")),
    ("Attendance", ("attendance", "absence", "absent", "late", "tardy")),
    ("Meal", ("meal", "lunch", "breakfast", "snack", "nutrition", "food")),
    ("Safety", ("safety", "emergency", "evacuation", "security", "lockdown")),
    ("Behavior", ("behavior", "discipline", "guidance", "biting", "conduct")),
    ("Supplies", ("clothing", "supplies", "bring", "diaper", "nap", "belongings")),
    ("Holiday", ("holiday", "closure", "closed", "calendar")),
    ("Communication", ("communication", "conference", "newsletter", "contact")),
]

_HEADING_RE = re.compile(r"^(?:\d+\.\s*)?([A-Z][A-Za-z][A-Za-z &/'\-]{3,48})\s*$")


def _guess_type(text: str) -> str:
    low = text.lower()
    for etype, needles in _TYPE_HINTS:
        if any(n in low for n in needles):
            return etype
    return "General"


def _extract_heuristic(chunk: Chunk) -> list[Extracted]:
    """Offline fallback: split the chunk on heading-like lines and make one
    entity per section. Bodies are the raw text (trimmed), typed by keyword."""
    lines = chunk.text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_title = None
    buf: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _HEADING_RE.match(stripped) and len(stripped.split()) <= 7:
            if current_title and buf:
                sections.append((current_title, buf))
            current_title, buf = stripped.rstrip(":").title(), []
        elif stripped:
            buf.append(stripped)
    if current_title and buf:
        sections.append((current_title, buf))

    out: list[Extracted] = []
    for title, body_lines in sections:
        body = " ".join(body_lines).strip()
        if len(body) < 60:  # too thin to be a useful fact
            continue
        out.append(
            Extracted(
                type=_guess_type(title + " " + body),
                name=title,
                body=body[:600] + ("..." if len(body) > 600 else ""),
                page=chunk.page_start,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Dedup + persist
# --------------------------------------------------------------------------- #
def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "topic"


def _dedup(items: list[Extracted]) -> list[Extracted]:
    """Collapse near-duplicate topics (same slug), keeping the longest body."""
    best: dict[str, Extracted] = {}
    for it in items:
        key = _slug(it.name)
        cur = best.get(key)
        if cur is None or len(it.body) > len(cur.body):
            if cur is not None:
                it.page = min(it.page, cur.page)
            best[key] = it
    return list(best.values())


def link_similar(
    db: Session,
    k: int = 3,
    max_dist: float = 0.45,
    rel: str = "related",
) -> int:
    """Connect entities by embedding similarity so the graph is navigable.

    For each entity we add edges to its `k` nearest neighbours within `max_dist`
    cosine distance (and always at least its single nearest, so nothing is
    orphaned). Edges are undirected and deduped. Only rebuilds the `rel`
    ("related") edges — hand-authored typed edges (servedBy, …) are untouched.
    Uses pgvector's `<=>` operator in one lateral query rather than pulling
    vectors into Python.
    """
    from sqlalchemy import bindparam, delete, text

    from app import models as _m

    db.execute(delete(_m.KbRelationship).where(_m.KbRelationship.rel == rel))

    # k nearest neighbours per node within the distance threshold.
    knn = db.execute(
        text(
            """
            SELECT a.id AS src, nn.id AS dst
            FROM kb_entities a
            CROSS JOIN LATERAL (
                SELECT b.id, a.embedding <=> b.embedding AS dist
                FROM kb_entities b
                WHERE b.id <> a.id AND b.embedding IS NOT NULL
                ORDER BY a.embedding <=> b.embedding
                LIMIT :k
            ) nn
            WHERE a.embedding IS NOT NULL AND nn.dist <= :max_dist
            """
        ).bindparams(bindparam("k", k), bindparam("max_dist", max_dist))
    ).all()

    pairs: set[tuple[str, str]] = set()
    linked: set[str] = set()
    for src, dst in knn:
        pairs.add((src, dst) if src < dst else (dst, src))
        linked.add(src)

    # Orphan rescue: any node with no edge above threshold gets its single
    # nearest neighbour, so the graph has no isolated dots.
    orphans = db.execute(
        text(
            """
            SELECT a.id AS src, nn.id AS dst
            FROM kb_entities a
            CROSS JOIN LATERAL (
                SELECT b.id
                FROM kb_entities b
                WHERE b.id <> a.id AND b.embedding IS NOT NULL
                ORDER BY a.embedding <=> b.embedding
                LIMIT 1
            ) nn
            WHERE a.embedding IS NOT NULL
            """
        )
    ).all()
    for src, dst in orphans:
        if src not in linked:
            pairs.add((src, dst) if src < dst else (dst, src))

    for src, dst in pairs:
        db.add(models.KbRelationship(rel=rel, src_id=src, dst_id=dst))
    db.commit()
    return len(pairs)


def clear_ingested(db: Session, id_prefix: str = "hb-") -> int:
    """Remove a previous handbook import, scoped strictly to the `id_prefix`
    collection. Never touches curated/operator data. Makes re-importing
    idempotent rather than piling up suffixed duplicates.

    Order matters: relationship edges and changelog rows reference kb_entities
    (FKs), so they must be cleared/unlinked before the entities are deleted."""
    from sqlalchemy import delete, or_, update

    like = f"{id_prefix}%"
    # 1) Relationship edges touching an ingested entity (e.g. the semantic
    #    "related" links) — otherwise the entity delete hits a FK violation.
    db.execute(
        delete(models.KbRelationship).where(
            or_(
                models.KbRelationship.src_id.like(like),
                models.KbRelationship.dst_id.like(like),
            )
        )
    )
    # 2) Import-noise changelog rows for this collection.
    db.execute(
        delete(models.ChangelogEntry).where(models.ChangelogEntry.reason == "handbook ingest")
    )
    # 3) Any other changelog rows referencing these entities: keep the audit
    #    line but unlink the entity so the FK doesn't block the delete.
    db.execute(
        update(models.ChangelogEntry)
        .where(models.ChangelogEntry.entity_id.like(like))
        .values(entity_id=None)
    )
    # 4) The entities themselves.
    n = db.execute(
        delete(models.KbEntity).where(models.KbEntity.id.like(like))
    ).rowcount
    db.commit()
    return n or 0


def ingest_pdf(
    db: Session,
    path: Path,
    source_label: str,
    actor: str = "Handbook Import",
    max_pages: int | None = None,
    id_prefix: str = "hb-",
) -> dict:
    """Parse `path`, extract entities, and write them as new graph nodes.

    Returns a report dict. Existing entities are never modified: ids collide only
    within this import, and we suffix to keep them distinct.
    """
    from app.embeddings import embed_texts, entity_text

    pages = pdf_pages(path)
    if max_pages:
        pages = pages[:max_pages]
    chunks = chunk_pages(pages)

    extract = _extract_bedrock if settings.bedrock_enabled else _extract_heuristic
    raw: list[Extracted] = []
    for ch in chunks:
        try:
            raw.extend(extract(ch))
        except Exception as exc:  # noqa: BLE001 — one bad chunk shouldn't sink the run
            print(f"  ! chunk pp.{ch.page_start}-{ch.page_end} failed: {exc}")
    items = _dedup(raw)

    # Reserve ids: avoid colliding with anything already in the graph.
    existing = set(db.scalars(select(models.KbEntity.id)).all())
    created: list[models.KbEntity] = []
    used: set[str] = set(existing)
    for it in items:
        base = f"{id_prefix}{_slug(it.name)}"
        eid, n = base, 2
        while eid in used:
            eid, n = f"{base}-{n}", n + 1
        used.add(eid)
        attrs = {"body": it.body, "source": "handbook"}
        if it.keywords:
            attrs["keywords"] = ", ".join(it.keywords)
        e = models.KbEntity(
            id=eid,
            type=it.type if it.type in ENTITY_TYPES else "General",
            name=it.name,
            attributes=attrs,
            sources=[f"{source_label} p.{it.page}"],
        )
        db.add(e)
        created.append(e)

    if created:
        db.flush()
        vecs = embed_texts([entity_text(e) for e in created])
        for e, v in zip(created, vecs):
            e.embedding = v
        for e in created:
            db.add(
                models.ChangelogEntry(
                    actor=actor,
                    action=f"Imported '{e.name}' from {source_label}",
                    entity_id=e.id,
                    after=(e.attributes.get("body") or "")[:200],
                    is_diff=False,
                    reason="handbook ingest",
                )
            )
        db.add(
            models.ChangelogEntry(
                actor=actor,
                action=f"Ingested {source_label}: {len(created)} entities from {len(chunks)} sections",
                is_diff=False,
                reason="handbook ingest",
            )
        )
        db.commit()

    # Rebuild similarity edges so the new entities are connected in the graph.
    edges = link_similar(db)

    by_type: dict[str, int] = {}
    for e in created:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    return {
        "source": source_label,
        "mode": "bedrock" if settings.bedrock_enabled else "heuristic",
        "pages": len(pages),
        "chunks": len(chunks),
        "created": len(created),
        "edges": edges,
        "by_type": by_type,
        "entity_ids": [e.id for e in created],
    }


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Ingest a handbook PDF into the knowledge graph.")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_HANDBOOK), help="Path to the PDF.")
    parser.add_argument("--label", default=None, help="Source label used in citations.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages (for quick tests).")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    label = args.label or "Family Handbook (DCFD, Rev. Apr 2019)"

    db = SessionLocal()
    try:
        report = ingest_pdf(db, path, source_label=label, max_pages=args.max_pages)
    finally:
        db.close()

    print(f"\nIngest complete [{report['mode']}] — {report['source']}")
    print(f"  {report['pages']} pages -> {report['chunks']} sections -> {report['created']} entities")
    for etype, n in sorted(report["by_type"].items(), key=lambda kv: -kv[1]):
        print(f"    {etype:<14} {n}")


if __name__ == "__main__":
    main()
