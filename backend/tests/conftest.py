from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.blockchain.memory_ledger import InMemoryLedger
from app.config import Settings
from app.container import AppContainer, Services
from app.main import create_app
from app.models.db import UserRow
from app.models.domain import (
    PAY_SUPPLIER,
    Facts,
    InvoiceFact,
    Origin,
    Principal,
    PrincipalKind,
    ProposedAction,
    PurchaseOrderFact,
    Recommendation,
    SupplierFact,
)

AGENT_ID = "AGENT-TREASURY-001"
ALICE, BOB, CAROL = "USR-001", "USR-002", "USR-003"  # manager, CFO, AP clerk


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        ledger_mode="memory",
        approval_signing_secret="test-secret",
        rate_limit_per_minute=0,
    )


@pytest.fixture
def container(settings: Settings) -> AppContainer:
    container = AppContainer(settings)
    container.initialise()
    return container


@pytest.fixture
def ledger(container: AppContainer) -> InMemoryLedger:
    assert isinstance(container.ledger, InMemoryLedger)
    return container.ledger


@pytest.fixture
def services(container: AppContainer) -> Iterator[Services]:
    with container.db.session() as session:
        yield container.services(session)


@pytest.fixture
def client(container: AppContainer) -> Iterator[TestClient]:
    with TestClient(create_app(container)) as test_client:
        yield test_client


def as_user(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}


def get_user(services: Services, user_id: str) -> UserRow:
    user = services.session.get(UserRow, user_id)
    assert user is not None
    return user


# ---- builders for pure governance tests: no database involved --------------

def agent_principal(**overrides: object) -> Principal:
    values: dict[str, object] = {
        "kind": PrincipalKind.AGENT,
        "id": AGENT_ID,
        "name": "Treasury AI Agent",
        "role": "TREASURY_ASSISTANT",
        "active": True,
        "permissions": frozenset(
            {"READ_INVOICE", "READ_SUPPLIER", "READ_PO", "READ_POLICY", "PROPOSE_PAYMENT"}
        ),
        "forbidden": frozenset(
            {"CHANGE_SUPPLIER", "CHANGE_SUPPLIER_BANK_ACCOUNT", "CREATE_SUPPLIER", "DELETE_AUDIT_RECORD"}
        ),
        "autonomous_limit": Decimal("1000"),
        "version": "1.0.0",
    }
    values.update(overrides)
    return Principal(**values)  # type: ignore[arg-type]


def payment_action(amount: str | None = "50000", **overrides: object) -> ProposedAction:
    values: dict[str, object] = {
        "action_id": "ACT-TEST",
        "action_type": PAY_SUPPLIER,
        "principal_kind": PrincipalKind.AGENT,
        "principal_id": AGENT_ID,
        "origin": Origin.AI,
        "invoice_id": "INV-1",
        "supplier_id": "SUP-1",
        "purchase_order_id": "PO-1",
        "amount": Decimal(amount) if amount is not None else None,
        "evidence_ids": ("invoice:INV-1", "supplier:SUP-1", "po:PO-1"),
        "recommendation": Recommendation.PAYMENT_RECOMMENDED,
    }
    values.update(overrides)
    return ProposedAction(**values)  # type: ignore[arg-type]


def payment_facts(amount: str = "50000", **overrides: object) -> Facts:
    values: dict[str, object] = {
        "principal": agent_principal(),
        "ai_enabled": True,
        "invoice": InvoiceFact(
            id="INV-1",
            supplier_id="SUP-1",
            purchase_order_id="PO-1",
            amount=Decimal(amount),
            status="PENDING",
        ),
        "supplier": SupplierFact(
            id="SUP-1", name="Acme", status="APPROVED", risk="LOW", payment_limit=Decimal("1000000")
        ),
        "purchase_order": PurchaseOrderFact(
            id="PO-1", supplier_id="SUP-1", approved_amount=Decimal(amount), status="APPROVED"
        ),
    }
    values.update(overrides)
    return Facts(**values)  # type: ignore[arg-type]
