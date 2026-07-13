"""Recompute and store embeddings for every knowledge-base entity using the
currently-configured embedder (Bedrock Titan in bedrock mode, otherwise the
offline mock). Run this after switching LLM provider / embedder so the stored
document vectors match the query vectors — mixing embedders in one vector space
makes semantic search meaningless.

    uv run python -m app.reembed          # inside the api container
    ../.venv/Scripts/python -m app.reembed  # from ./api on the host

No-op-safe to re-run. Does nothing useful in FTS-only mode (EMBEDDINGS_ENABLED
=false) — retrieval ignores vectors there — but stays harmless if run.
"""

from __future__ import annotations

from app import models
from app.config import settings
from app.db import SessionLocal
from app.embeddings import embed_texts, entity_text


def reembed(batch_size: int = 64) -> int:
    """Re-embed all entities in batches. Returns the number re-embedded."""
    db = SessionLocal()
    try:
        entities = db.query(models.KbEntity).all()
        for i in range(0, len(entities), batch_size):
            batch = entities[i : i + batch_size]
            vecs = embed_texts([entity_text(e) for e in batch])
            for e, v in zip(batch, vecs):
                e.embedding = v
            db.commit()
        return len(entities)
    finally:
        db.close()


if __name__ == "__main__":
    embedder = "Bedrock Titan" if settings.bedrock_enabled else "mock (offline)"
    if not settings.embeddings_enabled:
        print(
            "Note: EMBEDDINGS_ENABLED=false — retrieval is FTS-only and ignores "
            "vectors. Re-embedding anyway so they're ready if you turn it back on."
        )
    n = reembed()
    print(f"Re-embedded {n} entities using the {embedder} embedder.")
