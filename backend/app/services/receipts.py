"""Execution receipts: creation, hashing, anchoring and verification."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.blockchain.ledger import LedgerClient
from app.errors import ConflictError, LedgerRejectedError, LedgerUnavailableError, NotFoundError
from app.models.db import ActionRow, ApprovalRow, ReceiptRow
from app.models.domain import (
    GovernanceDecision,
    PaymentResult,
    Principal,
    PrincipalKind,
    new_id,
    utc_now_iso,
)
from app.observability.audit import AuditLog
from app.security.hashing import ZERO_HASH, hash_object, id_hash, money_str
from app.services.approvals import approval_hash

ANCHORED = "ANCHORED"
PENDING = "PENDING"
REJECTED = "REJECTED"

VERIFIED = "VERIFIED"
TAMPER_DETECTED = "TAMPER_DETECTED"
NOT_ANCHORED = "NOT_ANCHORED"
LEDGER_UNAVAILABLE = "LEDGER_UNAVAILABLE"


def compute_receipt_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of every receipt field.

    `receipt_hash` and `blockchain_tx_hash` are not part of the payload: the
    first is this value, the second only exists after the hash is on-chain.
    """
    return hash_object(payload)


class ReceiptService:
    def __init__(self, session: Session, ledger: LedgerClient, audit: AuditLog) -> None:
        self._session = session
        self._ledger = ledger
        self._audit = audit

    # ------------------------------------------------------------- creation

    def create(
        self,
        *,
        action: ActionRow,
        principal: Principal,
        decision: GovernanceDecision,
        approval: ApprovalRow | None,
        payment: PaymentResult,
        permission: str,
        tool: str,
        model_provider: str,
        model_name: str,
    ) -> ReceiptRow:
        previous = self._session.scalars(
            select(ReceiptRow).order_by(ReceiptRow.seq.desc()).limit(1)
        ).first()
        is_agent = principal.kind is PrincipalKind.AGENT
        payload: dict[str, Any] = {
            "receipt_id": new_id("RCP"),
            "action_id": action.id,
            "action_hash": action.action_hash,
            "agent_id": principal.id if is_agent else None,
            "agent_version": principal.version if is_agent else None,
            "requested_by": principal.id,
            "origin": action.origin,
            "model_provider": model_provider,
            "model_name": model_name,
            "policy_version": decision.policy_version,
            "policy_hash": decision.policy_hash,
            "invoice_id": action.invoice_id,
            "supplier_id": action.supplier_id,
            "purchase_order_id": action.purchase_order_id,
            "retrieved_source_ids": list(action.evidence_ids),
            "requested_action": action.action_type,
            "permission_used": permission,
            "amount": money_str(payment.amount),
            "risk_level": decision.risk_level.value,
            "governance_decision": decision.decision.value,
            "governance_decision_id": decision.decision_id,
            "human_approval_id": approval.id if approval else None,
            "human_approval_role": approval.role if approval else None,
            "approval_hash": approval_hash(approval) if approval else None,
            "tool_executed": tool,
            "execution_result": {
                "transaction_id": payment.transaction_id,
                "status": payment.status,
            },
            "timestamp": utc_now_iso(),
            "previous_receipt_hash": previous.receipt_hash if previous else ZERO_HASH,
        }
        row = ReceiptRow(
            receipt_id=payload["receipt_id"],
            action_id=action.id,
            action_hash=action.action_hash,
            payload=payload,
            receipt_hash=compute_receipt_hash(payload),
            anchor_status=PENDING,
        )
        self._session.add(row)
        self._session.flush()
        self._audit.record(
            "RECEIPT_CREATED",
            actor=principal.id,
            subject=row.receipt_id,
            receipt_hash=row.receipt_hash,
            action_id=action.id,
        )
        return row

    def get(self, receipt_id: str) -> ReceiptRow:
        row = self._session.scalars(
            select(ReceiptRow).where(ReceiptRow.receipt_id == receipt_id)
        ).first()
        if row is None:
            raise NotFoundError(f"Receipt {receipt_id} not found.")
        return row

    # ------------------------------------------------------------- anchoring

    def anchor(self, row: ReceiptRow) -> ReceiptRow:
        """Writes the receipt hash to the ledger. Safe to call again after a failure.

        Never raises for a ledger problem: the payment has already happened, so
        the receipt stays PENDING and is retried later.
        """
        if row.anchor_status == ANCHORED:
            return row
        payload = row.payload
        approval = payload.get("approval_hash") or ZERO_HASH
        try:
            existing = self._ledger.get_execution(row.action_hash)
            if existing is not None:
                # A previous attempt reached the chain but its response was lost.
                if existing.receipt_hash != row.receipt_hash:
                    raise LedgerRejectedError(
                        "A different receipt hash is already recorded for this action."
                    )
                row.block_number = existing.block_number
            else:
                if approval != ZERO_HASH and self._ledger.get_approval_hash(row.action_hash) is None:
                    self._ledger.record_approval(
                        row.action_hash,
                        approval,
                        id_hash("role", payload.get("human_approval_role") or ""),
                    )
                agent_id = payload.get("agent_id")
                ref = self._ledger.record_execution(
                    action_hash=row.action_hash,
                    agent_hash=id_hash("agent", agent_id) if agent_id else ZERO_HASH,
                    permission_hash=id_hash("permission", payload["permission_used"]),
                    policy_hash=payload["policy_hash"],
                    approval_hash=approval,
                    receipt_hash=row.receipt_hash,
                    success=payload["execution_result"]["status"] == "SUCCESS",
                )
                row.blockchain_tx_hash = ref.tx_hash
                row.block_number = ref.block_number
            row.anchor_status = ANCHORED
            row.anchor_error = None
            self._audit.record(
                "RECEIPT_ANCHORED",
                actor="system",
                subject=row.receipt_id,
                tx_hash=row.blockchain_tx_hash,
                block_number=row.block_number,
            )
        except LedgerUnavailableError as exc:
            row.anchor_status = PENDING
            row.anchor_error = exc.message
            self._audit.record(
                "RECEIPT_ANCHOR_DEFERRED", actor="system", subject=row.receipt_id, error=exc.message
            )
        except LedgerRejectedError as exc:
            row.anchor_status = REJECTED
            row.anchor_error = exc.message
            self._audit.record(
                "RECEIPT_ANCHOR_REJECTED", actor="system", subject=row.receipt_id, error=exc.message
            )
        self._session.commit()
        return row

    # ---------------------------------------------------------- verification

    def verify(self, receipt_id: str) -> dict[str, Any]:
        row = self.get(receipt_id)
        recomputed = compute_receipt_hash(row.payload)
        local_match = recomputed == row.receipt_hash
        details: list[str] = []
        if not local_match:
            details.append("Recomputed hash differs from the hash stored with the receipt.")

        previous = self._session.scalars(
            select(ReceiptRow).where(ReceiptRow.seq < row.seq).order_by(ReceiptRow.seq.desc()).limit(1)
        ).first()
        expected_previous = previous.receipt_hash if previous else ZERO_HASH
        chain_link_ok = row.payload.get("previous_receipt_hash") == expected_previous
        if not chain_link_ok:
            details.append("The preceding receipt no longer matches the hash this receipt links to.")

        onchain_hash: str | None = None
        block_number: int | None = None
        chain_match: bool | None = None
        info = self._ledger.info()
        try:
            record = self._ledger.get_execution(row.action_hash)
        except LedgerUnavailableError as exc:
            status = TAMPER_DETECTED if not local_match else LEDGER_UNAVAILABLE
            details.append(exc.message)
        else:
            if record is None:
                status = TAMPER_DETECTED if not local_match else NOT_ANCHORED
                details.append("No record exists on the ledger for this action.")
            else:
                onchain_hash = record.receipt_hash
                block_number = record.block_number
                chain_match = onchain_hash == recomputed
                if chain_match and local_match:
                    status = VERIFIED
                    details.append("Recomputed hash equals the hash recorded on the ledger.")
                else:
                    status = TAMPER_DETECTED
                    if not chain_match:
                        details.append("Recomputed hash differs from the hash recorded on the ledger.")

        row.last_verification = status
        self._audit.record(
            "RECEIPT_VERIFIED",
            actor="system",
            subject=row.receipt_id,
            status=status,
            recomputed_hash=recomputed,
            onchain_hash=onchain_hash,
        )
        self._session.commit()
        return {
            "receipt_id": row.receipt_id,
            "status": status,
            "recomputed_hash": recomputed,
            "stored_hash": row.receipt_hash,
            "onchain_hash": onchain_hash,
            "local_match": local_match,
            "chain_match": chain_match,
            "chain_link_ok": chain_link_ok,
            "block_number": block_number,
            "blockchain_tx_hash": row.blockchain_tx_hash,
            "contract_address": info.contract_address,
            "ledger_mode": info.mode,
            "checked_at": utc_now_iso(),
            "details": details,
        }

    # ------------------------------------------------------------- demo only

    def tamper(self, receipt_id: str, *, recompute_hash: bool) -> ReceiptRow:
        """Simulates someone with database access inflating the amount tenfold.

        With `recompute_hash` the attacker also rewrites the stored hash, so
        the record is internally consistent and only the ledger disagrees.
        """
        row = self.get(receipt_id)
        if row.demo_backup is not None:
            raise ConflictError("Receipt is already tampered. Restore it first.")
        row.demo_backup = {"payload": row.payload, "receipt_hash": row.receipt_hash}
        payload = dict(row.payload)
        payload["amount"] = money_str(Decimal(payload["amount"]) * 10)
        row.payload = payload
        if recompute_hash:
            row.receipt_hash = compute_receipt_hash(payload)
        row.last_verification = None
        self._audit.record(
            "DEMO_RECEIPT_TAMPERED",
            actor="demo",
            subject=row.receipt_id,
            recompute_hash=recompute_hash,
        )
        self._session.commit()
        return row

    def restore(self, receipt_id: str) -> ReceiptRow:
        row = self.get(receipt_id)
        if row.demo_backup is None:
            raise ConflictError("Receipt has not been tampered with.")
        row.payload = row.demo_backup["payload"]
        row.receipt_hash = row.demo_backup["receipt_hash"]
        row.demo_backup = None
        row.last_verification = None
        self._audit.record("DEMO_RECEIPT_RESTORED", actor="demo", subject=row.receipt_id)
        self._session.commit()
        return row
