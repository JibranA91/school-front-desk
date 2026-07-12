import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.db import get_db
from app.schemas import LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def require_internal_secret(x_internal_secret: str | None = Header(default=None)) -> None:
    """Only the trusted `web` service (which holds the shared secret) may call login."""
    if x_internal_secret != settings.auth_shared_secret:
        raise HTTPException(status_code=401, detail="unauthorized caller")


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_secret),
) -> UserOut:
    user = db.scalar(
        select(models.User).where(func.lower(models.User.email) == body.email.lower())
    )
    if user is None or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        title=user.title,
    )
