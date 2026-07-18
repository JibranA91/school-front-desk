"""Knowledge-hygiene lifecycle: supersession + the deterministic expiry sweep.

Kept independent of app.main (main imports this) to avoid an import cycle, so
entity mutations here go straight through the models. The pluggable detection
engine (Check / CleanupEngine) will also live in this module in a later phase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.config import settings


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _snapshot(e: models.KbEntity) -> dict:
    """Restorable pre-change state for the changelog (mirrors main._entity_state)."""
    return {
        "type": e.type,
        "name": e.name,
        "attributes": dict(e.attributes or {}),
        "sources": list(e.sources or []),
        "enabled": e.enabled,
    }


def restore_superseded(db: Session, override: models.KbEntity, actor: str = "Auto-sync") -> list[str]:
    """Re-enable every node this override disabled (its outgoing `supersedes`
    edges). Call this BEFORE removing an override, so a lapsed temporary fact
    hands control back to the handbook fact it replaced. Logs a revertable entry
    per restored node; does not commit. Returns the restored entity ids."""
    edges = db.scalars(
        select(models.KbRelationship).where(
            models.KbRelationship.rel == "supersedes",
            models.KbRelationship.src_id == override.id,
        )
    ).all()
    restored: list[str] = []
    for edge in edges:
        target = db.get(models.KbEntity, edge.dst_id)
        if target is None or target.enabled:
            continue
        before = _snapshot(target)
        target.enabled = True
        db.add(
            models.ChangelogEntry(
                actor=actor,
                action=f"Re-enabled {target.name} (override '{override.name}' removed)",
                entity_id=target.id,
                is_diff=False,
                snapshot={"entity_id": target.id, "before": before},
            )
        )
        restored.append(target.id)
    return restored


def _remove(db: Session, e: models.KbEntity, actor: str) -> None:
    """Delete an entity + its incident edges; keep changelog history (unlinked);
    log a revertable removal. Self-contained twin of main._delete_entity_cascade
    (avoids importing app.main)."""
    before = _snapshot(e)
    eid, name = e.id, e.name
    db.query(models.KbRelationship).filter(
        (models.KbRelationship.src_id == eid) | (models.KbRelationship.dst_id == eid)
    ).delete(synchronize_session=False)
    db.query(models.ChangelogEntry).filter(
        models.ChangelogEntry.entity_id == eid
    ).update({models.ChangelogEntry.entity_id: None}, synchronize_session=False)
    db.delete(e)
    db.add(
        models.ChangelogEntry(
            actor=actor,
            action=f"Removed expired {name}",
            entity_id=None,
            is_diff=False,
            snapshot={"entity_id": eid, "before": before},
        )
    )


def sweep_expired(db: Session, actor: str = "Auto-sync") -> dict:
    """Deterministically clear expired overrides and restore what they
    superseded. An entity is expired when its `attributes.expires` (ISO date
    string) is before today. Authored/seed expired facts are removed; an expired
    handbook fact is only disabled (handbook is never deleted). Restoration runs
    first, so a lapsed override hands back to the handbook fact it replaced.

    No LLM, no operator round-trip — the operator consented to the date when the
    fact was authored. Runs on startup and before each scan (the seed of the
    future scheduled clean). Returns {"removed": [...], "restored": [...]}."""
    today = today_iso()
    entities = db.scalars(select(models.KbEntity)).all()
    expired = [
        e
        for e in entities
        if isinstance((e.attributes or {}).get("expires"), str)
        and (e.attributes or {})["expires"] < today
    ]
    removed: list[str] = []
    restored: list[str] = []
    for e in expired:
        restored += restore_superseded(db, e, actor=actor)
        if e.id.startswith("hb-"):
            if e.enabled:
                before = _snapshot(e)
                e.enabled = False
                db.add(
                    models.ChangelogEntry(
                        actor=actor,
                        action=f"Disabled expired {e.name}",
                        entity_id=e.id,
                        is_diff=False,
                        snapshot={"entity_id": e.id, "before": before},
                    )
                )
        else:
            _remove(db, e, actor)
        removed.append(e.id)
    if expired:
        db.commit()
    return {"removed": removed, "restored": restored}


# --------------------------------------------------------------------------- #
# Detection engine: pluggable checks over the graph (the "Clean" scan).
#
# Each Check emits a uniform Finding; the CleanupEngine just fans out over a
# registry, so detectors can be added/removed/reordered independently. Quick
# scan runs the deterministic tiers only (this module); the LLM confirmation
# tiers plug in behind the same protocol in a later phase.
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    id: str                 # stable id (kind + entities) so the UI can act/dismiss
    kind: str               # outdated | redundancy | contradiction
    tier: str               # deterministic | llm
    summary: str
    rationale: str
    entities: list[str]
    action: dict            # {"type": none|delete|disable|resolve|merge_needed, ...}
    confidence: float = 1.0

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "tier": self.tier,
            "summary": self.summary,
            "rationale": self.rationale,
            "entities": self.entities,
            "action": self.action,
            "confidence": self.confidence,
        }


_WORD = re.compile(r"[^a-z0-9]+")


def _norm(s: str | None) -> str:
    return _WORD.sub(" ", (s or "").lower()).strip()


def _origin(e: models.KbEntity) -> str:
    if e.id.startswith("hb-"):
        return "handbook"
    if any(str(s).startswith("Set by") for s in (e.sources or [])):
        return "authored"
    return "seed"


def _degrees(db: Session) -> dict[str, int]:
    deg: dict[str, int] = {}
    for r in db.scalars(select(models.KbRelationship)).all():
        deg[r.src_id] = deg.get(r.src_id, 0) + 1
        deg[r.dst_id] = deg.get(r.dst_id, 0) + 1
    return deg


def _neighbors(db: Session, entity_id: str) -> set[str]:
    ns: set[str] = set()
    for r in db.scalars(
        select(models.KbRelationship).where(
            (models.KbRelationship.src_id == entity_id)
            | (models.KbRelationship.dst_id == entity_id)
        )
    ).all():
        ns.add(r.dst_id if r.src_id == entity_id else r.src_id)
    return ns


_ORIGIN_RANK = {"handbook": 0, "seed": 1, "authored": 2}


def _pick_survivor(members: list[models.KbEntity], deg: dict[str, int]) -> models.KbEntity:
    """Which duplicate to KEEP: the most authoritative (handbook is the source of
    record and can never be deleted), then the most-connected, then a stable id
    tiebreak. Operator overrides this in the UI."""
    return sorted(
        members,
        key=lambda e: (_ORIGIN_RANK.get(_origin(e), 3), -deg.get(e.id, 0), e.id),
    )[0]


def _edge_safe(db: Session, remove_id: str, keep_id: str) -> bool:
    """A plain delete of `remove_id` is lossless only if every node it connects
    to is also connected to the survivor — otherwise deleting it would drop a
    real edge, and it needs a (later) merge instead."""
    return (_neighbors(db, remove_id) - {keep_id}) <= _neighbors(db, keep_id)


class OutdatedCheck:
    """Deterministic. Past-due facts are already cleared by sweep_expired (run
    before checks), so this only surfaces *upcoming* expirations as a heads-up —
    no action needed, they auto-remove on their date."""

    key = "outdated"

    def scan(self, db: Session, mode: str, progress=None) -> list[Finding]:
        today = today_iso()
        horizon = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
        out: list[Finding] = []
        for e in db.scalars(select(models.KbEntity)).all():
            exp = (e.attributes or {}).get("expires")
            if isinstance(exp, str) and today <= exp <= horizon:
                out.append(
                    Finding(
                        id=f"outdated:{e.id}",
                        kind="outdated",
                        tier="deterministic",
                        summary=f"'{e.name}' expires {exp}",
                        rationale=f"Temporary fact (expires={exp}); auto-removes on/after that date.",
                        entities=[e.id],
                        action={"type": "none"},
                    )
                )
        return out


class RedundancyCheck:
    """Deterministic tier: entities with an identical normalized name OR identical
    body are true duplicates. (Near-duplicate detection via embeddings is the LLM
    tier, added later.) Keeps the survivor; proposes delete only when lossless,
    disable when the duplicate is a handbook fact, else flags merge-needed."""

    key = "redundancy"

    def scan(self, db: Session, mode: str, progress=None) -> list[Finding]:
        ents = [e for e in db.scalars(select(models.KbEntity)).all() if e.enabled]
        deg = _degrees(db)
        groups: dict[tuple[str, str], list[models.KbEntity]] = {}
        for e in ents:
            keys = {("name", _norm(e.name))}
            body = (e.attributes or {}).get("body")
            if isinstance(body, str) and body.strip():
                keys.add(("body", _norm(body)))
            for k in keys:
                groups.setdefault(k, []).append(e)

        out: list[Finding] = []
        emitted: set[tuple[str, ...]] = set()
        for (basis, _val), members in groups.items():
            if len(members) < 2:
                continue
            key = tuple(sorted(m.id for m in members))
            if key in emitted:
                continue
            emitted.add(key)
            survivor = _pick_survivor(members, deg)
            for m in members:
                if m.id == survivor.id:
                    continue
                action = _redundancy_action(db, m, survivor)
                out.append(
                    Finding(
                        id=f"redundancy:{m.id}->{survivor.id}",
                        kind="redundancy",
                        tier="deterministic",
                        summary=f"'{m.name}' duplicates '{survivor.name}'",
                        rationale=f"Identical {basis}. Keep '{survivor.id}' ({_origin(survivor)}); "
                        f"{action['type'].replace('_', ' ')} '{m.id}'.",
                        entities=[m.id, survivor.id],
                        action=action,
                    )
                )
        return out


class ContradictionCheck:
    """Deterministic tier: two same-type entities on the same topic (normalized
    name) whose shared attribute keys hold different non-empty values. (Semantic
    contradictions across differently-keyed facts are the LLM tier, added later.)"""

    key = "contradiction"

    def scan(self, db: Session, mode: str, progress=None) -> list[Finding]:
        ents = [e for e in db.scalars(select(models.KbEntity)).all() if e.enabled]
        buckets: dict[tuple[str, str], list[models.KbEntity]] = {}
        for e in ents:
            buckets.setdefault((e.type, _norm(e.name)), []).append(e)

        out: list[Finding] = []
        for members in buckets.values():
            if len(members) < 2:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    aa, ba = (a.attributes or {}), (b.attributes or {})
                    shared = (set(aa) & set(ba)) - {"body"}
                    diffs = [
                        k
                        for k in shared
                        if str(aa[k]) != str(ba[k])
                        and aa[k] not in (None, "")
                        and ba[k] not in (None, "")
                    ]
                    if not diffs:
                        continue
                    out.append(
                        Finding(
                            id=f"contradiction:{'+'.join(sorted([a.id, b.id]))}",
                            kind="contradiction",
                            tier="deterministic",
                            summary=f"'{a.name}' and '{b.name}' disagree on {', '.join(diffs)}",
                            rationale="; ".join(f"{k}: {aa[k]} vs {ba[k]}" for k in diffs),
                            entities=[a.id, b.id],
                            action={"type": "resolve", "entities": [a.id, b.id]},
                        )
                    )
        return out


def _redundancy_action(db: Session, remove: models.KbEntity, survivor: models.KbEntity) -> dict:
    """How to resolve a duplicate: a handbook fact is never deleted (disable it);
    delete only when lossless; otherwise it needs a (later) merge."""
    if _origin(remove) == "handbook":
        return {"type": "disable", "entity_id": remove.id, "keep": survivor.id}
    if _edge_safe(db, remove.id, survivor.id):
        return {"type": "delete", "entity_id": remove.id, "keep": survivor.id}
    return {"type": "merge_needed", "entity_id": remove.id, "keep": survivor.id}


def _blurb(e: models.KbEntity) -> str:
    attrs = e.attributes or {}
    body = attrs.get("body")
    if isinstance(body, str) and body.strip():
        return body.strip()[:220]
    facts = "; ".join(f"{k}={v}" for k, v in attrs.items() if k != "body" and v not in (None, ""))
    return facts[:220] or e.name


def _near_pairs(db: Session, max_dist: float, limit: int) -> list[tuple[str, str, float]]:
    """Candidate near-neighbour pairs via pgvector kNN (the same `<=>` operator
    link_similar uses). Each unordered pair once (b.id > a.id), only enabled +
    embedded nodes, within max_dist cosine distance, closest first. No LLM."""
    rows = db.execute(
        text(
            """
            SELECT a.id AS a, nn.id AS b, nn.dist AS dist
            FROM kb_entities a
            JOIN LATERAL (
                SELECT b.id, a.embedding <=> b.embedding AS dist
                FROM kb_entities b
                WHERE b.id > a.id AND b.embedding IS NOT NULL AND b.enabled
                ORDER BY a.embedding <=> b.embedding
                LIMIT 4
            ) nn ON true
            WHERE a.embedding IS NOT NULL AND a.enabled AND nn.dist <= :max_dist
            ORDER BY nn.dist
            LIMIT :limit
            """
        ),
        {"max_dist": max_dist, "limit": limit},
    ).all()
    return [(r.a, r.b, float(r.dist)) for r in rows]


def _classify_pairs(db: Session, pairs: list[tuple[str, str, float]], progress=None) -> dict[int, tuple[str, str]]:
    """LLM-classify each candidate pair as duplicate / contradiction / distinct.
    Runs in SMALL batches — a large structured-output list is unreliable (the
    tool-call response truncates and fails to parse past ~10 items), so we chunk
    and merge. Each batch is best-effort: a failed batch is logged and skipped,
    not fatal. Returns {pair_index: (relation, reason)}."""
    from typing import Literal as _Lit

    from pydantic import BaseModel, Field

    from app.llm import get_chat_model

    ids = {i for p in pairs for i in (p[0], p[1])}
    ents = {
        e.id: e
        for e in db.scalars(select(models.KbEntity).where(models.KbEntity.id.in_(ids))).all()
    }

    class Verdict(BaseModel):
        index: int
        relation: _Lit["duplicate", "contradiction", "distinct"]
        reason: str = Field(description="One short clause.")

    class Verdicts(BaseModel):
        verdicts: list[Verdict]

    preamble = (
        "You audit a childcare center's knowledge base for hygiene. For each "
        "numbered pair of facts, classify the relationship:\n"
        "- duplicate: they state the SAME fact (one is redundant), even if worded "
        "differently.\n"
        "- contradiction: same topic but CONFLICTING information.\n"
        "- distinct: legitimately different facts (most pairs).\n"
        "Be conservative — only say duplicate/contradiction when clear. Give a "
        "verdict for EVERY index.\n\nPAIRS:\n"
    )
    model = get_chat_model(settings.chat_model, temperature=0).with_structured_output(Verdicts)

    out: dict[int, tuple[str, str]] = {}
    CHUNK = 8
    for start in range(0, len(pairs), CHUNK):
        lines = []
        for i in range(start, min(start + CHUNK, len(pairs))):
            a, b, _d = pairs[i]
            ea, eb = ents.get(a), ents.get(b)
            if ea is None or eb is None:
                continue
            lines.append(f"[{i}] A = {ea.name}: {_blurb(ea)}\n     B = {eb.name}: {_blurb(eb)}")
        if not lines:
            continue
        try:
            result = model.invoke(preamble + "\n".join(lines))
            for v in result.verdicts:
                out[v.index] = (v.relation, v.reason)
        except Exception as exc:  # noqa: BLE001
            print(f"[cleanup] pair-classify batch @{start} failed: {exc}")
        if progress:
            progress(f"AI review — confirmed {min(start + CHUNK, len(pairs))} / {len(pairs)} pairs…")
    return out


class LlmPairCheck:
    """Deep tier: pgvector kNN proposes near-neighbour candidate pairs, then ONE
    batched LLM call confirms duplicates / contradictions the deterministic tiers
    (identical text, shared-field conflicts) can't catch. No-op in Quick mode, or
    when embeddings / the LLM are off."""

    key = "AI review"

    def scan(self, db: Session, mode: str, progress=None) -> list[Finding]:
        if mode != "deep" or not settings.llm_enabled or not settings.embeddings_enabled:
            return []
        if progress:
            progress("AI review — finding near-duplicate candidates…")
        pairs = _near_pairs(db, max_dist=0.30, limit=40)
        if not pairs:
            return []
        if progress:
            progress(f"AI review — {len(pairs)} candidate pairs to confirm…")
        verdicts = _classify_pairs(db, pairs, progress)
        deg = _degrees(db)
        out: list[Finding] = []
        for i, (a, b, dist) in enumerate(pairs):
            rel, reason = verdicts.get(i, ("distinct", ""))
            if rel == "distinct":
                continue
            ea, eb = db.get(models.KbEntity, a), db.get(models.KbEntity, b)
            if ea is None or eb is None:
                continue
            conf = round(max(0.5, 1.0 - dist), 2)
            if rel == "duplicate":
                survivor = _pick_survivor([ea, eb], deg)
                remove = eb if survivor.id == ea.id else ea
                out.append(
                    Finding(
                        id=f"redundancy:{remove.id}->{survivor.id}",
                        kind="redundancy",
                        tier="llm",
                        summary=f"'{remove.name}' looks like a duplicate of '{survivor.name}'",
                        rationale=(reason or "Judged to state the same fact.")
                        + f" Keep '{survivor.id}' ({_origin(survivor)}).",
                        entities=[remove.id, survivor.id],
                        action=_redundancy_action(db, remove, survivor),
                        confidence=conf,
                    )
                )
            elif rel == "contradiction":
                out.append(
                    Finding(
                        id=f"contradiction:{'+'.join(sorted([a, b]))}",
                        kind="contradiction",
                        tier="llm",
                        summary=f"'{ea.name}' and '{eb.name}' may conflict",
                        rationale=reason or "Judged to give conflicting information.",
                        entities=[a, b],
                        action={"type": "resolve", "entities": [a, b]},
                        confidence=conf,
                    )
                )
        return out


class CleanupEngine:
    """Runs the registered checks and returns their findings. Add/remove/reorder
    checks here without touching the job, the API, or the UI."""

    def __init__(self, checks: list | None = None):
        self.checks = checks or [
            OutdatedCheck(),
            RedundancyCheck(),
            ContradictionCheck(),
            LlmPairCheck(),
        ]

    def scan(self, db: Session, mode: str = "quick", progress=None) -> dict:
        # Deterministic expiry is handled first (past-due auto-removed + restored),
        # so the reported findings are the judgment calls (dups, contradictions).
        swept = sweep_expired(db)
        findings: list[dict] = []
        total = len(self.checks)
        for i, check in enumerate(self.checks):
            if progress:
                progress(f"Checking {check.key}… ({i + 1}/{total})")
            findings.extend(f.as_dict() for f in check.scan(db, mode, progress))
        # De-dupe by finding id — a pair can surface from both a deterministic and
        # the LLM tier; the earlier (deterministic) one wins.
        seen: set[str] = set()
        unique = [f for f in findings if not (f["id"] in seen or seen.add(f["id"]))]
        return {"mode": mode, "swept": swept, "findings": unique}
