"""Rebuild the knowledge graph's semantic "related" edges from the CURRENT stored
entity embeddings.

Those edges (built by ingest.link_similar) are derived FROM the embeddings, so a
bulk re-embed — e.g. switching embedder/provider, Titan -> Voyage — leaves them
pointing at neighbours in the OLD vector space. `reembed` updates the entity
vectors but not the edges; run this right after it to bring the graph back into
the new space:

    uv run python -m app.reembed && uv run python -m app.relink   # in the api container
    ../.venv/Scripts/python -m app.relink                          # from ./api on the host

Only the auto-generated "related" edges are rebuilt — hand-authored typed edges
(servedBy, subjectTo, observes) are left intact. It reads whatever vectors are
stored, so it doesn't call the embedding provider itself. Safe to re-run. Normal
handbook ingestion already relinks newly-added entities, so this is only needed
after a bulk historical re-embed.
"""

from __future__ import annotations

from app.config import settings
from app.db import SessionLocal
from app.ingest import link_similar


def relink() -> int:
    """Rebuild the semantic 'related' edges from current embeddings. Returns the
    number of edges written."""
    db = SessionLocal()
    try:
        return link_similar(db)
    finally:
        db.close()


if __name__ == "__main__":
    if not settings.embeddings_enabled:
        print(
            "Note: EMBEDDINGS_ENABLED=false — retrieval is FTS-only and doesn't "
            "rank on graph edges; relinking anyway so they're ready if enabled."
        )
    n = relink()
    print(
        f"Relinked the knowledge graph: rebuilt {n} semantic 'related' edges from "
        f"the stored vectors (current embedder: {settings.embedder})."
    )
