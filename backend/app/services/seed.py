"""Loads the synthetic enterprise data into an empty database."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db import (
    AgentRow,
    ContractRow,
    InvoiceRow,
    PaymentRow,
    PurchaseOrderRow,
    SupplierRow,
    UserRow,
)
from app.models.domain import utc_now_iso


def _load(data_dir: Path, name: str) -> list[dict[str, Any]]:
    return json.loads((data_dir / name).read_text(encoding="utf-8"))


def seed_if_empty(session: Session, data_dir: Path) -> bool:
    if session.scalars(select(SupplierRow).limit(1)).first() is not None:
        return False

    for s in _load(data_dir, "suppliers.json"):
        session.add(SupplierRow(**{**s, "payment_limit": Decimal(s["payment_limit"])}))
    for p in _load(data_dir, "purchase_orders.json"):
        session.add(PurchaseOrderRow(**{**p, "approved_amount": Decimal(p["approved_amount"])}))
    for c in _load(data_dir, "contracts.json"):
        session.add(ContractRow(**c))
    for u in _load(data_dir, "users.json"):
        session.add(UserRow(**{**u, "approval_limit": Decimal(u["approval_limit"])}))
    for a in _load(data_dir, "agents.json"):
        session.add(
            AgentRow(
                **{**a, "autonomous_payment_limit": Decimal(a["autonomous_payment_limit"])}
            )
        )
    for i in _load(data_dir, "invoices.json"):
        invoice = InvoiceRow(**{**i, "amount": Decimal(i["amount"])})
        session.add(invoice)
        if invoice.status == "PAID":
            # Paid before this system existed: gives the duplicate control something to find.
            session.add(
                PaymentRow(
                    transaction_id=f"MOCK-TX-SEED-{invoice.id[-4:]}",
                    invoice_id=invoice.id,
                    idempotency_key=f"seed:{invoice.id}",
                    supplier_id=invoice.supplier_id,
                    purchase_order_id=invoice.purchase_order_id,
                    amount=invoice.amount,
                    status="SUCCESS",
                    timestamp=utc_now_iso(),
                )
            )
    session.commit()
    return True
