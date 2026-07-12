from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # 'parent' | 'operator'
    name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)  # e.g. "Director"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    children: Mapped[list[Child]] = relationship(back_populates="parent")


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(80))  # Infant / Toddler / Preschool
    age_range: Mapped[str] = mapped_column(String(80))
    ratio: Mapped[str] = mapped_column(String(20))
    room: Mapped[str] = mapped_column(String(80))


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    program_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("programs.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parent: Mapped[User] = relationship(back_populates="children")
    program: Mapped[Program | None] = relationship()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # 'user' | 'assistant'
    kind: Mapped[str] = mapped_column(String(30))  # user|assistant-text|confident|escalation|lunch
    content: Mapped[dict] = mapped_column(JSONB)  # {text|answer|citation|source|menu...}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Inquiry(Base):
    """Every parent question surfaced to the operator inbox (answered or not)."""

    __tablename__ = "inquiries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    asker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    child_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("children.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # answered|escalated|lowconf|resolved
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(40), nullable=True)  # grouping: entity type / theme
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    group_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    resolution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbEntity(Base):
    """A typed node in the knowledge graph."""

    __tablename__ = "kb_entities"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # human-readable id, e.g. tuition-infant
    type: Mapped[str] = mapped_column(String(40))  # Hours|Tuition|Policy|Meal|...
    name: Mapped[str] = mapped_column(String(160))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dims), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KbRelationship(Base):
    __tablename__ = "kb_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    rel: Mapped[str] = mapped_column(String(40))  # hasTuition|subjectTo|observes|servedBy
    src_id: Mapped[str] = mapped_column(ForeignKey("kb_entities.id"))
    dst_id: Mapped[str] = mapped_column(ForeignKey("kb_entities.id"))


class ChangelogEntry(Base):
    __tablename__ = "changelog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(120))  # human name | "AI Front Desk" | "Auto-sync"
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("kb_entities.id"), nullable=True)
    before: Mapped[str | None] = mapped_column(Text, nullable=True)
    after: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_diff: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MenuDay(Base):
    """Dynamic data source — today's lunch, 'synced from the kitchen'."""

    __tablename__ = "menu_days"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    day: Mapped[date] = mapped_column(Date, unique=True, index=True)
    items: Mapped[list] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CenterConfig(Base):
    __tablename__ = "center_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    philosophy: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
