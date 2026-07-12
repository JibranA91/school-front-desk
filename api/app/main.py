import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

import uuid

from pydantic import BaseModel

from app.config import settings
from app.db import get_db, init_db
from app import agent, authoring, ingest, models, retrieval
from app.routers import auth as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort: create the extension + tables on boot. If the DB isn't up
    # yet, don't crash the process — /health still answers.
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] init_db skipped: {exc}")
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
    return {"status": "ok", "bedrock": settings.bedrock_enabled}


@app.get("/center")
def center(db: Session = Depends(get_db)) -> dict:
    cfg = db.get(models.CenterConfig, 1)
    if not cfg:
        return {}
    return {"name": cfg.name, "phone": cfg.phone, "address": cfg.address, "hours": cfg.hours}


@app.get("/search")
def search(q: str, k: int = 4, db: Session = Depends(get_db)) -> dict:
    """Debug endpoint for the retrieval layer — hybrid search + 1-hop expansion."""
    return retrieval.retrieve_subgraph(db, q, k)


class AskRequest(BaseModel):
    question: str
    asker_id: str | None = None
    child_id: str | None = None


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@app.post("/ask")
def ask(body: AskRequest, db: Session = Depends(get_db)) -> dict:
    """Parent asks a question. Runs the agent, logs the inquiry for the operator
    inbox, and returns a renderable answer."""
    result = agent.answer_question(db, body.question)

    # Small talk (greetings, thanks) isn't a question the operator needs to see.
    if result.get("log", True):
        inquiry = models.Inquiry(
            asker_id=_as_uuid(body.asker_id),
            child_id=_as_uuid(body.child_id),
            text=body.question,
            status=result["status"],
            category=result.get("category"),
            confidence=result.get("confidence"),
            group_key=result.get("group_key"),
        )
        db.add(inquiry)
        db.commit()
        result["inquiry_id"] = str(inquiry.id)

    return result


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


@app.post("/ingest")
async def ingest_handbook(
    file: UploadFile = File(...),
    label: str = Form("Family Handbook"),
    actor: str = Form("Operator"),
    replace: bool = Form(True),
    db: Session = Depends(get_db),
) -> dict:
    """Ingest an uploaded handbook PDF into the knowledge graph. The extraction
    agent (Sonnet when Bedrock is on) turns it into typed `hb-` entities; retrieval
    picks them up immediately. `replace` clears any prior handbook import first."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    removed = ingest.clear_ingested(db) if replace else 0
    tmp_path = Path(tempfile.gettempdir()) / f"handbook-{uuid.uuid4().hex}.pdf"
    try:
        tmp_path.write_bytes(data)
        report = ingest.ingest_pdf(db, tmp_path, source_label=label, actor=actor)
    finally:
        tmp_path.unlink(missing_ok=True)
    report["replaced"] = removed
    return report


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
            }
        )
    return out


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


@app.get("/inbox")
def inbox(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(models.Inquiry).order_by(models.Inquiry.created_at.desc())
    ).all()
    return [
        {
            "id": str(r.id),
            "text": r.text,
            "status": r.status,
            "category": r.category,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
