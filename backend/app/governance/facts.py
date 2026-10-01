"""Loads the facts a decision is made on from the system of record.

This is the only impure part of governance. It never reads a value from the
request when the database has its own copy.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.governance.rules import PolicyRules
from app.models.db import (
    ActionRow,
    AgentRow,
    ContractRow,
    InvoiceRow,
    PaymentRow,
    PurchaseOrderRow,
    SupplierRow,
    UserRow,
)
from app.models.domain import (
    IN_FLIGHT_STATUSES,
    PAY_SUPPLIER,
    Facts,
    InvoiceFact,
    Principal,
    PrincipalKind,
    ProposedAction,
    PurchaseOrderFact,
    SupplierFact,
)
from app.rag.retriever import Retriever
from app.security.injection import looks_like_injection
from app.services.state import SystemState

_RECORD_TABLES = {
    "invoice": InvoiceRow,
    "payment_history": InvoiceRow,  # a lookup keyed by invoice id
    "supplier": SupplierRow,
    "po": PurchaseOrderRow,
    "contract": ContractRow,
}


class FactLoader:
    def __init__(self, session: Session, rules: PolicyRules, retriever: Retriever) -> None:
        self._session = session
        self._rules = rules
        self._retriever = retriever

    def principal(self, kind: PrincipalKind, principal_id: str) -> Principal | None:
        if kind is PrincipalKind.AGENT:
            agent = self._session.get(AgentRow, principal_id)
            if agent is None:
                return None
            return Principal(
                kind=kind,
                id=agent.id,
                name=agent.name,
                role=agent.role,
                active=agent.status == "ACTIVE",
                permissions=frozenset(agent.allowed_actions),
                forbidden=frozenset(agent.forbidden_actions),
                autonomous_limit=agent.autonomous_payment_limit,
                version=agent.version,
            )
        user = self._session.get(UserRow, principal_id)
        if user is None:
            return None
        return Principal(
            kind=kind,
            id=user.id,
            name=user.name,
            role=user.role,
            active=user.active,
            permissions=frozenset(user.permissions),
            autonomous_limit=self._rules.human_autonomous_limit,
        )

    def evidence_exists(self, source_id: str) -> bool:
        kind, _, identifier = source_id.partition(":")
        if kind == "policy":
            return self._retriever.get(source_id) is not None
        table = _RECORD_TABLES.get(kind)
        return table is not None and self._session.get(table, identifier) is not None

    def load(self, action: ProposedAction, *, run_compromised: bool = False) -> Facts:
        session = self._session
        invoice = session.get(InvoiceRow, action.invoice_id) if action.invoice_id else None
        supplier = session.get(SupplierRow, invoice.supplier_id) if invoice else None
        po = session.get(PurchaseOrderRow, invoice.purchase_order_id) if invoice else None

        paid_against_po = Decimal("0")
        already_paid = False
        in_flight: str | None = None
        if invoice is not None:
            already_paid = (
                session.scalars(
                    select(PaymentRow).where(PaymentRow.invoice_id == invoice.id)
                ).first()
                is not None
            )
            paid_against_po = sum(
                (
                    p.amount
                    for p in session.scalars(
                        select(PaymentRow).where(
                            PaymentRow.purchase_order_id == invoice.purchase_order_id
                        )
                    )
                ),
                Decimal("0"),
            )
            in_flight = session.scalars(
                select(ActionRow.id).where(
                    ActionRow.invoice_id == invoice.id,
                    ActionRow.action_type == PAY_SUPPLIER,
                    ActionRow.status.in_([s.value for s in IN_FLIGHT_STATUSES]),
                    ActionRow.id != action.action_id,
                )
            ).first()

        return Facts(
            principal=self.principal(action.principal_kind, action.principal_id),
            ai_enabled=SystemState(session).ai_enabled(),
            invoice=InvoiceFact(
                id=invoice.id,
                supplier_id=invoice.supplier_id,
                purchase_order_id=invoice.purchase_order_id,
                amount=invoice.amount,
                status=invoice.status,
            )
            if invoice
            else None,
            supplier=SupplierFact(
                id=supplier.id,
                name=supplier.name,
                status=supplier.status,
                risk=supplier.risk,
                payment_limit=supplier.payment_limit,
            )
            if supplier
            else None,
            purchase_order=PurchaseOrderFact(
                id=po.id,
                supplier_id=po.supplier_id,
                approved_amount=po.approved_amount,
                status=po.status,
            )
            if po
            else None,
            paid_against_po=paid_against_po,
            invoice_already_paid=already_paid,
            in_flight_action_id=in_flight,
            unresolved_evidence_ids=tuple(
                e for e in action.evidence_ids if not self.evidence_exists(e)
            ),
            untrusted_content_flagged=bool(
                invoice and looks_like_injection(f"{invoice.description}\n{invoice.notes}")
            ),
            run_compromised=run_compromised,
        )
