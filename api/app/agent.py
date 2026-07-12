"""Parent front-desk agent.

Two paths behind one interface (`answer_question`):
- **Bedrock (LangGraph):** a real tool-calling ReAct agent over the retrieval
  tools, using Claude on Bedrock via langchain-aws. Runs when AWS creds exist.
- **Mock (default):** deterministic retrieve-then-format grounding so the whole
  loop — answers, citations, escalation, the learning loop — runs and is
  testable without any AWS creds.

Both paths pass through the deterministic escalation layer (`escalation.decide`).
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import escalation, models, retrieval
from app.config import settings

FALLBACK_PHONE_MSG = (
    "That's a great question — I want to be sure I give you the right answer, "
    "so I've passed it to our staff. Someone from Sunnyside will follow up with "
    "you shortly."
)


def group_key(text: str) -> str:
    """Normalize a question so near-duplicate gaps group in the operator inbox."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(words[:8])


_GREETING_WORDS = {"hi", "hello", "hey", "yo", "hiya", "howdy", "greetings", "hullo", "heya"}


def _social_reply(text: str) -> str | None:
    """A friendly reply for greetings / thanks / goodbyes — so small talk isn't
    treated as an unanswerable center question. None → route to the knowledge agent."""
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return "Hi! I'm Sunny, the Sunnyside front desk. What can I help you with?"
    if len(words) > 5:  # long enough to carry a real question — let the agent handle it
        return None
    joined = " ".join(words)
    if "thank" in joined or joined in {"thanks", "thx", "ty", "cheers"}:
        return "You're very welcome! Is there anything else I can help you with?"
    if "bye" in words or "goodbye" in words or "see you" in joined or "good night" in joined:
        return "Take care! You can reach the front desk anytime you have a question."
    is_greeting = (
        words[0] in _GREETING_WORDS
        or any(p in joined for p in ("good morning", "good afternoon", "good evening"))
        or "how are you" in joined
    )
    if is_greeting:
        return (
            "Hi! I'm Sunny, the Sunnyside front desk. I can help with hours, tuition, "
            "meals, our illness policy, tours, and more — what would you like to know?"
        )
    return None


def todays_menu(db: Session) -> list[str] | None:
    row = db.scalar(select(models.MenuDay).where(models.MenuDay.day == date.today()))
    if row is None:  # fall back to the most recent day so the demo isn't date-fragile
        row = db.scalar(select(models.MenuDay).order_by(models.MenuDay.day.desc()))
    return list(row.items) if row and row.items else None


def _format_from_entity(e: dict) -> tuple[str, str, str]:
    """Return (answer, citation_label, source_text) for a retrieved entity dict."""
    attrs = e.get("attributes") or {}
    citation = f"per {e['name']}"
    sources = e.get("sources") or []
    source_text = sources[0] if sources else e.get("snippet") or e["name"]

    body = attrs.get("body")
    if isinstance(body, str) and body:
        return body, citation, source_text
    if e["type"] == "Tuition":
        includes = attrs.get("includes")
        extra = f" It includes {includes}." if includes else ""
        return (
            f"{attrs.get('program', '')} tuition is ${attrs.get('monthly')} per month.{extra}".strip(),
            citation,
            source_text,
        )
    if e["type"] == "Hours":
        return (
            f"We're open {attrs.get('days')}, {attrs.get('open')}–{attrs.get('close')}.",
            citation,
            source_text,
        )
    # Generic fallback: stitch scalar attributes.
    facts = ", ".join(f"{k}: {v}" for k, v in attrs.items() if isinstance(v, (str, int, float)))
    return (f"{e['name']} — {facts}", citation, source_text)


def _mock_answer(db: Session, question: str) -> dict:
    """Deterministic grounded answer (no LLM)."""
    sub = retrieval.retrieve_subgraph(db, question, k=4)
    hits = sub["hits"]
    top = hits[0] if hits else None

    # Mock semantic scores are hash-noise, so gate a confident answer on real
    # *lexical* overlap (a query term actually appears in the entity). Without it,
    # off-book questions ("swimming pool?") would get a false-confident answer.
    confidence = 0.0
    citations: list[str] = []
    answer, citation, source = ("", None, None)
    if top and top["lexical"] > 0:
        confidence = round(min(1.0, 0.6 + 0.4 * top["lexical"]), 3)
        citations = [top["id"]]
        answer, citation, source = _format_from_entity(top)
    elif top:
        # Weak match only — stays below threshold, routes to a graceful gap.
        confidence = round(top["semantic"] * 0.3, 3)

    return {
        "answer": answer,
        "citation": citation,
        "source": source,
        "citations": citations,
        "confidence": round(confidence, 3),
    }


def _bedrock_answer(db: Session, question: str) -> dict:
    """Real tool-calling agent over the graph (Claude on Bedrock via LangGraph)."""
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent
    from pydantic import BaseModel, Field

    from app.llm import get_chat_model

    @tool
    def search_graph(query: str) -> list[dict]:
        """Search the center's knowledge graph for entities relevant to a query."""
        return retrieval.search_graph(db, query, k=5)

    @tool
    def get_entity(entity_id: str) -> dict | None:
        """Fetch a single knowledge-graph entity by its id."""
        return retrieval.get_entity(db, entity_id)

    @tool
    def expand_neighbors(entity_id: str) -> list[dict]:
        """Get entities directly related (1 hop) to the given entity."""
        return retrieval.expand_neighbors(db, entity_id)

    class Answer(BaseModel):
        answer: str = Field(description="The grounded answer for the parent, or empty if unknown.")
        confidence: float = Field(description="0..1 confidence the answer is correct and grounded.")
        citations: list[str] = Field(description="Entity ids the answer is grounded in.")

    cfg = db.get(models.CenterConfig, 1)
    center = cfg.name if cfg else "the center"
    system = (
        f"You are Sunny, the AI front desk for {center}. Answer parents' questions "
        "ONLY from the knowledge graph retrieved via your tools. Always ground answers "
        "in retrieved entities and list the entity ids you used in `citations`. Be warm, "
        "concise, and specific to the center. If the graph does not contain the answer, "
        "return an empty answer with confidence 0 and no citations — never guess."
    )
    agent = create_react_agent(
        get_chat_model(),
        tools=[search_graph, get_entity, expand_neighbors],
        prompt=system,
        response_format=Answer,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    structured: Answer = result["structured_response"]

    # Validate citations against the graph (drop hallucinated ids).
    valid = [cid for cid in structured.citations if retrieval.get_entity(db, cid)]
    citation_label = None
    source = None
    if valid:
        top = retrieval.get_entity(db, valid[0])
        if top:
            citation_label = f"per {top['name']}"
            srcs = top.get("sources") or []
            source = srcs[0] if srcs else top.get("snippet")
    return {
        "answer": structured.answer,
        "citation": citation_label,
        "source": source,
        "citations": valid,
        "confidence": float(structured.confidence),
    }


def answer_question(db: Session, question: str) -> dict:
    """Full pipeline: answer (real or mock) → deterministic escalation → response.

    Returns a shape the frontend can render directly (see the message `kind`s).
    """
    # Small talk short-circuits before the knowledge pipeline — no escalation,
    # no inbox gap ("log": False).
    social = _social_reply(question)
    if social is not None:
        return {
            "kind": "assistant-text",
            "answer": social,
            "citation": None,
            "source": None,
            "menu": None,
            "citations": [],
            "confidence": 1.0,
            "category": "social",
            "needs_escalation": False,
            "status": "answered",
            "group_key": group_key(question),
            "log": False,
        }

    raw = _bedrock_answer(db, question) if settings.bedrock_enabled else _mock_answer(db, question)
    decision = escalation.decide(question, raw["confidence"], raw["citations"])

    base = {
        "confidence": raw["confidence"],
        "category": decision.category,
        "needs_escalation": decision.needs_escalation,
        "status": decision.status,
        "citations": raw["citations"],
        "group_key": group_key(question),
    }

    # Sensitive → warm hand-off card, with related grounded guidance if we have it.
    if decision.needs_escalation and decision.category is not None:
        related = ""
        if decision.category in {"health", "allergy", "medication"}:
            pol = retrieval.get_entity(db, "policy-illness")
            if pol and (pol.get("attributes") or {}).get("body"):
                related = " While you wait: " + pol["attributes"]["body"]
        return {
            **base,
            "kind": "escalation",
            "answer": (
                "I want to make sure you get the right guidance on this — I've flagged "
                "it for our staff, who'll reach out shortly." + related
            ),
            "citation": None,
            "source": None,
            "menu": None,
        }

    # Knowledge gap / low confidence → graceful hand-off (no guessing).
    if decision.needs_escalation:
        return {
            **base,
            "kind": "assistant-text",
            "answer": FALLBACK_PHONE_MSG,
            "citation": None,
            "source": None,
            "menu": None,
        }

    # Answerable. Live-data (menu) gets its own card.
    top_id = raw["citations"][0] if raw["citations"] else None
    if top_id == "meals" or any(w in question.lower() for w in ["lunch", "menu", "today's food"]):
        menu = todays_menu(db)
        if menu:
            return {
                **base,
                "kind": "lunch",
                "answer": "Yes — a fresh lunch is served every day and it's included in "
                "tuition. Here's what's on today's tray:",
                "menu": menu,
                "citation": "per Today’s Menu",
                "source": "Today's Menu · synced from the kitchen this morning.",
            }

    return {
        **base,
        "kind": "confident",
        "answer": raw["answer"],
        "citation": raw["citation"],
        "source": raw["source"],
        "menu": None,
    }
