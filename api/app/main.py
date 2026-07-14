import tempfile
import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import uuid

from pydantic import BaseModel

from app.config import settings
from app.model_catalog import resolve_chat_model
from app.db import SessionLocal, get_db, init_db
from app import agent, authoring, ingest, models, retrieval
from app.routers import auth as auth_router


def _maybe_seed_on_start() -> None:
    """First-boot convenience for hosted deploys (e.g. Railway). When
    SEED_ON_START is "demo" or "fresh" AND the database has no users yet, load
    the seed data. The empty-DB guard means an existing dataset is never
    overwritten, so it's safe to leave enabled across redeploys."""
    mode = (settings.seed_on_start or "").lower()
    if mode not in ("demo", "fresh"):
        return
    try:
        from app import seed as seed_mod

        with SessionLocal() as db:
            has_users = db.scalar(select(models.User).limit(1)) is not None
        if has_users:
            print("[startup] seed_on_start: users already present — skipping.")
            return
        print(f"[startup] seed_on_start={mode}: empty database, seeding…")
        seed_mod.seed(fresh=(mode == "fresh"))
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] seed_on_start skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort: create the extension + tables on boot. If the DB isn't up
    # yet, don't crash the process — /health still answers.
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] init_db skipped: {exc}")
    _maybe_seed_on_start()
    yield


app = FastAPI(title="AI Front Desk API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "provider": settings.provider,  # bedrock | anthropic | mock
        "llm_enabled": settings.llm_enabled,
        "retrieval": "hybrid" if settings.embeddings_enabled else "fts-only",
        "embeddings": settings.embedder if settings.embeddings_enabled else "off",
        "models": {
            "parent": resolve_chat_model(settings.parent_model, settings.provider),
            "chat": resolve_chat_model(settings.chat_model, settings.provider),
        } if settings.llm_enabled else "mock",
    }


@app.get("/center")
def center(db: Session = Depends(get_db)) -> dict:
    cfg = db.get(models.CenterConfig, 1)
    if not cfg:
        return {}
    return {"name": cfg.name, "phone": cfg.phone, "address": cfg.address, "hours": cfg.hours}


@app.get("/search")
def search(q: str, k: int = 4) -> dict:
    """Debug endpoint for the retrieval layer — hybrid search + 1-hop expansion.
    Goes through the configured Retriever, not the DB directly."""
    return retrieval.get_retriever().retrieve_subgraph(q, k)


class AskRequest(BaseModel):
    question: str
    asker_id: str | None = None
    child_id: str | None = None
    session_id: str | None = None


class ActorRequest(BaseModel):
    """Just who is acting — for endpoints that carry no other payload
    (entity delete, changelog revert)."""

    actor: str = "Operator"
    actor_user_id: str | None = None


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _conversation_for(db: Session, parent_id: uuid.UUID) -> models.Conversation:
    """The parent's chat thread — one per parent, created on first message."""
    conv = db.scalar(
        select(models.Conversation)
        .where(models.Conversation.parent_id == parent_id)
        .order_by(models.Conversation.created_at)
        .limit(1)
    )
    if conv is None:
        conv = models.Conversation(parent_id=parent_id)
        db.add(conv)
        db.flush()
    return conv


def _message_to_msg(m: models.Message, idx: int) -> dict:
    """Serialize a stored message into the shape the chat UI renders."""
    c = m.content or {}
    out: dict = {"id": idx, "type": m.kind}
    if m.kind == "user":
        out["text"] = c.get("text")
    elif m.kind == "assistant-text":
        out["text"] = c.get("answer") or c.get("text")
    elif m.kind == "staff":
        out["text"] = c.get("text")
        out["by"] = c.get("by")
    else:  # confident | escalation | lunch
        out.update(
            answer=c.get("answer"),
            citation=c.get("citation"),
            source=c.get("source"),
            menu=c.get("menu"),
        )
    return out


def _thread_up_to(db: Session, inq: models.Inquiry) -> list[dict]:
    """Messages for the operator to read behind an inquiry: scoped to that
    inquiry's chat session and cut off at the moment the question was asked —
    so the operator sees the lead-up to *this* question, not later turns or
    other sessions. Legacy inquiries (no session_id) fall back to time-only."""
    conv = db.scalar(
        select(models.Conversation)
        .where(models.Conversation.parent_id == inq.asker_id)
        .order_by(models.Conversation.created_at)
        .limit(1)
    )
    if conv is None:
        return []
    q = (
        select(models.Message)
        .where(models.Message.conversation_id == conv.id)
        .where(models.Message.created_at <= inq.created_at)
        .order_by(models.Message.created_at)
    )
    if inq.session_id:
        q = q.where(models.Message.session_id == inq.session_id)
    rows = db.scalars(q).all()
    return [_message_to_msg(m, i + 1) for i, m in enumerate(rows)]


def _thread_messages(db: Session, parent_id: uuid.UUID) -> list[dict]:
    conv = db.scalar(
        select(models.Conversation)
        .where(models.Conversation.parent_id == parent_id)
        .order_by(models.Conversation.created_at)
        .limit(1)
    )
    if conv is None:
        return []
    rows = db.scalars(
        select(models.Message)
        .where(models.Message.conversation_id == conv.id)
        .order_by(models.Message.created_at)
    ).all()
    return [_message_to_msg(m, i + 1) for i, m in enumerate(rows)]


# Topic (for inbox grouping) derived from what the answer was grounded in.
_LIVE_TOPIC = {
    "live:menu": "Meal",
    "live:menu-week": "Meal",
    "live:programs": "Program",
    "live:center": "Center",
    "live:children": "Enrollment",
}
_CATEGORY_TOPIC = {
    "health": "Health",
    "allergy": "Health",
    "medication": "Health",
    "safety": "Safety",
    "billing_dispute": "Billing",
    "custody": "Family",
}


def _topic_for(db: Session, result: dict) -> str | None:
    """The subject of a question, for inbox grouping — the type of the primary
    cited entity, else a category-derived theme, else None (Other)."""
    cits = result.get("citations") or []
    if cits:
        top = cits[0]
        if top in _LIVE_TOPIC:
            return _LIVE_TOPIC[top]
        entity = db.get(models.KbEntity, top)
        if entity is not None:
            return entity.type
    category = result.get("category")
    return _CATEGORY_TOPIC.get(category) if category else None


@app.post("/ask")
def ask(body: AskRequest, db: Session = Depends(get_db)) -> dict:
    """Parent asks a question. Runs the agent, persists the turn to the parent's
    conversation thread, logs the inquiry for the operator inbox, and returns a
    renderable answer."""
    asker = _as_uuid(body.asker_id)
    result = agent.answer_question(
        db, body.question, asker_id=asker, session_id=body.session_id
    )

    # Persist the transcript (the human 1:1 channel — never read by the agent).
    if asker is not None:
        conv = _conversation_for(db, asker)
        db.add(
            models.Message(
                conversation_id=conv.id, role="user", kind="user",
                content={"text": body.question}, session_id=body.session_id,
            )
        )
        db.add(
            models.Message(
                conversation_id=conv.id, role="assistant", kind=result["kind"],
                content={
                    "answer": result.get("answer"),
                    "citation": result.get("citation"),
                    "source": result.get("source"),
                    "menu": result.get("menu"),
                },
                session_id=body.session_id,
            )
        )
        db.commit()

    # Small talk (greetings, thanks) isn't a question the operator needs to see.
    if result.get("log", True):
        inquiry = models.Inquiry(
            asker_id=asker,
            child_id=_as_uuid(body.child_id),
            text=body.question,
            status=result["status"],
            category=result.get("category"),
            topic=_topic_for(db, result),
            confidence=result.get("confidence"),
            group_key=result.get("group_key"),
            session_id=body.session_id,
        )
        db.add(inquiry)
        db.commit()
        result["inquiry_id"] = str(inquiry.id)

    return result


@app.get("/history")
def history(parent_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """The authenticated parent's own chat transcript (staff replies included)."""
    pid = _as_uuid(parent_id)
    return _thread_messages(db, pid) if pid else []


# Which inquiry states belong in the parent's Updates feed — the questions that
# went to staff (not the ones the AI already answered inline in chat).
_UPDATE_STATES = ("escalated", "lowconf", "resolved")


@app.get("/my/updates")
def my_updates(parent_id: str, db: Session = Depends(get_db)) -> dict:
    """The parent's escalated questions + staff answers — a durable notifications
    feed, independent of the ephemeral chat session. `unseen` counts answers that
    arrived since the parent last opened the feed."""
    pid = _as_uuid(parent_id)
    if pid is None:
        return {"updates": [], "unseen": 0}
    rows = db.scalars(
        select(models.Inquiry)
        .where(models.Inquiry.asker_id == pid)
        .where(models.Inquiry.status.in_(_UPDATE_STATES))
        .order_by(models.Inquiry.created_at.desc())
    ).all()
    user = db.get(models.User, pid)
    seen_at = user.updates_seen_at if user else None

    updates, unseen = [], 0
    for r in rows:
        answered = bool(r.resolution_text)
        is_unseen = answered and (
            seen_at is None or (r.resolved_at is not None and r.resolved_at > seen_at)
        )
        if is_unseen:
            unseen += 1
        updates.append(
            {
                "id": str(r.id),
                "question": r.text,
                "answered": answered,
                "answer": r.resolution_text,
                "category": r.category,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "answered_at": r.resolved_at.isoformat() if r.resolved_at else None,
                "unseen": is_unseen,
            }
        )
    return {"updates": updates, "unseen": unseen}


@app.post("/my/updates/seen")
def my_updates_seen(parent_id: str, db: Session = Depends(get_db)) -> dict:
    """Mark the parent's Updates feed as read (clears the unseen badge)."""
    pid = _as_uuid(parent_id)
    user = db.get(models.User, pid) if pid else None
    if user is not None:
        user.updates_seen_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


class ThemeRequest(BaseModel):
    theme: str  # 'light' | 'dark'


@app.post("/me/theme")
def set_theme(body: ThemeRequest, user_id: str, db: Session = Depends(get_db)) -> dict:
    """Persist the signed-in user's color-scheme preference. Applies to any user
    (parent or operator); user_id comes from the trusted session, never the client."""
    theme = body.theme if body.theme in ("light", "dark") else "light"
    user = db.get(models.User, _as_uuid(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.theme = theme
    db.commit()
    return {"ok": True, "theme": theme}


class AuthorProposeRequest(BaseModel):
    instruction: str


class AuthorApplyRequest(BaseModel):
    changes: list[dict]
    summary: str | None = None
    accept_conflicts: bool = True
    actor: str = "Operator"
    actor_user_id: str | None = None


@app.post("/author/propose")
def author_propose(body: AuthorProposeRequest, db: Session = Depends(get_db)) -> dict:
    """Operator instruction → proposed graph changes + conflict detection (no write)."""
    return authoring.propose(db, body.instruction)


@app.post("/author/apply")
def author_apply(body: AuthorApplyRequest, db: Session = Depends(get_db)) -> dict:
    """Apply confirmed changes to the graph + changelog."""
    return authoring.apply(
        db,
        body.changes,
        actor=body.actor,
        summary=body.summary,
        actor_user_id=_as_uuid(body.actor_user_id),
        accept_conflicts=body.accept_conflicts,
    )


# In-memory ingest job progress (single-process demo; not persisted).
_INGEST_JOBS: dict[str, dict] = {}


def _run_ingest_job(job_id: str, tmp_path: Path, label: str, actor: str, replace: bool) -> None:
    """Background worker: clears (optionally), ingests, and links — updating the
    job's progress dict as it works through the handbook's sections."""
    job = _INGEST_JOBS[job_id]
    db = None
    try:
        db = SessionLocal()
        if replace:
            job.update(phase="Clearing the previous handbook…")
            job["replaced"] = ingest.clear_ingested(db)
        job.update(phase="Reading the handbook…")

        def on_progress(done: int, total: int, entities: int, pages: int) -> None:
            job.update(
                phase=f"Reading section {done} of {total}…",
                chunks_done=done,
                chunks_total=total,
                entities=entities,
                pages=pages,
            )

        report = ingest.ingest_pdf(
            db, tmp_path, source_label=label, actor=actor, progress=on_progress
        )
        report["replaced"] = job.get("replaced", 0)
        job.update(status="done", phase="Done", entities=report["created"], report=report)
    except Exception as exc:  # noqa: BLE001
        job.update(status="error", error=str(exc))
    finally:
        if db is not None:
            db.close()
        tmp_path.unlink(missing_ok=True)


@app.post("/ingest")
async def ingest_handbook(
    file: UploadFile = File(...),
    label: str = Form("Family Handbook"),
    actor: str = Form("Operator"),
    replace: bool = Form(True),
) -> dict:
    """Start a handbook ingestion job. Returns a job_id immediately; the client
    polls /ingest/status/{job_id} for live progress. The extraction agent turns
    the PDF into typed `hb-` entities; `replace` clears any prior import first."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    job_id = uuid.uuid4().hex
    tmp_path = Path(tempfile.gettempdir()) / f"handbook-{job_id}.pdf"
    tmp_path.write_bytes(data)
    _INGEST_JOBS[job_id] = {
        "status": "running",
        "phase": "Starting…",
        "pages": 0,
        "chunks_done": 0,
        "chunks_total": 0,
        "entities": 0,
        "replaced": 0,
    }
    threading.Thread(
        target=_run_ingest_job,
        args=(job_id, tmp_path, label, actor, replace),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/ingest/status/{job_id}")
def ingest_status(job_id: str) -> dict:
    """Live progress for a handbook ingestion job (running | done | error)."""
    job = _INGEST_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown ingest job.")
    return job


@app.get("/changelog")
def changelog(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(models.ChangelogEntry).order_by(models.ChangelogEntry.created_at.desc())
    ).all()
    out = []
    for c in rows:
        initials = "".join(w[0] for w in c.actor.split()[:2]).upper() or "?"
        color = (
            "#5463D6" if c.actor_user_id else ("#29B9BB" if c.actor == "AI Front Desk" else "#737685")
        )
        out.append(
            {
                "id": str(c.id),
                "who": c.actor,
                "when": c.created_at.strftime("%b %d · %I:%M %p").replace(" 0", " ")
                if c.created_at
                else "",
                "what": c.action,
                "before": c.before,
                "after": c.after,
                "isDiff": c.is_diff,
                "initials": initials,
                "color": color,
                # Only operator edits/deletes carry a restorable snapshot.
                "revertable": c.snapshot is not None,
            }
        )
    return out


@app.post("/changelog/{entry_id}/revert")
def revert_change(
    entry_id: str, body: ActorRequest = ActorRequest(), db: Session = Depends(get_db)
) -> dict:
    """Undo a previous change by restoring the entity to its pre-change state
    (from the changelog snapshot). An add reverts to a delete; an update or a
    delete reverts to the captured 'before'. Logs the revert itself."""
    entry = db.get(models.ChangelogEntry, _as_uuid(entry_id))
    if entry is None:
        raise HTTPException(status_code=404, detail="Changelog entry not found.")
    snap = entry.snapshot
    if not snap:
        raise HTTPException(status_code=400, detail="This change can't be reverted.")

    eid = snap["entity_id"]
    before = snap.get("before")
    e = db.get(models.KbEntity, eid)

    if before is None:
        # The change created this entity — undoing it means removing it.
        label = e.name if e is not None else eid
        if e is not None:
            _delete_entity_cascade(db, e)
        action = f"Reverted — removed {label}"
        entity_id = None
    else:
        # Restore (recreating the entity if a delete is being undone).
        if e is None:
            e = models.KbEntity(id=eid, type=before["type"], name=before["name"])
            db.add(e)
            db.flush()
        e.type = before["type"]
        e.name = before["name"]
        e.attributes = dict(before.get("attributes") or {})
        flag_modified(e, "attributes")
        e.sources = list(before.get("sources") or [])
        _reembed(db, e)
        action = f"Reverted change to {before['name']}"
        entity_id = e.id

    db.add(
        models.ChangelogEntry(
            actor=body.actor,
            actor_user_id=_as_uuid(body.actor_user_id),
            action=action,
            entity_id=entity_id,
            is_diff=False,
            snapshot=None,  # a revert is not itself revertable
        )
    )
    db.commit()
    return {"ok": True}


@app.get("/inbox/{inquiry_id}/thread")
def inbox_thread(inquiry_id: str, db: Session = Depends(get_db)) -> dict:
    """The parent's full conversation behind an inquiry, for the operator to read
    before replying. Anonymous inquiries have no account/thread to reply into."""
    inq = db.get(models.Inquiry, _as_uuid(inquiry_id))
    if inq is None:
        raise HTTPException(status_code=404, detail="Inquiry not found.")
    messages = _thread_up_to(db, inq) if inq.asker_id else []
    return {
        "who": _asker_context(db, inq),
        "session": (inq.session_id or "")[:6],
        "can_reply": inq.asker_id is not None,
        "messages": messages,
    }


class ReplyRequest(BaseModel):
    text: str
    actor: str = "Operator"
    actor_user_id: str | None = None


@app.post("/inbox/{inquiry_id}/reply")
def reply_inquiry(
    inquiry_id: str, body: ReplyRequest, db: Session = Depends(get_db)
) -> dict:
    """Operator replies directly to the parent — a private message in the thread.
    This is NOT a knowledge update: it lands in `messages`, which the agent never
    reads, so it can't affect future AI answers. Resolves just this inquiry."""
    inq = db.get(models.Inquiry, _as_uuid(inquiry_id))
    if inq is None:
        raise HTTPException(status_code=404, detail="Inquiry not found.")
    if inq.asker_id is None:
        raise HTTPException(status_code=400, detail="This inquiry has no parent account to reply to.")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Reply is empty.")

    conv = _conversation_for(db, inq.asker_id)
    msg = models.Message(
        conversation_id=conv.id, role="assistant", kind="staff",
        content={"text": text, "by": body.actor},
    )
    db.add(msg)
    inq.status = "resolved"
    inq.resolution_text = text
    inq.resolved_by_id = _as_uuid(body.actor_user_id)
    inq.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "message_id": str(msg.id)}


@app.get("/graph")
def graph(db: Session = Depends(get_db)) -> dict:
    """The knowledge graph for visualization: typed nodes + relationship edges."""
    entities = db.scalars(select(models.KbEntity)).all()
    rels = db.scalars(select(models.KbRelationship)).all()
    nodes = [
        {
            "id": e.id,
            "type": e.type,
            "name": e.name,
            "source": (e.sources[0] if e.sources else None),
            "handbook": e.id.startswith("hb-"),
        }
        for e in entities
    ]
    edges = [{"source": r.src_id, "target": r.dst_id, "rel": r.rel} for r in rels]
    return {"nodes": nodes, "edges": edges}


def _entity_origin(e: models.KbEntity) -> str:
    """Where a fact came from — drives the inspector's filter + delete warning.
    handbook: an imported `hb-` node; authored: created by an operator via the
    authoring agent ('Set by …'); seed: the curated demo backbone."""
    if e.id.startswith("hb-"):
        return "handbook"
    if any(str(s).startswith("Set by") for s in (e.sources or [])):
        return "authored"
    return "seed"


def _entity_state(e: models.KbEntity) -> dict:
    """A restorable snapshot of an entity — stored on the changelog so a change
    can be reverted later (see /changelog/{id}/revert)."""
    return {
        "type": e.type,
        "name": e.name,
        "attributes": dict(e.attributes or {}),
        "sources": list(e.sources or []),
    }


def _reembed(db: Session, e: models.KbEntity) -> None:
    from app.embeddings import embed_texts, entity_text

    e.embedding = embed_texts([entity_text(e)])[0]


def _delete_entity_cascade(db: Session, e: models.KbEntity) -> None:
    """Remove an entity and everything that references it: incident relationship
    edges, and the FK link from any changelog rows (history is kept, unlinked)."""
    db.query(models.KbRelationship).filter(
        (models.KbRelationship.src_id == e.id) | (models.KbRelationship.dst_id == e.id)
    ).delete(synchronize_session=False)
    db.query(models.ChangelogEntry).filter(
        models.ChangelogEntry.entity_id == e.id
    ).update({models.ChangelogEntry.entity_id: None}, synchronize_session=False)
    db.delete(e)


@app.get("/entities")
def list_entities(db: Session = Depends(get_db)) -> list[dict]:
    """Full detail on every knowledge-graph node, for the operator's inspector —
    attributes, sources, origin, and how many edges touch it."""
    entities = db.scalars(select(models.KbEntity)).all()
    rels = db.scalars(select(models.KbRelationship)).all()
    deg: Counter = Counter()
    for r in rels:
        deg[r.src_id] += 1
        deg[r.dst_id] += 1
    out = [
        {
            "id": e.id,
            "type": e.type,
            "name": e.name,
            "attributes": e.attributes or {},
            "sources": e.sources or [],
            "origin": _entity_origin(e),
            "connections": deg.get(e.id, 0),
            "updated_at": e.updated_at.isoformat() if e.updated_at else None,
        }
        for e in entities
    ]
    out.sort(key=lambda d: (d["type"], d["name"]))
    return out


class EntityPatchRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    attributes: dict | None = None  # full replacement of the attributes map
    actor: str = "Operator"
    actor_user_id: str | None = None


@app.patch("/entity/{entity_id}")
def update_entity(
    entity_id: str, body: EntityPatchRequest, db: Session = Depends(get_db)
) -> dict:
    """Directly edit an entity's name/type/attributes (no LLM). Re-embeds so
    retrieval stays fresh, and logs a revertable changelog entry."""
    e = db.get(models.KbEntity, entity_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Entity not found.")

    before = _entity_state(e)
    new_attrs = body.attributes if body.attributes is not None else dict(e.attributes or {})

    # A representative diff for the changelog display (first changed attribute,
    # else the name).
    diff_before = diff_after = None
    is_diff = False
    for k in new_attrs:
        if str(before["attributes"].get(k)) != str(new_attrs.get(k)):
            diff_after = f"{k}: {new_attrs.get(k)}"
            if k in before["attributes"]:
                diff_before = f"{k}: {before['attributes'].get(k)}"
                is_diff = True
            break
    if body.name is not None and body.name != e.name:
        diff_before = diff_before or before["name"]
        diff_after = diff_after or body.name
        is_diff = True

    if body.name is not None:
        e.name = body.name
    if body.type is not None:
        e.type = body.type
    if body.attributes is not None:
        e.attributes = new_attrs
        flag_modified(e, "attributes")
    _reembed(db, e)

    db.add(
        models.ChangelogEntry(
            actor=body.actor,
            actor_user_id=_as_uuid(body.actor_user_id),
            action=f"Edited {e.name}",
            entity_id=e.id,
            before=diff_before,
            after=diff_after,
            is_diff=is_diff,
            snapshot={"entity_id": entity_id, "before": before},
        )
    )
    db.commit()
    return {"ok": True, "id": e.id}


@app.delete("/entity/{entity_id}")
def delete_entity(
    entity_id: str, body: ActorRequest = ActorRequest(), db: Session = Depends(get_db)
) -> dict:
    """Remove an entity from the knowledge graph. Its incident edges go too;
    changelog history is preserved. The deletion itself is revertable."""
    e = db.get(models.KbEntity, entity_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    state = _entity_state(e)
    _delete_entity_cascade(db, e)
    db.add(
        models.ChangelogEntry(
            actor=body.actor,
            actor_user_id=_as_uuid(body.actor_user_id),
            action=f"Removed {state['name']}",
            entity_id=None,  # entity no longer exists; id lives in the snapshot
            is_diff=False,
            snapshot={"entity_id": entity_id, "before": state},
        )
    )
    db.commit()
    return {"deleted": entity_id}


def _asker_context(db: Session, inq: models.Inquiry) -> str:
    """Human label for who asked — real context for the operator ('Parent of
    Ava · Discovery Room'), or 'Prospective family' for anonymous inquiries."""
    if inq.child_id:
        child = db.get(models.Child, inq.child_id)
        if child:
            room = child.program.room if child.program else None
            return f"Parent of {child.name}" + (f" · {room}" if room else "")
    if inq.asker_id:
        user = db.get(models.User, inq.asker_id)
        if user:
            return user.name
    return "Prospective family"


@app.get("/inbox")
def inbox(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(models.Inquiry).order_by(models.Inquiry.created_at.desc())
    ).all()
    # How many *open* inquiries share each group_key — the "3 parents asked this"
    # demand signal for knowledge gaps.
    open_counts = Counter(
        r.group_key for r in rows if r.group_key and r.status != "resolved"
    )
    return [
        {
            "id": str(r.id),
            "text": r.text,
            "status": r.status,
            "category": r.category,
            "topic": r.topic,
            "confidence": r.confidence,
            "who": _asker_context(db, r),
            "session": (r.session_id or "")[:6],
            "group_key": r.group_key,
            "group_count": open_counts.get(r.group_key, 1) if r.group_key else 1,
            "resolution_text": r.resolution_text,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


class ResolveRequest(BaseModel):
    changes: list[dict] = []
    summary: str | None = None
    accept_conflicts: bool = True
    resolution_text: str | None = None
    actor: str = "Operator"
    actor_user_id: str | None = None
    resolve_group: bool = True


@app.post("/inbox/{inquiry_id}/resolve")
def resolve_inquiry(
    inquiry_id: str, body: ResolveRequest, db: Session = Depends(get_db)
) -> dict:
    """Close the learning loop: fold the operator's answer into the graph (via the
    authoring agent) and mark the inquiry — and any open siblings sharing its
    group_key — resolved, so the next parent gets it grounded."""
    inq = db.get(models.Inquiry, _as_uuid(inquiry_id))
    if inq is None:
        raise HTTPException(status_code=404, detail="Inquiry not found.")

    applied: list[str] = []
    if body.changes:
        result = authoring.apply(
            db,
            body.changes,
            actor=body.actor,
            summary=body.summary,
            actor_user_id=_as_uuid(body.actor_user_id),
            accept_conflicts=body.accept_conflicts,
        )
        applied = result.get("applied", [])

    targets = [inq]
    if body.resolve_group and inq.group_key:
        siblings = db.scalars(
            select(models.Inquiry).where(
                models.Inquiry.group_key == inq.group_key,
                models.Inquiry.status != "resolved",
            )
        ).all()
        targets = siblings or [inq]

    now = datetime.now(timezone.utc)
    for t in targets:
        t.status = "resolved"
        t.resolution_text = body.resolution_text
        t.resolved_by_id = _as_uuid(body.actor_user_id)
        t.resolved_at = now
    db.commit()
    return {"resolved": [str(t.id) for t in targets], "applied": applied}
