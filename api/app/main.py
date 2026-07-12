from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

import uuid

from pydantic import BaseModel

from app.config import settings
from app.db import get_db, init_db
from app import agent, models, retrieval
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
