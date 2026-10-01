"""Metrics derived from the audit trail.

Counting audit events instead of keeping in-process counters means the numbers
survive a restart and cannot drift from the record they summarise.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.db import AuditEventRow, ReceiptRow

# Event type names, shared by the code that emits them.
AGENT_RUN = "AGENT_RUN_COMPLETED"
GOVERNANCE_ALLOW = "GOVERNANCE_ALLOW"
GOVERNANCE_DENY = "GOVERNANCE_DENY"
GOVERNANCE_REQUIRE_APPROVAL = "GOVERNANCE_REQUIRE_APPROVAL"
APPROVAL_GRANTED = "APPROVAL_GRANTED"
APPROVAL_REJECTED = "APPROVAL_REJECTED"
PROMPT_INJECTION_BLOCKED = "PROMPT_INJECTION_BLOCKED"
DUPLICATE_PAYMENT_BLOCKED = "DUPLICATE_PAYMENT_BLOCKED"

_METRIC_EVENTS = {
    "total_agent_requests": AGENT_RUN,
    "actions_allowed": GOVERNANCE_ALLOW,
    "actions_denied": GOVERNANCE_DENY,
    "actions_requiring_approval": GOVERNANCE_REQUIRE_APPROVAL,
    "human_approvals": APPROVAL_GRANTED,
    "human_rejections": APPROVAL_REJECTED,
    "prompt_injection_blocks": PROMPT_INJECTION_BLOCKED,
    "duplicate_payment_blocks": DUPLICATE_PAYMENT_BLOCKED,
}


def collect_metrics(session: Session) -> dict[str, int]:
    counts = dict(
        session.execute(
            select(AuditEventRow.event_type, func.count()).group_by(AuditEventRow.event_type)
        ).all()
    )
    metrics = {name: int(counts.get(event, 0)) for name, event in _METRIC_EVENTS.items()}
    metrics["verified_receipts"] = session.scalar(
        select(func.count()).select_from(ReceiptRow).where(
            ReceiptRow.last_verification == "VERIFIED"
        )
    ) or 0
    return metrics
