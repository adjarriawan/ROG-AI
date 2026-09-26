"""Global knowledge base: facts learned from conversation, reusable anywhere.

Unlike `documents`, these are not uploaded files - they are short statements
the agent proposed or a human entered. They are global on purpose: the point is
that something learned in one session is available in every other one.

The write path is deliberately two-step. The agent may only create 'pending'
rows; nothing is searchable until a human approves it. With no auth in front of
this app, a self-publishing agent would let one hostile prompt rewrite what
every future session believes.
"""

import logging
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from config import get_settings
from database import SessionLocal
from models import KnowledgeFact  # re-exported: main.py builds the export query
from services.embedding_service import embed_query

log = logging.getLogger("agentic_rag.knowledge")

MIN_LENGTH = 10
MAX_LENGTH = 2000

STATUSES = ("pending", "approved", "rejected")


class Fact(TypedDict):
    """An approved fact as the search tool reports it."""

    id: int
    content: str
    distance: float


class InvalidFact(ValueError):
    """The text is not usable as a fact."""


def normalise(content: str) -> str:
    """Collapse whitespace, the same way document chunks are cleaned."""
    return " ".join(content.split())


def _validate(content: str) -> str:
    cleaned = normalise(content)
    if len(cleaned) < MIN_LENGTH:
        raise InvalidFact(f"Fakta terlalu pendek (minimal {MIN_LENGTH} karakter).")
    if len(cleaned) > MAX_LENGTH:
        raise InvalidFact(f"Fakta terlalu panjang (maksimal {MAX_LENGTH} karakter).")
    return cleaned


def propose(db: Session, content: str, session_id: str | None) -> int | None:
    """Record a candidate fact. Returns its id, or None if already known.

    Not embedded here: pending rows are never searched, and most of them are
    cheap duplicates of something already proposed.
    """
    cleaned = _validate(content)
    row = db.execute(
        text(
            """
            INSERT INTO knowledge_facts (content, status, origin, source_session_id)
            VALUES (:c, 'pending', 'agent', :s)
            ON CONFLICT (lower(content)) DO NOTHING
            RETURNING id
            """
        ),
        {"c": cleaned, "s": session_id},
    ).scalar_one_or_none()
    db.commit()
    if row is None:
        log.info("fact already known, not re-proposed")
    return row


def add_verified(db: Session, content: str) -> KnowledgeFact:
    """A human adds a fact directly - approved, and embedded immediately."""
    cleaned = _validate(content)
    existing = db.execute(
        select(KnowledgeFact).where(
            text("lower(knowledge_facts.content) = lower(:c)").bindparams(c=cleaned)
        )
    ).scalar_one_or_none()
    fact = existing or KnowledgeFact(content=cleaned)
    fact.content = cleaned
    fact.origin = "human"
    fact.status = "approved"
    fact.embedding = embed_query(cleaned)
    fact.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


def set_status(db: Session, fact_id: int, status: str) -> KnowledgeFact | None:
    """Approve or reject. Approving embeds the text a human has just read."""
    if status not in STATUSES:
        raise InvalidFact(f"Status tidak dikenal: {status}")
    fact = db.get(KnowledgeFact, fact_id)
    if fact is None:
        return None
    fact.status = status
    fact.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    if status == "approved" and fact.embedding is None:
        fact.embedding = embed_query(fact.content)
    db.commit()
    db.refresh(fact)
    log.info("fact %d -> %s", fact_id, status)
    return fact


def delete(db: Session, fact_id: int) -> bool:
    fact = db.get(KnowledgeFact, fact_id)
    if fact is None:
        return False
    db.delete(fact)
    db.commit()
    return True


def listing(db: Session, status: str | None, limit: int) -> list[KnowledgeFact]:
    stmt = select(KnowledgeFact).order_by(KnowledgeFact.created_at.desc()).limit(limit)
    if status:
        if status not in STATUSES:
            raise InvalidFact(f"Status tidak dikenal: {status}")
        stmt = stmt.where(KnowledgeFact.status == status)
    return list(db.execute(stmt).scalars().all())


def search(query: str, k: int | None = None) -> list[Fact]:
    """Nearest approved facts. Pending and rejected rows are unreachable here."""
    s = get_settings()
    vector = embed_query(query)
    with SessionLocal() as db:
        rows = db.execute(
            text(
                """
                SELECT id, content,
                       embedding <=> CAST(:q AS vector) AS distance
                FROM knowledge_facts
                WHERE status = 'approved' AND embedding IS NOT NULL
                ORDER BY distance
                LIMIT :k
                """
            ),
            {"q": str(vector), "k": k or s.knowledge_top_k},
        ).all()
    return [
        Fact(id=r.id, content=r.content, distance=round(float(r.distance), 4))
        for r in rows
        if r.distance <= s.knowledge_max_distance
    ]
