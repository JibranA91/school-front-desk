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
import uuid
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

DEFAULT_OOS_MSG = (
    "I'm the Sunnyside front desk, so I can help with things like hours, tuition, "
    "meals, enrollment, and our policies — but that one's outside what I can help "
    "with. Is there something about the center I can answer?"
)

# Live-data tool results aren't graph entities, so they carry a `ref` token the
# model cites instead of an entity id. Each maps to how we show provenance.
LIVE_SOURCES: dict[str, tuple[str, str]] = {
    "live:menu": ("per Today’s Menu", "Today's Menu · synced from the kitchen this morning."),
    "live:programs": ("per our Programs", "Live from Sunnyside's program roster."),
    "live:center": ("per our Center details", "Live from Sunnyside's profile."),
    "live:children": ("per your enrollment record", "Live from your family's record."),
}


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


def _oos_response(question: str, text: str) -> dict:
    # Out of scope for a daycare front desk (weather, sports, general trivia):
    # decline politely and DO NOT log — junk must not pollute the operator inbox.
    r = _base(question, status="answered", category="out_of_scope", needs_escalation=False,
              confidence=1.0, citations=[], log=False)
    r.update(kind="assistant-text", answer=text or DEFAULT_OOS_MSG, citation=None, source=None, menu=None)
    return r


# A "while you wait" policy is attached only where a curated entity is reliably
# the right one for the category. Retrieval-picked policies proved tangential on
# sensitive topics (e.g. a peanut-allergy question matching a birthday-treats
# policy), and this is the path where we're most cautious — so we map explicitly
# and stay silent for categories without a clearly-relevant curated policy.
_SENSITIVE_RELATED: dict[str, str] = {"health": "policy-illness"}


def _sensitive_response(question: str, category: str) -> dict:
    related = ""
    entity_id = _SENSITIVE_RELATED.get(category)
    if entity_id:
        pol = retrieval.get_retriever().get_entity(entity_id)
        body = (pol.get("attributes") or {}).get("body") if pol else None
        if isinstance(body, str) and body:
            related = f" While you wait, here's our related policy — {pol['name']}: {body}"
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
    # Show the menu card ONLY when the answer is genuinely grounded in today's
    # menu — i.e. the agent actually called the live menu tool. We render the
    # model's own grounded answer, never a canned string, and never trigger on a
    # bare keyword like "lunch" (which used to hijack e.g. "can my child bring
    # fish for lunch?").
    if "live:menu" in (citations or []):
        menu = todays_menu(db)
        if menu:
            r = _base(question, status="answered", category=None, needs_escalation=False,
                      confidence=confidence, citations=citations, log=True)
            r.update(
                kind="lunch",
                answer=answer,
                menu=menu,
                citation=citation or "per Today’s Menu",
                source=source or "Today's Menu · synced from the kitchen this morning.",
            )
            return r
    r = _base(question, status="answered", category=None, needs_escalation=False,
              confidence=confidence, citations=citations, log=True)
    r.update(kind="confident", answer=answer, citation=citation, source=source, menu=None)
    return r


def _citation_details(citations: list[str]) -> tuple[str | None, str | None]:
    if not citations:
        return None, None
    top = citations[0]
    if top in LIVE_SOURCES:  # live-data source, not a graph entity
        return LIVE_SOURCES[top]
    e = retrieval.get_retriever().get_entity(top)
    if not e:
        return None, None
    srcs = e.get("sources") or []
    return f"per {e['name']}", (srcs[0] if srcs else e.get("snippet"))


# --------------------------------------------------------------------------- #
# Bedrock path — all messages through the LLM, model-classified intent.
# --------------------------------------------------------------------------- #


def _bedrock_answer(db: Session, question: str, asker_id: uuid.UUID | None = None) -> dict:
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent
    from pydantic import BaseModel, Field

    from app.llm import get_chat_model

    # --- Knowledge-graph tools (the stored source of truth) ---
    # Read through the configured Retriever — the agent never touches the store.
    kb = retrieval.get_retriever()

    @tool
    def search_graph(query: str) -> list[dict]:
        """Search the center's knowledge graph for entities relevant to a query."""
        return kb.search(query, k=5)

    @tool
    def get_entity(entity_id: str) -> dict | None:
        """Fetch a single knowledge-graph entity by its id."""
        return kb.get_entity(entity_id)

    @tool
    def expand_neighbors(entity_id: str) -> list[dict]:
        """Get entities directly related (1 hop) to the given entity."""
        return kb.expand_neighbors(entity_id)

    # --- Live-data tools (query the database directly, not the graph) ---
    @tool
    def get_todays_menu() -> dict:
        """Today's lunch and snacks, synced live from the kitchen. Use for any
        menu/lunch/food question. Cite ref 'live:menu'."""
        menu = todays_menu(db)
        return {"ref": "live:menu", "items": menu or [], "posted": bool(menu)}

    @tool
    def get_programs() -> dict:
        """The center's live program roster — each program's name, age range,
        staff-to-child ratio, and room. Cite ref 'live:programs'."""
        rows = db.scalars(select(models.Program).order_by(models.Program.name)).all()
        return {
            "ref": "live:programs",
            "programs": [
                {"name": p.name, "age_range": p.age_range, "ratio": p.ratio, "room": p.room}
                for p in rows
            ],
        }

    @tool
    def get_center_info() -> dict:
        """The center's live profile — name, phone, address, and operating hours.
        Cite ref 'live:center'."""
        cfg = db.get(models.CenterConfig, 1)
        if not cfg:
            return {"ref": "live:center"}
        return {
            "ref": "live:center",
            "name": cfg.name,
            "phone": cfg.phone,
            "address": cfg.address,
            "hours": cfg.hours,
        }

    tools = [
        search_graph, get_entity, expand_neighbors,
        get_todays_menu, get_programs, get_center_info,
    ]

    # Personalized tool — only registered for an authenticated parent, and
    # scoped strictly to that parent's own children (never another family's).
    if asker_id is not None:
        @tool
        def get_my_children() -> dict:
            """The asking family's enrolled children — each child's first name,
            program, room, and age range. Use for personal questions like
            'what room is my child in?'. Cite ref 'live:children'."""
            kids = db.scalars(
                select(models.Child).where(models.Child.parent_id == asker_id)
            ).all()
            return {
                "ref": "live:children",
                "children": [
                    {
                        "name": c.name,
                        "program": c.program.name if c.program else None,
                        "room": c.program.room if c.program else None,
                        "age_range": c.program.age_range if c.program else None,
                    }
                    for c in kids
                ],
            }

        tools.append(get_my_children)

    class Answer(BaseModel):
        intent: Literal["greeting", "answer", "unknown", "out_of_scope"] = Field(
            description="greeting = small talk/thanks; answer = a center question you "
            "answered from the tools; unknown = a CENTER question no tool can answer "
            "(a real knowledge gap for staff); out_of_scope = not about this childcare "
            "center at all (weather, sports, general trivia, unrelated requests)."
        )
        answer: str = Field(description="Reply text: the grounded answer, a warm greeting, or empty if unknown.")
        confidence: float = Field(description="0..1 confidence the answer is correct and grounded.")
        citations: list[str] = Field(
            description="What the answer is grounded in: knowledge-graph entity ids "
            "and/or live-tool refs (e.g. 'live:menu'). Empty for greeting/unknown."
        )

    cfg = db.get(models.CenterConfig, 1)
    center = cfg.name if cfg else "the center"
    system = (
        f"You are Sunny, the AI front desk for {center}, chatting with a parent.\n"
        "- Greetings or small talk (hi, thanks, how are you): reply warmly and briefly, "
        "invite a question, DO NOT use tools. Set intent='greeting'.\n"
        "- A question about the center: use the tools to find the answer and ground it. "
        "For policies and general info use the knowledge-graph tools (search_graph, "
        "get_entity, expand_neighbors). For information that changes or is specific to "
        "this family, use the LIVE tools: get_todays_menu (menu/lunch), get_programs "
        "(ages/ratios/rooms), get_center_info (phone/address/hours)"
        + (", get_my_children (this family's kids/rooms)" if asker_id is not None else "")
        + ". List every source you used in `citations` — entity ids and/or live refs "
        "like 'live:menu'. Set intent='answer'. Be warm, concise, and specific.\n"
        "- A CENTER question no tool can answer (a real gap for staff to fill): set "
        "intent='unknown', answer='', no citations.\n"
        "- A question NOT about this childcare center at all (weather, sports, news, "
        "general trivia, unrelated requests): set intent='out_of_scope' and write a "
        "brief, friendly redirect back to what you can help with. No citations.\n"
        "\nGROUNDING — this is critical:\n"
        "- If the tool results DO address the question, ANSWER it (intent='answer') "
        "and cite them. Never hand off a question the knowledge base can answer.\n"
        "- Assert ONLY what the tool results explicitly state. Never infer, extrapolate, "
        "guess, or combine facts to fill a gap, and never use outside knowledge.\n"
        "- If the SPECIFIC thing asked isn't in the tool results — even when related "
        "information exists — set intent='unknown'. Related-but-not-specific is NOT an "
        "answer. (E.g. a general fee policy doesn't let you confirm a specific discount "
        "it never mentions.)\n"
        "- Do NOT assert a negative from absence. If a parent asks whether you offer "
        "something and the tool results don't mention it, set intent='unknown' (staff "
        "will confirm) rather than guessing 'no'.\n"
        "Return the structured Answer."
    )
    agent = create_react_agent(
        # temperature=0: this is factual grounding, not creative writing — keeps
        # borderline answer/hand-off decisions stable across runs.
        get_chat_model(settings.bedrock_parent_model, temperature=0),
        tools=tools,
        prompt=system,
        response_format=Answer,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    s: Answer = result["structured_response"]
    # A citation is valid if it's a real entity or a known live-data ref.
    valid = [c for c in s.citations if c in LIVE_SOURCES or kb.get_entity(c)]
    citation, source = _citation_details(valid)
    return {
        "intent": s.intent,
        "answer": s.answer,
        "confidence": float(s.confidence),
        "citations": valid,
        "citation": citation,
        "source": source,
    }


def _answer_bedrock(db: Session, question: str, asker_id: uuid.UUID | None = None) -> dict:
    # Safety net first, deterministically — sensitive topics always escalate,
    # without depending on (or paying for) the model.
    sensitive = escalation.classify_sensitive(question)
    if sensitive is not None:
        return _sensitive_response(question, sensitive)

    raw = _bedrock_answer(db, question, asker_id)
    if raw["intent"] == "greeting":
        return _greeting_response(question, raw["answer"] or "Hi! How can I help you today?")
    if raw["intent"] == "out_of_scope":
        return _oos_response(question, raw["answer"])
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


def _mock_answer(question: str) -> dict:
    sub = retrieval.get_retriever().retrieve_subgraph(question, k=4)
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
        return _sensitive_response(question, sensitive)
    social = _social_reply(question)
    if social is not None:
        return _greeting_response(question, social)
    raw = _mock_answer(question)
    decision = escalation.decide(question, raw["confidence"], raw["citations"])
    if decision.needs_escalation:
        return _gap_response(question)
    return _answer_response(
        db, question, raw["answer"], raw["citation"], raw["source"],
        raw["citations"], raw["confidence"],
    )


# --------------------------------------------------------------------------- #


def answer_question(
    db: Session, question: str, asker_id: uuid.UUID | None = None
) -> dict:
    """Full pipeline. Returns a shape the frontend can render directly.

    `asker_id` is the authenticated parent (server-derived, never client-trusted);
    it scopes the personalized live-data tool to that family. The mock path has no
    tool-calling, so it ignores it.
    """
    if settings.bedrock_enabled:
        return _answer_bedrock(db, question, asker_id)
    return _answer_mock(db, question)
