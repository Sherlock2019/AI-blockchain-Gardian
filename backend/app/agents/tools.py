"""The agent's toolbox.

Every tool here is a read. There is no payment tool, no supplier-update tool
and no way to reach one from this class: the strongest tool boundary is a tool
that does not exist. Each call is still checked against the agent's
permissions and written to the audit trail.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ForbiddenError
from app.models.db import ContractRow, InvoiceRow, PaymentRow, PurchaseOrderRow, SupplierRow
from app.models.domain import Principal, RetrievedSource
from app.observability.audit import AuditLog
from app.rag.retriever import Retriever
from app.security.hashing import money_str

_SNIPPET_LENGTH = 320


class ToolGateway:
    def __init__(
        self, principal: Principal, session: Session, retriever: Retriever, audit: AuditLog
    ) -> None:
        self._principal = principal
        self._session = session
        self._retriever = retriever
        self._audit = audit
        # What was actually read. Citations come from here, not from the model,
        # so a recommendation cannot cite a document the agent never saw.
        self.sources: list[RetrievedSource] = []

    def _authorize(self, permission: str, subject: str) -> None:
        allowed = self._principal.active and permission in self._principal.permissions
        self._audit.record(
            "TOOL_CALL" if allowed else "TOOL_CALL_DENIED",
            actor=self._principal.id,
            subject=subject,
            permission=permission,
        )
        if not allowed:
            raise ForbiddenError(f"{self._principal.id} does not possess {permission} permission.")

    def _cite(self, source_id: str, kind: str, title: str, snippet: str, score: float | None = None) -> None:
        if all(s.source_id != source_id for s in self.sources):
            self.sources.append(
                RetrievedSource(
                    source_id=source_id,
                    kind=kind,
                    title=title,
                    snippet=snippet[:_SNIPPET_LENGTH],
                    score=score,
                )
            )

    def read_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        self._authorize("READ_INVOICE", invoice_id)
        row = self._session.get(InvoiceRow, invoice_id)
        if row is None:
            return None
        self._cite(
            f"invoice:{row.id}",
            "invoice",
            f"Invoice {row.id}",
            f"{row.description}. Amount {money_str(row.amount)}. Supplier {row.supplier_id}. "
            f"PO {row.purchase_order_id}. Status {row.status}.",
        )
        return {
            "id": row.id,
            "supplier_id": row.supplier_id,
            "purchase_order_id": row.purchase_order_id,
            "amount": money_str(row.amount),
            "description": row.description,
            "status": row.status,
            "notes": row.notes,
        }

    def read_supplier(self, supplier_id: str) -> dict[str, Any] | None:
        self._authorize("READ_SUPPLIER", supplier_id)
        row = self._session.get(SupplierRow, supplier_id)
        if row is None:
            return None
        self._cite(
            f"supplier:{row.id}",
            "supplier",
            f"Supplier {row.id} — {row.name}",
            f"Status {row.status}. Risk {row.risk}. Payment limit {money_str(row.payment_limit)}.",
        )
        # The account token is deliberately not returned: the agent has no use for it.
        return {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "risk": row.risk,
            "payment_limit": money_str(row.payment_limit),
        }

    def read_purchase_order(self, po_id: str) -> dict[str, Any] | None:
        self._authorize("READ_PO", po_id)
        row = self._session.get(PurchaseOrderRow, po_id)
        if row is None:
            return None
        self._cite(
            f"po:{row.id}",
            "purchase_order",
            f"Purchase order {row.id}",
            f"{row.description}. Approved amount {money_str(row.approved_amount)}. "
            f"Supplier {row.supplier_id}. Status {row.status}.",
        )
        contract = next(
            (
                c
                for c in self._session.scalars(
                    select(ContractRow).where(ContractRow.supplier_id == row.supplier_id)
                )
                if row.id in c.purchase_order_ids
            ),
            None,
        )
        if contract is not None:
            self._cite(f"contract:{contract.id}", "contract", contract.title, contract.terms)
        return {
            "id": row.id,
            "supplier_id": row.supplier_id,
            "approved_amount": money_str(row.approved_amount),
            "description": row.description,
            "status": row.status,
            "contract_id": contract.id if contract else None,
        }

    def read_payment_history(self, invoice_id: str) -> list[dict[str, Any]]:
        """Payments already made against this invoice. Part of reading the invoice's state."""
        self._authorize("READ_INVOICE", f"payments:{invoice_id}")
        rows = list(
            self._session.scalars(select(PaymentRow).where(PaymentRow.invoice_id == invoice_id))
        )
        self._cite(
            f"payment_history:{invoice_id}",
            "payment_history",
            f"Payment history for {invoice_id}",
            "; ".join(f"{r.transaction_id} paid {money_str(r.amount)} on {r.timestamp[:10]}" for r in rows)
            or "No payment has been made against this invoice.",
        )
        return [
            {"transaction_id": r.transaction_id, "amount": money_str(r.amount), "status": r.status}
            for r in rows
        ]

    def search_policy(self, query: str, k: int = 4) -> list[RetrievedSource]:
        self._authorize("READ_POLICY", "policy-search")
        found = []
        for hit in self._retriever.search(query, k=k, kind="policy"):
            self._cite(hit.chunk.source_id, "policy", hit.chunk.title, hit.chunk.text, hit.score)
            found.append(next(s for s in self.sources if s.source_id == hit.chunk.source_id))
        return found
