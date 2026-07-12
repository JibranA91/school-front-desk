"""Parent front-desk agent.

**Bedrock path (real):** every message goes through the LangGraph agent. The
model classifies intent (`greeting` / `answer` / `unknown`) and grounds answers
in the retrieval tools. Code enforces only the non-negotiable safety rules —
sensitive categories always escalate (checked before the model, deterministically)
and cited entity ids must exist.

**Mock path (no AWS creds):** can't use an LLM to classify intent, so it keeps a
keyword social short-circuit + retrieve-then-format grounding.

Both paths produce the same response shape (see the message `kind`s).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

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


def todays_menu(db: Session) -> list[str] | None:
    row = db.scalar(select(models.MenuDay).where(models.MenuDay.day == date.today()))
    if row is None:  # fall back to the most recent day so the demo isn't date-fragile
        row = db.scalar(select(models.MenuDay).order_by(models.MenuDay.day.desc()))
    return list(row.items) if row and row.items else None


# --------------------------------------------------------------------------- #
# Response shaping — one shape for both paths.
# --------------------------------------------------------------------------- #


def _base(question: str, *, status, category, needs_escalation, confidence, citations, log) -> dict:
    return {
        "status": status,
        "category": category,
        "needs_escalation": needs_escalation,
        "confidence": confidence,
        "citations": citations,
        "group_key": group_key(question),
        "log": log,
    }


def _greeting_response(question: str, text: str) -> dict:
    r = _base(question, status="answered", category="social", needs_escalation=False,
              confidence=1.0, citations=[], log=False)
    r.update(kind="assistant-text", answer=text, citation=None, source=None, menu=None)
    return r


def _gap_response(question: str) -> dict:
    r = _base(question, status="escalated", category=None, needs_escalation=True,
              confidence=0.0, citations=[], log=True)
    r.update(kind="assistant-text", answer=FALLBACK_PHONE_MSG, citation=None, source=None, menu=None)
    return r


def _sensitive_response(db: Session, question: str, category: str) -> dict:
    related = ""
    if category in {"health", "allergy", "medication"}:
        pol = retrieval.get_entity(db, "policy-illness")
        if pol and (pol.get("attributes") or {}).get("body"):
            related = " While you wait: " + pol["attributes"]["body"]
    r = _base(question, status="escalated", category=category, needs_escalation=True,
              confidence=1.0, citations=[], log=True)
    r.update(
        kind="escalation",
        answer=(
            "I want to make sure you get the right guidance on this — I've flagged it "
            "for our staff, who'll reach out shortly." + related
        ),
        citation=None,
        source=None,
        menu=None,
    )
    return r


def _answer_response(db, question, answer, citation, source, citations, confidence) -> dict:
    top_id = citations[0] if citations else None
    if top_id == "meals" or any(w in question.lower() for w in ["lunch", "menu", "today's food"]):
        menu = todays_menu(db)
        if menu:
            r = _base(question, status="answered", category=None, needs_escalation=False,
                      confidence=confidence, citations=citations, log=True)
            r.update(
                kind="lunch",
                answer="Yes — a fresh lunch is served every day and it's included in "
                "tuition. Here's what's on today's tray:",
                menu=menu,
                citation="per Today’s Menu",
                source="Today's Menu · synced from the kitchen this morning.",
            )
            return r
    r = _base(question, status="answered", category=None, needs_escalation=False,
              confidence=confidence, citations=citations, log=True)
    r.update(kind="confident", answer=answer, citation=citation, source=source, menu=None)
    return r


def _citation_details(db: Session, citations: list[str]) -> tuple[str | None, str | None]:
    if not citations:
        return None, None
    top = retrieval.get_entity(db, citations[0])
    if not top:
        return None, None
    srcs = top.get("sources") or []
    return f"per {top['name']}", (srcs[0] if srcs else top.get("snippet"))


# --------------------------------------------------------------------------- #
# Bedrock path — all messages through the LLM, model-classified intent.
# --------------------------------------------------------------------------- #


def _bedrock_answer(db: Session, question: str) -> dict:
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
        intent: Literal["greeting", "answer", "unknown"] = Field(
            description="greeting = small talk/thanks; answer = a center question you "
            "answered from the tools; unknown = a center question the graph can't answer."
        )
        answer: str = Field(description="Reply text: the grounded answer, a warm greeting, or empty if unknown.")
        confidence: float = Field(description="0..1 confidence the answer is correct and grounded.")
        citations: list[str] = Field(description="Entity ids the answer is grounded in (empty for greeting/unknown).")

    cfg = db.get(models.CenterConfig, 1)
    center = cfg.name if cfg else "the center"
    system = (
        f"You are Sunny, the AI front desk for {center}, chatting with a parent.\n"
        "- Greetings or small talk (hi, thanks, how are you): reply warmly and briefly, "
        "invite a question, DO NOT use tools. Set intent='greeting'.\n"
        "- A question about the center: use the tools to find the answer, ground it in "
        "retrieved entities, and list the entity ids you used in `citations`. Set "
        "intent='answer'. Be warm, concise, and specific.\n"
        "- A center question the graph does not cover: set intent='unknown', answer='', "
        "no citations. NEVER guess or use outside knowledge.\n"
        "Return the structured Answer."
    )
    agent = create_react_agent(
        get_chat_model(settings.bedrock_parent_model),
        tools=[search_graph, get_entity, expand_neighbors],
        prompt=system,
        response_format=Answer,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    s: Answer = result["structured_response"]
    valid = [cid for cid in s.citations if retrieval.get_entity(db, cid)]
    citation, source = _citation_details(db, valid)
    return {
        "intent": s.intent,
        "answer": s.answer,
        "confidence": float(s.confidence),
        "citations": valid,
        "citation": citation,
        "source": source,
    }


def _answer_bedrock(db: Session, question: str) -> dict:
    # Safety net first, deterministically — sensitive topics always escalate,
    # without depending on (or paying for) the model.
    sensitive = escalation.classify_sensitive(question)
    if sensitive is not None:
        return _sensitive_response(db, question, sensitive)

    raw = _bedrock_answer(db, question)
    if raw["intent"] == "greeting":
        return _greeting_response(question, raw["answer"] or "Hi! How can I help you today?")
    # Trust an 'answer' only if it actually cites a real entity.
    if raw["intent"] == "answer" and raw["citations"] and raw["answer"]:
        return _answer_response(
            db, question, raw["answer"], raw["citation"], raw["source"],
            raw["citations"], raw["confidence"],
        )
    return _gap_response(question)


# --------------------------------------------------------------------------- #
# Mock path — no LLM, so keyword social short-circuit + retrieval grounding.
# --------------------------------------------------------------------------- #

_GREETING_WORDS = {"hi", "hello", "hey", "yo", "hiya", "howdy", "greetings", "hullo", "heya"}


def _social_reply(text: str) -> str | None:
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return "Hi! I'm Sunny, the Sunnyside front desk. What can I help you with?"
    if len(words) > 5:
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


def _format_from_entity(e: dict) -> tuple[str, str, str]:
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
    facts = ", ".join(f"{k}: {v}" for k, v in attrs.items() if isinstance(v, (str, int, float)))
    return (f"{e['name']} — {facts}", citation, source_text)


def _mock_answer(db: Session, question: str) -> dict:
    sub = retrieval.retrieve_subgraph(db, question, k=4)
    hits = sub["hits"]
    top = hits[0] if hits else None
    confidence = 0.0
    citations: list[str] = []
    answer, citation, source = ("", None, None)
    if top and top["lexical"] > 0:
        confidence = round(min(1.0, 0.6 + 0.4 * top["lexical"]), 3)
        citations = [top["id"]]
        answer, citation, source = _format_from_entity(top)
    elif top:
        confidence = round(top["semantic"] * 0.3, 3)
    return {
        "answer": answer,
        "citation": citation,
        "source": source,
        "citations": citations,
        "confidence": confidence,
    }


def _answer_mock(db: Session, question: str) -> dict:
    sensitive = escalation.classify_sensitive(question)
    if sensitive is not None:
        return _sensitive_response(db, question, sensitive)
    social = _social_reply(question)
    if social is not None:
        return _greeting_response(question, social)
    raw = _mock_answer(db, question)
    decision = escalation.decide(question, raw["confidence"], raw["citations"])
    if decision.needs_escalation:
        return _gap_response(question)
    return _answer_response(
        db, question, raw["answer"], raw["citation"], raw["source"],
        raw["citations"], raw["confidence"],
    )


# --------------------------------------------------------------------------- #


def answer_question(db: Session, question: str) -> dict:
    """Full pipeline. Returns a shape the frontend can render directly."""
    if settings.bedrock_enabled:
        return _answer_bedrock(db, question)
    return _answer_mock(db, question)
