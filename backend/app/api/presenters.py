"""Maps rows to the JSON the dashboard consumes. No decisions are made here."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db import (
    ActionRow,
    AgentRunRow,
    ApprovalRow,
    AuditEventRow,
    ContractRow,
    InvoiceRow,
    PurchaseOrderRow,
    ReceiptRow,
    SupplierRow,
    UserRow,
)
from app.models.domain import ActionStatus
from app.security.hashing import money_str


def user(row: UserRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "role": row.role,
        "approval_limit": money_str(row.approval_limit),
    }


def invoice(row: InvoiceRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "supplier_id": row.supplier_id,
        "purchase_order_id": row.purchase_order_id,
        "amount": money_str(row.amount),
        "description": row.description,
        "notes": row.notes,
        "status": row.status,
        "scenario": row.scenario,
    }


def supplier(row: SupplierRow | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "risk": row.risk,
        "payment_limit": money_str(row.payment_limit),
        "account_token": row.account_token,
    }


def purchase_order(row: PurchaseOrderRow | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "supplier_id": row.supplier_id,
        "approved_amount": money_str(row.approved_amount),
        "description": row.description,
        "status": row.status,
    }


def contract(row: ContractRow | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"id": row.id, "title": row.title, "terms": row.terms}


def approval(row: ApprovalRow | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "approval_id": row.id,
        "user_id": row.user_id,
        "role": row.role,
        "decision": row.decision,
        "timestamp": row.timestamp,
        "comment": row.comment,
        "digital_signature_mock": row.signature,
    }


def receipt(row: ReceiptRow) -> dict[str, Any]:
    return {
        **row.payload,
        "receipt_hash": row.receipt_hash,
        "blockchain_tx_hash": row.blockchain_tx_hash,
        "block_number": row.block_number,
        "anchor_status": row.anchor_status,
        "anchor_error": row.anchor_error,
        "last_verification": row.last_verification,
        "tampered_in_demo": row.demo_backup is not None,
    }


def action(session: Session, row: ActionRow) -> dict[str, Any]:
    approval_row = session.scalars(
        select(ApprovalRow).where(ApprovalRow.action_id == row.id)
    ).first()
    receipt_row = session.scalars(
        select(ReceiptRow).where(ReceiptRow.action_id == row.id)
    ).first()
    return {
        "id": row.id,
        "action_hash": row.action_hash,
        "correlation_id": row.correlation_id,
        "origin": row.origin,
        "principal_kind": row.principal_kind,
        "principal_id": row.principal_id,
        "action_type": row.action_type,
        "invoice_id": row.invoice_id,
        "supplier_id": row.supplier_id,
        "purchase_order_id": row.purchase_order_id,
        "amount": money_str(row.amount) if row.amount is not None else None,
        "params": row.params,
        "evidence_ids": row.evidence_ids,
        "recommendation": row.recommendation,
        "run_id": row.run_id,
        "status": row.status,
        "decision": row.decision,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "approval": approval(approval_row),
        "receipt_id": receipt_row.receipt_id if receipt_row else None,
    }


def actions_for(session: Session, **filters: Any) -> list[dict[str, Any]]:
    query = select(ActionRow).filter_by(**filters).order_by(ActionRow.created_at.desc())
    return [action(session, row) for row in session.scalars(query)]


def audit_event(row: AuditEventRow) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "timestamp": row.timestamp,
        "correlation_id": row.correlation_id,
        "event_type": row.event_type,
        "actor": row.actor,
        "subject": row.subject,
        "data": row.data,
        "event_hash": row.event_hash,
    }


def _stage(stage: str, title: str, detail: str, status: str) -> dict[str, str]:
    return {"stage": stage, "title": title, "detail": detail, "status": status}


def timeline(analysis: dict[str, Any], actions: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Observe → Verify for one agent run, derived from stored state."""
    steps = [
        _stage(t["stage"], t["title"], t["detail"], t["status"]) for t in analysis.get("trace", [])
    ]
    if not actions:
        return steps

    denied = [a for a in actions if a["status"] == ActionStatus.DENIED]
    payment = next((a for a in actions if a["action_type"] == "PAY_SUPPLIER"), actions[0])
    decision = payment.get("decision") or {}
    focus = denied[0] if denied else payment
    focus_decision = focus.get("decision") or {}
    steps.append(
        _stage(
            "GOVERNANCE",
            f"{focus['action_type']}: {focus_decision.get('decision', 'PENDING')}",
            " ".join(focus_decision.get("reasons", [])),
            "BLOCKED" if denied else "DONE",
        )
    )

    status = payment["status"]
    approval_row = payment.get("approval")
    if status == ActionStatus.DENIED:
        approval_step = _stage("APPROVAL", "Not reached", "The request was denied.", "SKIPPED")
    elif approval_row:
        approval_step = _stage(
            "APPROVAL",
            f"{approval_row['decision']} by {approval_row['user_id']}",
            approval_row["comment"] or f"Role {approval_row['role']}.",
            "DONE" if approval_row["decision"] == "APPROVED" else "BLOCKED",
        )
    elif status == ActionStatus.PENDING_APPROVAL:
        approval_step = _stage(
            "APPROVAL",
            f"Waiting for {decision.get('required_approval')}",
            "A human with sufficient authority must decide.",
            "PENDING",
        )
    else:
        approval_step = _stage(
            "APPROVAL", "Not required", "Within the autonomous limit.", "SKIPPED"
        )
    steps.append(approval_step)

    executed = status == ActionStatus.EXECUTED
    waiting = status in (ActionStatus.PENDING_APPROVAL, ActionStatus.AUTHORIZED)
    steps.append(
        _stage(
            "EXECUTE",
            "Mock payment executed" if executed else "Not executed",
            payment.get("last_error") or ("Receipt created." if executed else f"Status {status}."),
            "DONE" if executed else ("PENDING" if waiting else "SKIPPED"),
        )
    )
    steps.append(
        _stage(
            "VERIFY",
            "Receipt " + (payment["receipt_id"] or "not created"),
            "Open the receipt to verify it against the ledger." if executed else "Nothing to verify.",
            "DONE" if executed else "SKIPPED",
        )
    )
    return steps


def agent_run(session: Session, row: AgentRunRow) -> dict[str, Any]:
    actions = actions_for(session, run_id=row.id)
    actions.reverse()
    analysis = {k: v for k, v in row.analysis.items() if k not in ("proposed_actions", "trace")}
    return {
        **analysis,
        "correlation_id": row.correlation_id,
        "requested_by": row.requested_by,
        "created_at": row.created_at,
        "actions": actions,
        "timeline": timeline(row.analysis, actions),
    }
