"""Mock payment tool. Never talks to a real payment provider."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DuplicatePaymentError
from app.models.db import PaymentRow
from app.models.domain import PaymentResult, utc_now_iso


def _result(row: PaymentRow) -> PaymentResult:
    return PaymentResult(
        transaction_id=row.transaction_id,
        invoice_id=row.invoice_id,
        supplier_id=row.supplier_id,
        amount=row.amount,
        status=row.status,
        timestamp=row.timestamp,
    )


class MockPaymentService:
    """Idempotent on `idempotency_key`; at most one payment per invoice.

    Both guarantees are unique constraints, so they hold under concurrent
    callers. Because this mock writes to the application database, payment and
    receipt commit in one transaction. A real provider would not: see
    docs/SECURITY.md, "Duplicate execution".
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def execute_payment(
        self,
        supplier_id: str,
        invoice_id: str,
        amount: Decimal,
        *,
        idempotency_key: str,
        purchase_order_id: str | None = None,
    ) -> PaymentResult:
        replay = self._session.scalars(
            select(PaymentRow).where(PaymentRow.idempotency_key == idempotency_key)
        ).first()
        if replay is not None:
            return _result(replay)

        row = PaymentRow(
            transaction_id=f"MOCK-TX-{uuid.uuid4().hex[:10].upper()}",
            invoice_id=invoice_id,
            idempotency_key=idempotency_key,
            supplier_id=supplier_id,
            purchase_order_id=purchase_order_id,
            amount=amount,
            status="SUCCESS",
            timestamp=utc_now_iso(),
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
        except IntegrityError as exc:
            raise DuplicatePaymentError(f"Invoice {invoice_id} has already been paid.") from exc
        return _result(row)
