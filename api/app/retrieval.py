"""Hybrid retrieval over the knowledge graph: semantic (pgvector) + lexical
(Postgres full-text search) + structural (1-hop relationship expansion). These
functions are what the LangGraph agent calls as tools (search_graph / get_entity
/ expand_neighbors); `retrieve_subgraph` assembles the minimal relevant subgraph.

The lexical signal is Postgres FTS: `to_tsvector`/`plainto_tsquery` +
`ts_rank_cd`. The `english` text-search config gives Snowball stemming
(tour/tours, morning/mornings) and stopword removal for free, so a query like
"do you have a swimming pool" reduces to `swimming & pool` and simply scores 0
against entities that don't mention them — no manual stopword list needed.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.db import SessionLocal
from app.embeddings import embed_query
from app.retrieval_base import EntitySummary, Retriever

# Hybrid weights: semantic recall + lexical precision on named entities.
W_SEMANTIC = 0.65
W_LEXICAL = 0.35

# Postgres text-search configuration (stemming + stopwords).
_TS_CONFIG = "english"


def _summary(e: models.KbEntity) -> dict:
    attrs = e.attributes or {}
    body = attrs.get("body")
    return {
        "id": e.id,
        "type": e.type,
        "name": e.name,
        "attributes": attrs,
        "sources": e.sources or [],
        "snippet": body[:220] if isinstance(body, str) else None,
    }


def _searchable(entity=models.KbEntity):
    """SQL text we run FTS over: entity name + all attribute values (the JSONB
    cast to text). Matches the breadth of what the old word-overlap scored."""
    return entity.name + func.cast(" ", Text) + func.coalesce(
        func.cast(entity.attributes, Text), ""
    )


def search_graph(db: Session, query: str, k: int = 5) -> list[dict]:
    """Rank entities by a hybrid of semantic similarity (pgvector cosine) and
    lexical relevance (Postgres FTS ts_rank_cd). Both signals are computed in
    one SQL pass; ts_rank_cd is min-max normalized across the result set so it
    blends sensibly with the 0..1 cosine similarity."""
    qvec = embed_query(query)
    semantic = (1.0 - models.KbEntity.embedding.cosine_distance(qvec)).label("sem")
    tsv = func.to_tsvector(_TS_CONFIG, _searchable())
    tsq = func.plainto_tsquery(_TS_CONFIG, query)
    lexical = func.ts_rank_cd(tsv, tsq).label("lex")

    rows = db.execute(
        select(models.KbEntity, semantic, lexical).where(
            models.KbEntity.embedding.is_not(None)
        )
    ).all()

    max_lex = max((float(r.lex) for r in rows), default=0.0) or 1.0
    scored = []
    for e, sem, lex in rows:
        s = float(sem)
        lx = float(lex) / max_lex  # normalize FTS rank to 0..1 within this set
        scored.append((W_SEMANTIC * s + W_LEXICAL * lx, s, lx, e))
    scored.sort(key=lambda r: r[0], reverse=True)

    out = []
    for score, sem, lx, e in scored[:k]:
        summary = _summary(e)
        summary["score"] = round(score, 4)
        summary["semantic"] = round(sem, 4)
        summary["lexical"] = round(lx, 4)
        out.append(summary)
    return out


def get_entity(db: Session, entity_id: str) -> dict | None:
    e = db.get(models.KbEntity, entity_id)
    return _summary(e) if e else None


def expand_neighbors(db: Session, entity_id: str, rel: str | None = None) -> list[dict]:
    q = select(models.KbRelationship).where(
        or_(
            models.KbRelationship.src_id == entity_id,
            models.KbRelationship.dst_id == entity_id,
        )
    )
    if rel:
        q = q.where(models.KbRelationship.rel == rel)

    neighbors = []
    for r in db.scalars(q).all():
        other_id = r.dst_id if r.src_id == entity_id else r.src_id
        e = db.get(models.KbEntity, other_id)
        if e:
            s = _summary(e)
            s["via"] = r.rel
            neighbors.append(s)
    return neighbors


def retrieve_subgraph(db: Session, query: str, k: int | None = None, expand: bool = True) -> dict:
    """Top-k hits plus their neighbors (BFS over `retrieval_hops` relationship
    hops from the top `retrieval_expand_top` hits) — the minimal relevant
    subgraph handed to the agent's context. Shape is config-driven; a
    max-entities cap guards against blow-up on a densely-linked graph."""
    k = k or settings.retrieval_k
    max_entities = settings.retrieval_max_entities
    hits = search_graph(db, query, k)
    subgraph: dict[str, dict] = {h["id"]: h for h in hits}

    if expand and settings.retrieval_hops > 0:
        frontier = [h["id"] for h in hits[: settings.retrieval_expand_top]]
        for _ in range(settings.retrieval_hops):
            if len(subgraph) >= max_entities:
                break
            next_frontier: list[str] = []
            for entity_id in frontier:
                for n in expand_neighbors(db, entity_id):
                    if n["id"] not in subgraph:
                        subgraph[n["id"]] = n
                        next_frontier.append(n["id"])
                        if len(subgraph) >= max_entities:
                            break
                if len(subgraph) >= max_entities:
                    break
            frontier = next_frontier
            if not frontier:
                break
    return {"query": query, "hits": hits, "entities": list(subgraph.values())}


# --------------------------------------------------------------------------- #
# Retriever implementation + factory (the swap seam)
# --------------------------------------------------------------------------- #


class PgVectorRetriever:
    """Default `Retriever`: Postgres + pgvector (semantic) + FTS (lexical) +
    kb_relationships (structural). Opens its own short-lived read session per
    call, so the interface stays connection-agnostic. Delegates to the module
    functions above."""

    def search(self, query: str, k: int = 5) -> list[EntitySummary]:
        with SessionLocal() as db:
            return search_graph(db, query, k)

    def get_entity(self, entity_id: str) -> EntitySummary | None:
        with SessionLocal() as db:
            return get_entity(db, entity_id)

    def expand_neighbors(self, entity_id: str, rel: str | None = None) -> list[EntitySummary]:
        with SessionLocal() as db:
            return expand_neighbors(db, entity_id, rel)

    def retrieve_subgraph(self, query: str, k: int | None = None, expand: bool = True) -> dict:
        with SessionLocal() as db:
            return retrieve_subgraph(db, query, k, expand)


_BACKENDS = {"pgvector": PgVectorRetriever}


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    """The configured knowledge-base retriever. Swap `settings.retriever` (or
    register another class in `_BACKENDS`) to change stores — nothing else moves."""
    backend = _BACKENDS.get(settings.retriever)
    if backend is None:
        raise ValueError(
            f"Unknown retriever {settings.retriever!r}; options: {sorted(_BACKENDS)}"
        )
    return backend()
