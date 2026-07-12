"""Hybrid retrieval over the knowledge graph: semantic (pgvector) + lexical
(word overlap) + structural (1-hop relationship expansion). These functions are
what the LangGraph agent will call as tools (search_graph / get_entity /
expand_neighbors); `retrieve_subgraph` assembles the minimal relevant subgraph.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.embeddings import embed_query, tokens

# Hybrid weights: semantic recall + lexical precision on named entities.
W_SEMANTIC = 0.65
W_LEXICAL = 0.35

# Common words that would otherwise create false lexical matches (e.g. "do you
# have a swimming pool" matching a policy body just because it contains "have").
STOPWORDS = {
    "the", "a", "an", "is", "are", "am", "be", "been", "do", "does", "did", "you",
    "your", "yours", "i", "my", "we", "our", "it", "its", "he", "she", "they", "them",
    "have", "has", "had", "can", "could", "will", "would", "should", "of", "to", "on",
    "in", "for", "and", "or", "at", "by", "with", "from", "this", "that", "these",
    "those", "what", "when", "where", "how", "why", "who", "which", "if", "so", "as",
    "get", "got", "there", "here", "about", "any", "some", "me", "us",
}


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


def _stem(t: str) -> str:
    # Very light singularization so tour/tours, morning/mornings match.
    return t[:-1] if len(t) > 3 and t.endswith("s") else t


def _lexical_score(query_tokens: set[str], e: models.KbEntity) -> float:
    meaningful = {_stem(t) for t in (query_tokens - STOPWORDS)}
    if not meaningful:
        return 0.0
    text = e.name + " " + " ".join(str(v) for v in (e.attributes or {}).values())
    entity_tokens = {_stem(t) for t in tokens(text)}
    hits = sum(1 for q in meaningful if q in entity_tokens)
    return hits / len(meaningful)


def search_graph(db: Session, query: str, k: int = 5) -> list[dict]:
    """Rank entities by a hybrid of semantic similarity and lexical overlap."""
    qvec = embed_query(query)
    qtokens = set(tokens(query))
    dist = models.KbEntity.embedding.cosine_distance(qvec)
    rows = db.execute(
        select(models.KbEntity, dist.label("dist"))
        .where(models.KbEntity.embedding.is_not(None))
        .order_by(dist)
        .limit(max(k * 3, 10))
    ).all()

    scored = []
    for e, d in rows:
        semantic = 1.0 - float(d)  # cosine distance -> similarity
        lexical = _lexical_score(qtokens, e)
        score = W_SEMANTIC * semantic + W_LEXICAL * lexical
        scored.append((score, semantic, lexical, e))
    scored.sort(key=lambda r: r[0], reverse=True)

    out = []
    for score, semantic, lexical, e in scored[:k]:
        s = _summary(e)
        s["score"] = round(score, 4)
        s["semantic"] = round(semantic, 4)
        s["lexical"] = round(lexical, 4)
        out.append(s)
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


def retrieve_subgraph(db: Session, query: str, k: int = 4, expand: bool = True) -> dict:
    """Top-k hits plus 1-hop neighbors of the strongest hits — the minimal
    relevant subgraph handed to the agent's context."""
    hits = search_graph(db, query, k)
    subgraph: dict[str, dict] = {h["id"]: h for h in hits}
    if expand:
        for h in hits[:3]:
            for n in expand_neighbors(db, h["id"]):
                subgraph.setdefault(n["id"], n)
    return {"query": query, "hits": hits, "entities": list(subgraph.values())}
