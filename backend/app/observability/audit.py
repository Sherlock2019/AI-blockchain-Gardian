"""Append-only, hash-chained audit trail.

Each event commits to the one before it, so editing or removing a row in the
middle breaks the chain. This does not stop someone with database access from
rewriting the whole chain: that is what the on-chain receipt anchor is for.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.db import AuditEventRow
from app.models.domain import utc_now_iso
from app.observability.logging import get_correlation_id, log_event, sanitize
from app.security.hashing import ZERO_HASH, hash_object

logger = logging.getLogger("trustchain.audit")


def _event_hash(row: AuditEventRow) -> str:
    return hash_object(
        {
            "timestamp": row.timestamp,
            "correlation_id": row.correlation_id,
            "event_type": row.event_type,
            "actor": row.actor,
            "subject": row.subject,
            "data": row.data,
            "prev_hash": row.prev_hash,
        }
    )


class AuditLog:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, event_type: str, *, actor: str, subject: str, **data: Any) -> AuditEventRow:
        self._session.flush()
        last = self._session.scalars(
            select(AuditEventRow).order_by(AuditEventRow.seq.desc()).limit(1)
        ).first()
        row = AuditEventRow(
            timestamp=utc_now_iso(),
            correlation_id=get_correlation_id(),
            event_type=event_type,
            actor=actor,
            subject=subject,
            data=sanitize(data),
            prev_hash=last.event_hash if last else ZERO_HASH,
            event_hash="",
        )
        row.event_hash = _event_hash(row)
        self._session.add(row)
        self._session.flush()
        log_event(logger, event_type, actor=actor, subject=subject, **data)
        return row

    def list(self, limit: int = 200, correlation_id: str | None = None) -> list[AuditEventRow]:
        query = select(AuditEventRow).order_by(AuditEventRow.seq.desc()).limit(limit)
        if correlation_id:
            query = query.where(AuditEventRow.correlation_id == correlation_id)
        return list(self._session.scalars(query))

    def count(self, event_type: str) -> int:
        return self._session.scalar(
            select(func.count()).select_from(AuditEventRow).where(
                AuditEventRow.event_type == event_type
            )
        ) or 0

    def verify_chain(self) -> dict[str, Any]:
        """Walk the chain and report the first row that does not hold."""
        previous = ZERO_HASH
        count = 0
        for row in self._session.scalars(select(AuditEventRow).order_by(AuditEventRow.seq)):
            count += 1
            if row.prev_hash != previous or row.event_hash != _event_hash(row):
                return {"intact": False, "events": count, "broken_at_seq": row.seq}
            previous = row.event_hash
        return {"intact": True, "events": count, "broken_at_seq": None, "head_hash": previous}
