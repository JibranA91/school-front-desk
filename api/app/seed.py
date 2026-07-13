"""Seed the Sunnyside Early Learning demo dataset.

Run with the DB up:  uv run python -m app.seed
Resets all tables, then inserts invented demo data (no real personal data).
Embeddings are left NULL here — they're computed when the retrieval layer lands.
"""

from __future__ import annotations

from datetime import date, timedelta

import bcrypt
from sqlalchemy import select

from app.db import Base, SessionLocal, engine, init_db
from app import models
from app.embeddings import embed_texts, entity_text

DEMO_PASSWORD = "demo1234"

# A rotating week of weekday lunches (Mon–Fri), so "menus rotate weekly" is backed
# by real data rather than a single day. Each list is entrée + sides + drink.
WEEKDAY_MENUS: list[list[str]] = [
    ["Turkey & cheese sandwich", "Crisp apple slices", "Whole milk"],
    ["Cheese quesadilla", "Black beans & corn", "Orange wedges", "Whole milk"],
    ["Whole-wheat pasta with marinara", "Steamed green beans", "Pear slices", "Whole milk"],
    ["Baked chicken tenders", "Brown rice", "Roasted carrots", "Whole milk"],
    ["Veggie & cheese pizza", "Garden salad", "Banana", "Whole milk"],
]


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def seed_menu_week(db, today: date | None = None) -> int:
    """Upsert this week's weekday menus (Mon–Fri) so today (if a weekday) always
    has a fresh menu and the demo never goes stale. Idempotent — safe to re-run
    without touching any other data. Returns how many days were written."""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())  # Monday of the current week
    for offset, items in enumerate(WEEKDAY_MENUS):
        day = monday + timedelta(days=offset)
        row = db.scalar(select(models.MenuDay).where(models.MenuDay.day == day))
        if row is None:
            db.add(models.MenuDay(day=day, items=list(items)))
        else:
            row.items = list(items)
    return len(WEEKDAY_MENUS)


def reset_schema() -> None:
    Base.metadata.drop_all(engine)
    init_db()  # CREATE EXTENSION vector + create_all


def seed() -> None:
    reset_schema()
    pw = _hash(DEMO_PASSWORD)
    db = SessionLocal()
    try:
        # --- Center ---
        db.add(
            models.CenterConfig(
                id=1,
                name="Sunnyside Early Learning Center",
                phone="(505) 555-0142",
                address="1200 Meadowlark Lane, Albuquerque, NM",
                hours={"open": "7:00 AM", "close": "6:00 PM", "days": "Mon–Fri"},
                philosophy="Warm, play-based early education for infants through pre-K.",
            )
        )

        # --- Programs ---
        infant = models.Program(name="Infant", age_range="6 wks–12 mo", ratio="1:4", room="Sunroom")
        toddler = models.Program(name="Toddler", age_range="12–36 mo", ratio="1:6", room="Discovery Room")
        preschool = models.Program(name="Preschool", age_range="3–5 yr", ratio="1:10", room="Adventure Room")
        db.add_all([infant, toddler, preschool])
        db.flush()

        # --- Users ---
        maria = models.User(
            email="maria@sunnyside.example",
            password_hash=pw,
            role="operator",
            name="Maria Chen",
            title="Director",
        )
        p_ava = models.User(email="ava.parent@example.com", password_hash=pw, role="parent", name="Dana Ruiz")
        p_noah = models.User(email="noah.parent@example.com", password_hash=pw, role="parent", name="Sam Patel")
        p_liam = models.User(email="liam.parent@example.com", password_hash=pw, role="parent", name="Jordan Lee")
        db.add_all([maria, p_ava, p_noah, p_liam])
        db.flush()

        # --- Children ---
        ava = models.Child(parent_id=p_ava.id, program_id=toddler.id, name="Ava")
        noah = models.Child(parent_id=p_noah.id, program_id=infant.id, name="Noah")
        liam = models.Child(parent_id=p_liam.id, program_id=preschool.id, name="Liam")
        db.add_all([ava, noah, liam])
        db.flush()

        # --- Knowledge graph entities ---
        entities = [
            models.KbEntity(
                id="hours",
                type="Hours",
                name="Hours & Schedule",
                attributes={
                    "open": "7:00 AM",
                    "close": "6:00 PM",
                    "days": "Monday–Friday",
                    "body": "Open Monday through Friday, 7:00 AM–6:00 PM. Closed weekends and major holidays.",
                },
                sources=["2026 Family Handbook p.2 · reviewed by Maria Chen Oct 15, 2025"],
            ),
            models.KbEntity(
                id="tuition-infant",
                type="Tuition",
                name="Infant Tuition",
                attributes={"program": "Infant", "monthly": 1600, "includes": "meals, diapers, wipes"},
                sources=["2026 Family Handbook p.4"],
            ),
            models.KbEntity(
                id="tuition-toddler",
                type="Tuition",
                name="Toddler Tuition",
                attributes={"program": "Toddler", "monthly": 1450, "includes": "meals"},
                sources=["2026 Family Handbook p.4"],
            ),
            models.KbEntity(
                id="tuition-preschool",
                type="Tuition",
                name="Preschool Tuition",
                attributes={"program": "Preschool", "monthly": 1300, "includes": "meals"},
                sources=["2026 Family Handbook p.4"],
            ),
            models.KbEntity(
                id="policy-illness",
                type="Policy",
                name="Illness Policy",
                attributes={
                    "body": "Children with a fever of 100.4°F or higher must stay home until "
                    "they have been fever-free for 24 hours without medication.",
                    "sensitive": True,
                },
                sources=["2026 Family Handbook p.7 · reviewed by Maria Chen Oct 15, 2025"],
            ),
            models.KbEntity(
                id="meals",
                type="Meal",
                name="Meals & Menu",
                attributes={
                    "body": "A fresh lunch and two snacks are served daily, included in tuition. "
                    "Menus rotate weekly and accommodate documented allergies.",
                },
                sources=["2026 Family Handbook p.9"],
            ),
            models.KbEntity(
                id="tours",
                type="Enrollment",
                name="Visits & Tours",
                attributes={"body": "Tours are offered Tuesday and Thursday mornings and can be booked online."},
                sources=["sunnyside.example/tours"],
            ),
            models.KbEntity(
                id="holiday-veterans-day",
                type="Holiday",
                name="Veterans Day",
                attributes={"date": "Nov 11", "status": "closed"},
                sources=["2026 Holiday Calendar"],
            ),
        ]
        db.add_all(entities)
        db.flush()

        # Compute + store embeddings (Titan if creds present, else mock).
        vectors = embed_texts([entity_text(e) for e in entities])
        for e, vec in zip(entities, vectors):
            e.embedding = vec

        # --- Relationships ---
        db.add_all(
            [
                models.KbRelationship(rel="servedBy", src_id="tuition-infant", dst_id="meals"),
                models.KbRelationship(rel="subjectTo", src_id="meals", dst_id="policy-illness"),
                models.KbRelationship(rel="observes", src_id="hours", dst_id="holiday-veterans-day"),
            ]
        )

        # --- Menu (a rotating week, Mon–Fri) ---
        seed_menu_week(db)

        # --- Inbox (inquiries) ---
        db.add_all(
            [
                models.Inquiry(
                    asker_id=p_ava.id, child_id=ava.id,
                    text="My child has a fever — should I keep her home?",
                    status="escalated", category="health",
                ),
                models.Inquiry(
                    text="Do you offer a 3-day / part-time schedule?",
                    status="lowconf", group_key="part-time-schedule",
                ),
                models.Inquiry(
                    asker_id=p_noah.id, child_id=noah.id,
                    text="What are your hours?", status="answered", confidence=0.98,
                ),
                models.Inquiry(
                    text="How much is infant tuition?", status="answered", confidence=0.97,
                ),
                models.Inquiry(
                    asker_id=p_liam.id, child_id=liam.id,
                    text="Are you closed on Veterans Day?", status="answered", confidence=0.95,
                ),
                models.Inquiry(
                    text="Can I book a tour for next Tuesday?", status="answered", confidence=0.9,
                ),
            ]
        )

        # --- Changelog ---
        db.add_all(
            [
                models.ChangelogEntry(
                    actor="Maria Chen", actor_user_id=maria.id, action="Updated Today's Menu",
                    before="PB&J, carrots, milk", after="Turkey & cheese, apple slices, milk", is_diff=True,
                ),
                models.ChangelogEntry(
                    actor="AI Front Desk",
                    action="Escalated a fever question to the Toddler Room staff", is_diff=False,
                ),
                models.ChangelogEntry(
                    actor="Auto-sync", action="Adjusted infant tuition",
                    before="$1,550 / mo", after="$1,600 / mo", is_diff=True, entity_id="tuition-infant",
                ),
                models.ChangelogEntry(
                    actor="Maria Chen", actor_user_id=maria.id,
                    action="Confirmed illness policy — fever 100.4°F, stay home 24h fever-free",
                    is_diff=False, entity_id="policy-illness",
                ),
            ]
        )

        db.commit()
        print("Seed complete: Sunnyside demo data loaded.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
