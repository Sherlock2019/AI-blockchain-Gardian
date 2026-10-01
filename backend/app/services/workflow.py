"""The payment workflow: the only code path that can execute an action.

AI-originated and human-originated requests enter through `submit` and are
indistinguishable from there on. Nothing in this module consults a model.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.blockchain.ledger import LedgerClient
from app.errors import (
    ConflictError,
    DuplicatePaymentError,
    ForbiddenError,
    LedgerUnavailableError,
    NotFoundError,
)
from app.governance.approval import Approver
from app.governance.engine import GovernanceEngine
from app.governance.facts import FactLoader
from app.models.db import ActionRow, AgentRunRow, ApprovalRow, InvoiceRow, ReceiptRow, UserRow
from app.models.domain import (
    PAY_SUPPLIER,
    ActionStatus,
    Decision,
    Facts,
    GovernanceDecision,
    Origin,
    PrincipalKind,
    ProposedAction,
    Recommendation,
    dump,
    new_id,
    utc_now_iso,
)
from app.observability import metrics
from app.observability.audit import AuditLog
from app.observability.logging import get_correlation_id, log_event
from app.security.hashing import id_hash
from app.security.signing import ApprovalSigner
from app.services.approvals import signing_payload
from app.services.payment import MockPaymentService
from app.services.receipts import ReceiptService

logger = logging.getLogger("trustchain.workflow")

PAYMENT_TOOL = "MockPaymentService.execute_payment"
_DECISION_EVENTS = {
    Decision.ALLOW: metrics.GOVERNANCE_ALLOW,
    Decision.REQUIRE_APPROVAL: metrics.GOVERNANCE_REQUIRE_APPROVAL,
    Decision.DENY: metrics.GOVERNANCE_DENY,
}
_STATUS_FOR = {
    Decision.ALLOW: ActionStatus.AUTHORIZED,
    Decision.REQUIRE_APPROVAL: ActionStatus.PENDING_APPROVAL,
    Decision.DENY: ActionStatus.DENIED,
}


def to_domain(row: ActionRow) -> ProposedAction:
    return ProposedAction(
        action_id=row.id,
        action_type=row.action_type,
        principal_kind=PrincipalKind(row.principal_kind),
        principal_id=row.principal_id,
        origin=Origin(row.origin),
        invoice_id=row.invoice_id,
        supplier_id=row.supplier_id,
        purchase_order_id=row.purchase_order_id,
        amount=row.amount,
        params=dict(row.params or {}),
        evidence_ids=tuple(row.evidence_ids or ()),
        recommendation=Recommendation(row.recommendation) if row.recommendation else None,
        run_id=row.run_id,
    )


class PaymentWorkflow:
    def __init__(
        self,
        session: Session,
        governance: GovernanceEngine,
        facts: FactLoader,
        payments: MockPaymentService,
        receipts: ReceiptService,
        ledger: LedgerClient,
        audit: AuditLog,
        signer: ApprovalSigner,
    ) -> None:
        self._session = session
        self._governance = governance
        self._facts = facts
        self._payments = payments
        self._receipts = receipts
        self._ledger = ledger
        self._audit = audit
        self._signer = signer

    # ---------------------------------------------------------------- submit

    def submit(self, actions: Sequence[ProposedAction]) -> list[ActionRow]:
        """Evaluates each request and executes those that need no approval."""
        if not actions:
            return []

        # First pass, no side effects: did this batch ask for anything outside
        # the requester's scope? If so the whole batch is treated as compromised.
        probes = [(a, self._facts.load(a)) for a in actions]
        out_of_scope = [
            a for a, f in probes if self._governance.evaluate(a, f).permission_denied
        ]
        compromised = any(a.origin is Origin.AI for a in out_of_scope)
        if compromised:
            flagged = any(f.untrusted_content_flagged for _, f in probes)
            self._audit.record(
                metrics.PROMPT_INJECTION_BLOCKED if flagged else "OUT_OF_SCOPE_REQUEST_BLOCKED",
                actor=actions[0].principal_id,
                subject=actions[0].run_id or actions[0].action_id,
                requested=[a.action_type for a in out_of_scope],
            )

        rows: list[ActionRow] = []
        for action in actions:
            row = self._persist(action)
            facts = self._facts.load(action, run_compromised=compromised)
            decision = self._governance.evaluate(action, facts)
            self._apply(row, decision, facts, first=True)
            rows.append(row)
        self._session.commit()

        for row in rows:
            if row.status == ActionStatus.AUTHORIZED:
                try:
                    self.execute(row.id)
                except LedgerUnavailableError:
                    # Left AUTHORIZED with the error recorded; an operator can retry.
                    pass
            self._session.refresh(row)
        return rows

    def _persist(self, action: ProposedAction) -> ActionRow:
        now = utc_now_iso()
        row = ActionRow(
            id=action.action_id,
            action_hash=action.action_hash(),
            correlation_id=get_correlation_id(),
            origin=action.origin.value,
            principal_kind=action.principal_kind.value,
            principal_id=action.principal_id,
            action_type=action.action_type,
            invoice_id=action.invoice_id,
            supplier_id=action.supplier_id,
            purchase_order_id=action.purchase_order_id,
            amount=action.amount,
            params=dict(action.params),
            evidence_ids=list(action.evidence_ids),
            recommendation=action.recommendation.value if action.recommendation else None,
            run_id=action.run_id,
            status=ActionStatus.PROPOSED.value,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def _apply(
        self, row: ActionRow, decision: GovernanceDecision, facts: Facts, *, first: bool
    ) -> None:
        row.decision = dump(decision)
        row.status = _STATUS_FOR[decision.decision].value
        row.updated_at = utc_now_iso()
        event = _DECISION_EVENTS[decision.decision] if first else "GOVERNANCE_RECHECK"
        self._audit.record(
            event,
            actor=row.principal_id,
            subject=row.id,
            decision=decision.decision.value,
            decision_id=decision.decision_id,
            action_type=row.action_type,
            invoice_id=row.invoice_id,
            risk_level=decision.risk_level.value,
            required_approval=decision.required_approval,
            reasons=list(decision.reasons),
        )
        if first and decision.failed("duplicate_payment"):
            self._audit.record(
                metrics.DUPLICATE_PAYMENT_BLOCKED,
                actor=row.principal_id,
                subject=row.id,
                invoice_id=row.invoice_id,
            )

    # -------------------------------------------------------- human decision

    def decide(self, action_id: str, user: UserRow, *, approve: bool, comment: str) -> ActionRow:
        row = self._get(action_id)
        if row.status != ActionStatus.PENDING_APPROVAL:
            raise ConflictError(f"Action {action_id} is {row.status}, not awaiting approval.")
        action = to_domain(row)

        # The world may have changed since the request was made.
        facts = self._facts.load(action)
        decision = self._governance.evaluate(action, facts)
        if approve and decision.decision is Decision.DENY:
            self._apply(row, decision, facts, first=False)
            self._session.commit()
            return row

        required_role = decision.required_approval or self._governance.rules.lowest_approver_role
        amount = facts.invoice.amount if facts.invoice else (action.amount or Decimal("0"))
        problems = self._governance.approvals.approver_problems(
            Approver(user.id, user.role, user.approval_limit, user.active),
            required_role=required_role,
            amount=amount,
            requester_id=action.principal_id,
        )
        if problems:
            self._audit.record(
                "APPROVAL_REFUSED", actor=user.id, subject=row.id, problems=problems
            )
            self._session.commit()
            raise ForbiddenError(" ".join(problems))

        target = ActionStatus.AUTHORIZED if approve else ActionStatus.REJECTED
        if not self._transition(row.id, ActionStatus.PENDING_APPROVAL, target):
            self._session.rollback()
            raise ConflictError(f"Action {action_id} was decided by someone else.")

        approval = ApprovalRow(
            id=new_id("APR"),
            action_id=row.id,
            action_hash=row.action_hash,
            user_id=user.id,
            role=user.role,
            decision="APPROVED" if approve else "REJECTED",
            comment=comment,
            timestamp=utc_now_iso(),
            signature="",
        )
        approval.signature = self._signer.sign(signing_payload(approval))
        self._session.add(approval)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(f"Action {action_id} already has a decision.") from exc

        row.decision = dump(decision)
        self._audit.record(
            metrics.APPROVAL_GRANTED if approve else metrics.APPROVAL_REJECTED,
            actor=user.id,
            subject=row.id,
            approval_id=approval.id,
            role=user.role,
            invoice_id=row.invoice_id,
        )
        self._session.commit()

        if approve:
            try:
                self.execute(row.id)
            except LedgerUnavailableError:
                pass
        self._session.refresh(row)
        return row

    # --------------------------------------------------------------- execute

    def execute(self, action_id: str) -> ActionRow:
        """Runs an authorised action exactly once."""
        self._get(action_id)
        # Compare-and-set: of any number of concurrent callers, one proceeds.
        if not self._transition(action_id, ActionStatus.AUTHORIZED, ActionStatus.EXECUTING):
            self._session.rollback()
            raise ConflictError(f"Action {action_id} is not awaiting execution.")
        self._session.commit()

        row = self._get(action_id)
        self._session.refresh(row)
        try:
            receipt = self._execute_authorized(row)
        except LedgerUnavailableError as exc:
            self._session.rollback()
            self._set_status(action_id, ActionStatus.AUTHORIZED, exc.message)
            raise
        except Exception as exc:
            self._session.rollback()
            self._set_status(action_id, ActionStatus.FAILED, f"{type(exc).__name__}: {exc}")
            log_event(logger, "execution_failed", level=logging.ERROR, action_id=action_id)
            raise

        if receipt is not None:
            self._receipts.anchor(receipt)
        self._session.refresh(row)
        return row

    def _execute_authorized(self, row: ActionRow) -> ReceiptRow | None:
        action = to_domain(row)
        if action.action_hash() != row.action_hash:
            return self._stop(row, ActionStatus.DENIED, "Action record changed after it was authorised.")

        facts = self._facts.load(action)
        decision = self._governance.evaluate(action, facts)
        approval = self._session.scalars(
            select(ApprovalRow).where(ApprovalRow.action_id == row.id)
        ).first()

        if decision.decision is Decision.DENY:
            self._apply(row, decision, facts, first=False)
            self._session.commit()
            return None
        if decision.decision is Decision.REQUIRE_APPROVAL:
            if approval is None:
                # Was within the autonomous limit when submitted and no longer is.
                self._apply(row, decision, facts, first=False)
                self._session.commit()
                return None
            problem = self._approval_problem(approval, row, decision, facts)
            if problem:
                return self._stop(row, ActionStatus.DENIED, problem)

        principal = facts.principal
        assert principal is not None and facts.invoice is not None  # guaranteed by governance
        permission = self._governance.rules.action_permissions[action.action_type]

        # Web3 control layer: an agent must also be active and permitted in the
        # on-chain registry, which the backend cannot write to. If the registry
        # cannot be read the agent's action waits; the manual path is unaffected.
        if principal.kind is PrincipalKind.AGENT and not self._ledger.is_authorized(
            id_hash("agent", principal.id), id_hash("permission", permission)
        ):
            return self._stop(
                row,
                ActionStatus.DENIED,
                f"On-chain registry does not authorise {principal.id} for {permission}.",
            )

        if action.action_type != PAY_SUPPLIER:
            return self._stop(row, ActionStatus.DENIED, "No executor for this action type.")

        try:
            payment = self._payments.execute_payment(
                facts.invoice.supplier_id,
                facts.invoice.id,
                facts.invoice.amount,
                idempotency_key=row.action_hash,
                purchase_order_id=facts.invoice.purchase_order_id,
            )
        except DuplicatePaymentError as exc:
            self._audit.record(
                metrics.DUPLICATE_PAYMENT_BLOCKED,
                actor=row.principal_id,
                subject=row.id,
                invoice_id=row.invoice_id,
            )
            return self._stop(row, ActionStatus.DENIED, exc.message)

        invoice = self._session.get(InvoiceRow, facts.invoice.id)
        assert invoice is not None
        invoice.status = "PAID"
        row.status = ActionStatus.EXECUTED.value
        row.decision = dump(decision)
        row.last_error = None
        row.updated_at = utc_now_iso()
        self._audit.record(
            "PAYMENT_EXECUTED",
            actor=row.principal_id,
            subject=row.id,
            tool=PAYMENT_TOOL,
            transaction_id=payment.transaction_id,
            invoice_id=invoice.id,
        )

        provider, model = self._model_for(row)
        receipt = self._receipts.create(
            action=row,
            principal=principal,
            decision=decision,
            approval=approval,
            payment=payment,
            permission=permission,
            tool=PAYMENT_TOOL,
            model_provider=provider,
            model_name=model,
        )
        # Payment, invoice status, action status and receipt commit together.
        self._session.commit()
        return receipt

    def _approval_problem(
        self, approval: ApprovalRow, row: ActionRow, decision: GovernanceDecision, facts: Facts
    ) -> str | None:
        if approval.decision != "APPROVED":
            return "The recorded human decision is not an approval."
        if approval.action_hash != row.action_hash:
            return "The approval was given for a different action."
        if not self._signer.verify(signing_payload(approval), approval.signature):
            return "The approval signature does not verify."
        approver = self._session.get(UserRow, approval.user_id)
        if approver is None:
            return "The approver no longer exists."
        assert facts.invoice is not None and decision.required_approval is not None
        problems = self._governance.approvals.approver_problems(
            Approver(approver.id, approver.role, approver.approval_limit, approver.active),
            required_role=decision.required_approval,
            amount=facts.invoice.amount,
            requester_id=row.principal_id,
        )
        return " ".join(problems) or None

    def _model_for(self, row: ActionRow) -> tuple[str, str]:
        if row.run_id:
            run = self._session.get(AgentRunRow, row.run_id)
            if run is not None:
                return run.analysis["model_provider"], run.analysis["model_name"]
        return "none", "none"

    # --------------------------------------------------------------- helpers

    def _get(self, action_id: str) -> ActionRow:
        row = self._session.get(ActionRow, action_id)
        if row is None:
            raise NotFoundError(f"Action {action_id} not found.")
        return row

    def _transition(self, action_id: str, source: ActionStatus, target: ActionStatus) -> bool:
        result = self._session.execute(
            update(ActionRow)
            .where(ActionRow.id == action_id, ActionRow.status == source.value)
            .values(status=target.value, updated_at=utc_now_iso())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def _set_status(self, action_id: str, status: ActionStatus, error: str) -> None:
        row = self._get(action_id)
        self._session.refresh(row)
        row.status = status.value
        row.last_error = error
        row.updated_at = utc_now_iso()
        self._audit.record(
            "EXECUTION_DEFERRED" if status is ActionStatus.AUTHORIZED else "EXECUTION_FAILED",
            actor="system",
            subject=action_id,
            error=error,
        )
        self._session.commit()

    def _stop(self, row: ActionRow, status: ActionStatus, reason: str) -> None:
        row.status = status.value
        row.last_error = reason
        row.updated_at = utc_now_iso()
        self._audit.record("EXECUTION_REFUSED", actor="system", subject=row.id, reason=reason)
        self._session.commit()
        return None
