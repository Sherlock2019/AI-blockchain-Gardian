"""End-to-end scenarios at the service layer: real SQLite, simulated ledger, mock model."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.container import AppContainer, Services
from app.errors import AIDisabledError, ConflictError, ForbiddenError, LedgerUnavailableError
from app.models.db import (
    ActionRow,
    AgentRow,
    ApprovalRow,
    AuditEventRow,
    InvoiceRow,
    PaymentRow,
    ReceiptRow,
    SupplierRow,
)
from app.observability.metrics import collect_metrics
from app.security.hashing import id_hash
from tests.conftest import AGENT_ID, ALICE, BOB, CAROL, get_user


def run_agent(services: Services, invoice_id: str) -> list[ActionRow]:
    run = services.agent_runs.run(invoice_id, get_user(services, CAROL))
    return list(
        services.session.scalars(
            select(ActionRow).where(ActionRow.run_id == run.id).order_by(ActionRow.created_at)
        )
    )


def payment_of(actions: list[ActionRow]) -> ActionRow:
    return next(a for a in actions if a.action_type == "PAY_SUPPLIER")


def payments(services: Services, invoice_id: str) -> int:
    return services.session.scalar(
        select(func.count()).select_from(PaymentRow).where(PaymentRow.invoice_id == invoice_id)
    )


def events(services: Services, event_type: str) -> list[AuditEventRow]:
    return list(
        services.session.scalars(select(AuditEventRow).where(AuditEventRow.event_type == event_type))
    )


# ---- scenario 1: small payment, no human needed -----------------------------

def test_small_payment_is_executed_without_approval(services):
    action = payment_of(run_agent(services, "INV-2026-0043"))
    assert action.status == "EXECUTED"
    assert action.decision["decision"] == "ALLOW"
    assert payments(services, "INV-2026-0043") == 1
    assert services.session.get(InvoiceRow, "INV-2026-0043").status == "PAID"

    receipt = services.session.scalars(select(ReceiptRow)).one()
    assert receipt.payload["human_approval_id"] is None
    assert receipt.payload["agent_id"] == AGENT_ID
    assert receipt.anchor_status == "ANCHORED"


# ---- scenario 2: finance manager approval -----------------------------------

def test_fifty_thousand_waits_for_a_finance_manager(services):
    action = payment_of(run_agent(services, "INV-2026-0042"))
    assert action.status == "PENDING_APPROVAL"
    assert action.decision["required_approval"] == "FINANCE_MANAGER"
    assert payments(services, "INV-2026-0042") == 0  # nothing moves before a human decides

    decided = services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="ok")
    assert decided.status == "EXECUTED"
    assert payments(services, "INV-2026-0042") == 1

    receipt = services.session.scalars(select(ReceiptRow)).one()
    approval = services.session.scalars(select(ApprovalRow)).one()
    assert receipt.payload["human_approval_id"] == approval.id
    assert receipt.payload["amount"] == "50000.00"
    assert receipt.payload["governance_decision"] == "REQUIRE_APPROVAL"
    assert receipt.payload["model_name"] == "mock-treasury-1"
    assert "invoice:INV-2026-0042" in receipt.payload["retrieved_source_ids"]
    assert approval.signature.startswith("mock-hmac-sha256:")
    assert services.receipts.verify(receipt.receipt_id)["status"] == "VERIFIED"


def test_rejection_stops_the_payment(services):
    action = payment_of(run_agent(services, "INV-2026-0042"))
    decided = services.workflow.decide(action.id, get_user(services, ALICE), approve=False, comment="no")
    assert decided.status == "REJECTED"
    assert payments(services, "INV-2026-0042") == 0
    assert services.session.get(InvoiceRow, "INV-2026-0042").status == "PENDING"


# ---- scenario 3: CFO approval -----------------------------------------------

def test_quarter_million_needs_the_cfo(services):
    action = payment_of(run_agent(services, "INV-2026-0044"))
    assert action.decision["required_approval"] == "CFO"

    with pytest.raises(ForbiddenError, match="CFO is required"):
        services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    assert services.session.get(ActionRow, action.id).status == "PENDING_APPROVAL"
    assert payments(services, "INV-2026-0044") == 0
    assert len(events(services, "APPROVAL_REFUSED")) == 1

    decided = services.workflow.decide(action.id, get_user(services, BOB), approve=True, comment="")
    assert decided.status == "EXECUTED"


def test_clerk_cannot_approve_or_reject(services):
    action = payment_of(run_agent(services, "INV-2026-0042"))
    for approve in (True, False):
        with pytest.raises(ForbiddenError):
            services.workflow.decide(action.id, get_user(services, CAROL), approve=approve, comment="")
    assert services.session.get(ActionRow, action.id).status == "PENDING_APPROVAL"


# ---- scenarios 4 and 5: denied by policy ------------------------------------

def test_blocked_supplier_is_denied(services):
    action = payment_of(run_agent(services, "INV-2026-0045"))
    assert action.status == "DENIED"
    assert any("BLOCKED" in r for r in action.decision["reasons"])
    assert payments(services, "INV-2026-0045") == 0


def test_invoice_exceeding_purchase_order_is_denied(services):
    action = payment_of(run_agent(services, "INV-2026-0046"))
    assert action.status == "DENIED"
    assert any("exceeds" in r for r in action.decision["reasons"])


def test_denied_action_cannot_be_approved_or_executed(services):
    action = payment_of(run_agent(services, "INV-2026-0045"))
    with pytest.raises(ConflictError):
        services.workflow.decide(action.id, get_user(services, BOB), approve=True, comment="")
    with pytest.raises(ConflictError):
        services.workflow.execute(action.id)
    assert payments(services, "INV-2026-0045") == 0


# ---- scenario 6: prompt injection -------------------------------------------

def test_injected_bank_change_is_denied_and_takes_the_run_with_it(services):
    actions = run_agent(services, "INV-2026-0047")
    bank_change = next(a for a in actions if a.action_type == "CHANGE_SUPPLIER_BANK_ACCOUNT")
    assert bank_change.status == "DENIED"
    assert (
        "Agent AGENT-TREASURY-001 is explicitly forbidden from CHANGE_SUPPLIER_BANK_ACCOUNT."
        in bank_change.decision["reasons"]
    )

    payment = payment_of(actions)
    assert payment.status == "DENIED"
    assert any("outside the agent's scope" in r for r in payment.decision["reasons"])

    assert payments(services, "INV-2026-0047") == 0
    assert services.session.get(SupplierRow, "SUP-002").account_token == "MOCK-GLOBAL-002"
    assert collect_metrics(services.session)["prompt_injection_blocks"] == 1


def test_model_that_resists_injection_still_gets_no_autonomy(container: AppContainer):
    """Governance does not rely on which way the model happened to go."""
    from app.agents.llm import MockLLMProvider

    container.llm = MockLLMProvider(obeys_injection=False)
    with container.db.session() as session:
        services = container.services(session)
        actions = run_agent(services, "INV-2026-0047")
        assert [a.action_type for a in actions] == ["PAY_SUPPLIER"]
        assert actions[0].status == "PENDING_APPROVAL"
        checks = {c["name"]: c["status"] for c in actions[0].decision["policy_checks"]}
        assert checks["untrusted_content"] == "ESCALATE"
        assert checks["ai_recommendation"] == "ESCALATE"


# ---- scenario 7: duplicates -------------------------------------------------

def test_already_paid_invoice_is_denied_as_duplicate(services):
    action = payment_of(run_agent(services, "INV-2026-0040"))
    assert action.status == "DENIED"
    assert "Invoice INV-2026-0040 has already been paid." in action.decision["reasons"]
    assert payments(services, "INV-2026-0040") == 1
    assert collect_metrics(services.session)["duplicate_payment_blocks"] == 1


def test_second_request_while_one_is_pending_is_denied(services):
    first = payment_of(run_agent(services, "INV-2026-0042"))
    second = payment_of(run_agent(services, "INV-2026-0042"))
    assert first.status == "PENDING_APPROVAL"
    assert second.status == "DENIED"
    assert any(first.id in r for r in second.decision["reasons"])


def test_paying_twice_after_success_is_denied(services):
    assert payment_of(run_agent(services, "INV-2026-0043")).status == "EXECUTED"
    assert payment_of(run_agent(services, "INV-2026-0043")).status == "DENIED"
    assert payments(services, "INV-2026-0043") == 1


def test_execute_runs_once(services):
    action = payment_of(run_agent(services, "INV-2026-0043"))
    with pytest.raises(ConflictError):
        services.workflow.execute(action.id)
    assert payments(services, "INV-2026-0043") == 1


def test_payment_tool_is_idempotent_and_unique_per_invoice(services):
    from app.errors import DuplicatePaymentError
    from app.services.payment import MockPaymentService

    tool = MockPaymentService(services.session)
    first = tool.execute_payment("SUP-001", "INV-X", Decimal("10"), idempotency_key="key-1")
    replay = tool.execute_payment("SUP-001", "INV-X", Decimal("10"), idempotency_key="key-1")
    assert replay.transaction_id == first.transaction_id
    assert first.transaction_id.startswith("MOCK-TX-")
    with pytest.raises(DuplicatePaymentError):
        tool.execute_payment("SUP-001", "INV-X", Decimal("10"), idempotency_key="key-2")
    assert payments(services, "INV-X") == 1


def test_one_decision_per_action(services):
    action = payment_of(run_agent(services, "INV-2026-0042"))
    services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    with pytest.raises(ConflictError):
        services.workflow.decide(action.id, get_user(services, BOB), approve=True, comment="")
    assert services.session.scalar(select(func.count()).select_from(ApprovalRow)) == 1


# ---- scenario 8: AI off, manual workflow ------------------------------------

def test_agent_is_refused_when_ai_is_off(services):
    services.state.set_ai_enabled(False)
    services.session.commit()
    with pytest.raises(AIDisabledError):
        services.agent_runs.run("INV-2026-0048", get_user(services, CAROL))
    assert services.session.scalar(select(func.count()).select_from(ActionRow)) == 0


def test_manual_workflow_runs_under_the_same_controls_with_ai_off(services):
    services.state.set_ai_enabled(False)
    services.session.commit()

    action = services.manual.submit(get_user(services, CAROL), "INV-2026-0048")
    assert action.origin == "MANUAL"
    assert action.status == "PENDING_APPROVAL"
    assert action.decision["required_approval"] == "FINANCE_MANAGER"

    decided = services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    assert decided.status == "EXECUTED"
    receipt = services.session.scalars(select(ReceiptRow)).one()
    assert receipt.payload["agent_id"] is None
    assert receipt.payload["requested_by"] == CAROL
    assert receipt.payload["model_provider"] == "none"
    assert services.receipts.verify(receipt.receipt_id)["status"] == "VERIFIED"


def test_manual_requests_are_denied_by_the_same_policy(services):
    assert services.manual.submit(get_user(services, CAROL), "INV-2026-0045").status == "DENIED"
    assert services.manual.submit(get_user(services, CAROL), "INV-2026-0046").status == "DENIED"


def test_person_cannot_approve_their_own_request(services):
    action = services.manual.submit(get_user(services, ALICE), "INV-2026-0048")
    with pytest.raises(ForbiddenError, match="own request"):
        services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    assert services.workflow.decide(
        action.id, get_user(services, BOB), approve=True, comment=""
    ).status == "EXECUTED"


def test_manually_typed_wrong_amount_is_denied(services):
    action = services.manual.submit(
        get_user(services, CAROL), "INV-2026-0048", amount=Decimal("180000")
    )
    assert action.status == "DENIED"
    assert any("does not match" in r for r in action.decision["reasons"])


def test_switching_ai_off_denies_agent_requests_awaiting_approval(services):
    action = payment_of(run_agent(services, "INV-2026-0042"))
    services.state.set_ai_enabled(False)
    services.session.commit()

    decided = services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    assert decided.status == "DENIED"
    assert payments(services, "INV-2026-0042") == 0
    # The invoice is free to be processed by a person.
    assert services.manual.submit(get_user(services, CAROL), "INV-2026-0042").status == "PENDING_APPROVAL"


# ---- the world changes between request and approval -------------------------

def test_supplier_blocked_after_request_is_caught_at_approval(services):
    action = payment_of(run_agent(services, "INV-2026-0042"))
    services.session.get(SupplierRow, "SUP-001").status = "BLOCKED"
    services.session.commit()

    decided = services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    assert decided.status == "DENIED"
    assert payments(services, "INV-2026-0042") == 0


def test_forged_approval_does_not_execute(services):
    """Someone with database access inserts an approval and flips the status."""
    action = payment_of(run_agent(services, "INV-2026-0042"))
    services.session.add(
        ApprovalRow(
            id="APR-FORGED", action_id=action.id, action_hash=action.action_hash, user_id=ALICE,
            role="FINANCE_MANAGER", decision="APPROVED", comment="", timestamp="2026-01-01T00:00:00Z",
            signature="mock-hmac-sha256:" + "0" * 64,
        )
    )
    action.status = "AUTHORIZED"
    services.session.commit()

    result = services.workflow.execute(action.id)
    assert result.status == "DENIED"
    assert "signature does not verify" in result.last_error
    assert payments(services, "INV-2026-0042") == 0


def test_amount_edited_after_approval_does_not_execute(services):
    action = payment_of(run_agent(services, "INV-2026-0042"))
    services.session.execute(
        ActionRow.__table__.update().where(ActionRow.id == action.id).values(status="PROPOSED")
    )
    services.session.commit()
    services.session.refresh(action)
    action.amount = Decimal("999999")
    action.status = "AUTHORIZED"
    services.session.commit()

    result = services.workflow.execute(action.id)
    assert result.status == "DENIED"
    assert "changed after it was authorised" in result.last_error


def test_action_interrupted_mid_execution_is_recovered_at_startup(container, services):
    """A crash between claiming an action and paying must not strand the invoice."""
    action = payment_of(run_agent(services, "INV-2026-0042"))
    services.session.add(
        ApprovalRow(
            id="APR-X", action_id=action.id, action_hash=action.action_hash, user_id=ALICE,
            role="FINANCE_MANAGER", decision="APPROVED", comment="", timestamp="2026-01-01T00:00:00Z",
            signature="",
        )
    )
    approval = services.session.scalars(select(ApprovalRow)).one()
    from app.services.approvals import signing_payload

    approval.signature = container.signer.sign(signing_payload(approval))
    action.status = "EXECUTING"  # the process died here
    services.session.commit()

    container.initialise()  # restart
    services.session.refresh(action)
    assert action.status == "AUTHORIZED"
    assert payments(services, "INV-2026-0042") == 0

    assert services.workflow.execute(action.id).status == "EXECUTED"
    assert payments(services, "INV-2026-0042") == 1


# ---- web3 control layer -----------------------------------------------------

def test_agent_deactivated_on_chain_cannot_execute(services, ledger):
    ledger.deactivate_agent(id_hash("agent", AGENT_ID))
    action = payment_of(run_agent(services, "INV-2026-0043"))
    assert action.status == "DENIED"
    assert "On-chain registry does not authorise" in action.last_error
    assert payments(services, "INV-2026-0043") == 0
    # The application database still says ACTIVE: the chain is an independent control.
    assert services.session.get(AgentRow, AGENT_ID).status == "ACTIVE"


def test_ledger_outage_holds_agent_actions_and_they_resume(services, ledger):
    ledger.available = False
    action = payment_of(run_agent(services, "INV-2026-0043"))
    assert action.status == "AUTHORIZED"
    assert "unreachable" in action.last_error
    assert payments(services, "INV-2026-0043") == 0
    with pytest.raises(LedgerUnavailableError):
        services.workflow.execute(action.id)

    ledger.available = True
    assert services.workflow.execute(action.id).status == "EXECUTED"
    assert payments(services, "INV-2026-0043") == 1


def test_ledger_outage_does_not_stop_the_manual_workflow(services, ledger):
    ledger.available = False
    action = services.manual.submit(get_user(services, CAROL), "INV-2026-0048")
    decided = services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    assert decided.status == "EXECUTED"

    receipt = services.session.scalars(select(ReceiptRow)).one()
    assert receipt.anchor_status == "PENDING"
    assert services.receipts.verify(receipt.receipt_id)["status"] == "LEDGER_UNAVAILABLE"

    ledger.available = True
    assert services.receipts.anchor(receipt).anchor_status == "ANCHORED"
    assert services.receipts.verify(receipt.receipt_id)["status"] == "VERIFIED"


# ---- audit trail and metrics ------------------------------------------------

def test_every_step_is_audited_under_one_correlation_id(services):
    from app.observability.logging import set_correlation_id

    set_correlation_id("corr-test-0001")
    action = payment_of(run_agent(services, "INV-2026-0042"))
    services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")

    recorded = [e.event_type for e in reversed(services.audit.list(correlation_id="corr-test-0001"))]
    for expected in (
        "TOOL_CALL", "AGENT_RUN_COMPLETED", "GOVERNANCE_REQUIRE_APPROVAL", "APPROVAL_GRANTED",
        "PAYMENT_EXECUTED", "RECEIPT_CREATED", "RECEIPT_ANCHORED",
    ):
        assert expected in recorded
    assert recorded.index("GOVERNANCE_REQUIRE_APPROVAL") < recorded.index("APPROVAL_GRANTED")
    assert recorded.index("APPROVAL_GRANTED") < recorded.index("PAYMENT_EXECUTED")
    assert services.audit.verify_chain()["intact"] is True


def test_audit_chain_detects_an_edited_event(services):
    run_agent(services, "INV-2026-0043")
    event = events(services, "PAYMENT_EXECUTED")[0]
    event.data = {**event.data, "transaction_id": "MOCK-TX-FORGED"}
    services.session.commit()
    result = services.audit.verify_chain()
    assert result["intact"] is False
    assert result["broken_at_seq"] == event.seq


def test_audit_never_stores_invoice_free_text(services):
    run_agent(services, "INV-2026-0047")
    stored = json.dumps([e.data for e in services.session.scalars(select(AuditEventRow))])
    assert "IGNORE ALL PREVIOUS" not in stored


def test_metrics_follow_the_audit_trail(services):
    run_agent(services, "INV-2026-0043")  # allowed
    pending = payment_of(run_agent(services, "INV-2026-0042"))  # needs approval
    run_agent(services, "INV-2026-0045")  # denied
    services.workflow.decide(pending.id, get_user(services, ALICE), approve=False, comment="")

    metrics = collect_metrics(services.session)
    assert metrics["total_agent_requests"] == 3
    assert metrics["actions_allowed"] == 1
    assert metrics["actions_requiring_approval"] == 1
    assert metrics["actions_denied"] == 1
    assert metrics["human_rejections"] == 1
    assert metrics["human_approvals"] == 0
