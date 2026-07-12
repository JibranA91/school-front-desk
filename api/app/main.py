from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, init_db
from app import models


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "bedrock": settings.bedrock_enabled}


@app.get("/center")
def center(db: Session = Depends(get_db)) -> dict:
    cfg = db.get(models.CenterConfig, 1)
    if not cfg:
        return {}
    return {"name": cfg.name, "phone": cfg.phone, "address": cfg.address, "hours": cfg.hours}


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
