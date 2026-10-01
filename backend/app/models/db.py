"""SQLAlchemy tables: operational state for the application."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


class MoneyType(TypeDecorator[Decimal]):
    """Decimal in Python, integer cents in the database."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Any) -> int | None:
        if value is None:
            return None
        return int((Decimal(value) * 100).to_integral_value())

    def process_result_value(self, value: int | None, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(Decimal("0.01"))


class Base(DeclarativeBase):
    pass


class SupplierRow(Base):
    __tablename__ = "suppliers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    risk: Mapped[str] = mapped_column(String)
    payment_limit: Mapped[Decimal] = mapped_column(MoneyType)
    account_token: Mapped[str] = mapped_column(String)


class PurchaseOrderRow(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    supplier_id: Mapped[str] = mapped_column(String, index=True)
    approved_amount: Mapped[Decimal] = mapped_column(MoneyType)
    description: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


class ContractRow(Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    supplier_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    purchase_order_ids: Mapped[list[str]] = mapped_column(JSON)
    terms: Mapped[str] = mapped_column(Text)


class InvoiceRow(Base):
    __tablename__ = "invoices"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    supplier_id: Mapped[str] = mapped_column(String, index=True)
    purchase_order_id: Mapped[str] = mapped_column(String, index=True)
    amount: Mapped[Decimal] = mapped_column(MoneyType)
    description: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String)
    scenario: Mapped[str] = mapped_column(String, default="")


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    approval_limit: Mapped[Decimal] = mapped_column(MoneyType)
    permissions: Mapped[list[str]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentRow(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON)
    forbidden_actions: Mapped[list[str]] = mapped_column(JSON)
    autonomous_payment_limit: Mapped[Decimal] = mapped_column(MoneyType)
    policy: Mapped[str] = mapped_column(String)


class ActionRow(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_hash: Mapped[str] = mapped_column(String, unique=True)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    origin: Mapped[str] = mapped_column(String)
    principal_kind: Mapped[str] = mapped_column(String)
    principal_id: Mapped[str] = mapped_column(String)
    action_type: Mapped[str] = mapped_column(String)
    invoice_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    supplier_id: Mapped[str | None] = mapped_column(String, nullable=True)
    purchase_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(MoneyType, nullable=True)
    params: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommendation: Mapped[str | None] = mapped_column(String, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    # One human decision per action: a second approver cannot overwrite the first.
    __table_args__ = (UniqueConstraint("action_id", name="uq_approval_action"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_id: Mapped[str] = mapped_column(String, index=True)
    action_hash: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)
    comment: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[str] = mapped_column(String)
    signature: Mapped[str] = mapped_column(String)


class PaymentRow(Base):
    __tablename__ = "payments"
    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    # The database, not application code, is the last line against a double payment.
    invoice_id: Mapped[str] = mapped_column(String, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    supplier_id: Mapped[str] = mapped_column(String)
    purchase_order_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(MoneyType)
    status: Mapped[str] = mapped_column(String)
    timestamp: Mapped[str] = mapped_column(String)


class ReceiptRow(Base):
    __tablename__ = "receipts"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_id: Mapped[str] = mapped_column(String, unique=True)
    action_id: Mapped[str] = mapped_column(String, unique=True)
    action_hash: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    receipt_hash: Mapped[str] = mapped_column(String)
    anchor_status: Mapped[str] = mapped_column(String, default="PENDING")
    anchor_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    blockchain_tx_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    block_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_verification: Mapped[str | None] = mapped_column(String, nullable=True)
    demo_backup: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String, index=True)
    correlation_id: Mapped[str] = mapped_column(String)
    requested_by: Mapped[str] = mapped_column(String)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String)
    event_hash: Mapped[str] = mapped_column(String)


class SystemStateRow(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict[str, Any] = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **kwargs)
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    def new_session(self) -> Session:
        return self._factory()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._factory()
        try:
            yield session
        finally:
            session.close()
