"""The knowledge-base READ contract.

The agent (and API) depend only on this interface — never on how the graph is
stored. Any backend (Postgres + pgvector, a managed vector DB, a graph DB, a
hosted search API, …) implements `Retriever` and is selected by config
(`settings.retriever`) via `get_retriever()`. Swapping the store is a one-line
config change; the agent contract does not move.

Every method returns entities in the same `EntitySummary` shape so downstream
code (grounding, citation validation, response shaping) is storage-agnostic.
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class EntitySummary(TypedDict, total=False):
    id: str                 # stable id used for citations
    type: str               # e.g. Tuition, Hours, Policy, Meal, …
    name: str
    attributes: dict        # includes a human-readable `body` where present
    sources: list           # provenance strings
    snippet: str | None
    # Present only on ranked search results:
    score: float
    semantic: float
    lexical: float


@runtime_checkable
class Retriever(Protocol):
    """Read side of the knowledge base. Implementations manage their own
    connection — no session/handle is passed in."""

    def search(self, query: str, k: int = 5) -> list[EntitySummary]:
        """Ranked entities relevant to `query` (hybrid semantic + lexical)."""
        ...

    def get_entity(self, entity_id: str) -> EntitySummary | None:
        """A single entity by id, or None if it doesn't exist."""
        ...

    def expand_neighbors(self, entity_id: str, rel: str | None = None) -> list[EntitySummary]:
        """Entities one relationship hop from `entity_id` (optionally by rel type)."""
        ...

    def retrieve_subgraph(self, query: str, k: int = 4, expand: bool = True) -> dict:
        """Top-k hits plus 1-hop neighbors — the minimal relevant subgraph.
        Returns {"query", "hits": [EntitySummary], "entities": [EntitySummary]}."""
        ...
