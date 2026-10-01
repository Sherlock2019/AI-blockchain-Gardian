"""The canonical form of a human approval: what is signed and what is hashed."""

from __future__ import annotations

from typing import Any

from app.models.db import ApprovalRow
from app.security.hashing import hash_object


def signing_payload(row: ApprovalRow) -> dict[str, Any]:
    """Everything the approver is accountable for, including which action they saw."""
    return {
        "approval_id": row.id,
        "action_id": row.action_id,
        "action_hash": row.action_hash,
        "user_id": row.user_id,
        "role": row.role,
        "decision": row.decision,
        "comment": row.comment,
        "timestamp": row.timestamp,
    }


def approval_hash(row: ApprovalRow) -> str:
    return hash_object({**signing_payload(row), "signature": row.signature})
