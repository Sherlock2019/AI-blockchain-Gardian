"""Governance as a pure function: no database, no model, no ledger."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.config import REPO_ROOT
from app.governance.approval import ApprovalEngine, Approver
from app.governance.engine import GovernanceEngine
from app.governance.rules import load_rules
from app.models.domain import (
    CheckStatus,
    Decision,
    GovernanceDecision,
    Origin,
    PrincipalKind,
    Recommendation,
    RiskLevel,
)
from tests.conftest import agent_principal, payment_action, payment_facts

POLICIES: Path = REPO_ROOT / "data" / "policies"


@pytest.fixture(scope="module")
def engine() -> GovernanceEngine:
    return GovernanceEngine(load_rules(POLICIES))


def status_of(decision: GovernanceDecision, name: str) -> CheckStatus:
    for check in (*decision.permission_checks, *decision.policy_checks):
        if check.name == name:
            return check.status
    raise AssertionError(f"check {name} was not evaluated")


# ---- decisions by amount ----------------------------------------------------

@pytest.mark.parametrize(
    ("amount", "decision", "role", "risk"),
    [
        ("500", Decision.ALLOW, None, RiskLevel.LOW),
        ("1000", Decision.ALLOW, None, RiskLevel.LOW),
        ("1000.01", Decision.REQUIRE_APPROVAL, "FINANCE_MANAGER", RiskLevel.MEDIUM),
        ("50000", Decision.REQUIRE_APPROVAL, "FINANCE_MANAGER", RiskLevel.MEDIUM),
        ("100000", Decision.REQUIRE_APPROVAL, "FINANCE_MANAGER", RiskLevel.MEDIUM),
        ("100000.01", Decision.REQUIRE_APPROVAL, "CFO", RiskLevel.HIGH),
        ("250000", Decision.REQUIRE_APPROVAL, "CFO", RiskLevel.HIGH),
    ],
)
def test_thresholds(engine, amount, decision, role, risk):
    result = engine.evaluate(payment_action(amount), payment_facts(amount))
    assert result.decision is decision
    assert result.required_approval == role
    assert result.risk_level is risk


def test_decision_records_policy_version_and_hash(engine):
    result = engine.evaluate(payment_action("500"), payment_facts("500"))
    assert result.policy_version == "PAYMENT-POLICY-v1"
    assert result.policy_hash.startswith("0x") and len(result.policy_hash) == 66


# ---- permission engine ------------------------------------------------------

def test_forbidden_action_is_denied_with_the_reason(engine):
    action = payment_action(action_type="CHANGE_SUPPLIER_BANK_ACCOUNT", amount=None)
    result = engine.evaluate(action, payment_facts())
    assert result.decision is Decision.DENY
    assert result.permission_denied
    assert result.policy_checks == ()  # business checks never run for an unpermitted request
    assert any("CHANGE_SUPPLIER_BANK_ACCOUNT" in reason for reason in result.reasons)


def test_allow_list_denies_even_without_an_explicit_forbid(engine):
    principal = agent_principal(forbidden=frozenset())
    action = payment_action(action_type="CREATE_SUPPLIER", amount=None)
    result = engine.evaluate(action, payment_facts(principal=principal))
    assert result.decision is Decision.DENY
    assert "does not possess CREATE_SUPPLIER permission" in " ".join(result.reasons)


def test_action_the_system_never_defined_is_denied(engine):
    result = engine.evaluate(payment_action(action_type="WIRE_FUNDS_OFFSHORE"), payment_facts())
    assert result.decision is Decision.DENY
    assert status_of(result, "action_known") is CheckStatus.FAIL


def test_explicit_forbid_overrides_a_grant(engine):
    principal = agent_principal(forbidden=frozenset({"PROPOSE_PAYMENT"}))
    result = engine.evaluate(payment_action("500"), payment_facts("500", principal=principal))
    assert result.decision is Decision.DENY
    assert "explicitly forbidden" in " ".join(result.reasons)


def test_unknown_agent_is_denied(engine):
    result = engine.evaluate(payment_action("500"), payment_facts("500", principal=None))
    assert result.decision is Decision.DENY
    assert status_of(result, "identity_valid") is CheckStatus.FAIL


def test_inactive_agent_is_denied(engine):
    facts = payment_facts("500", principal=agent_principal(active=False))
    assert engine.evaluate(payment_action("500"), facts).decision is Decision.DENY


def test_agent_is_denied_when_ai_is_disabled(engine):
    result = engine.evaluate(payment_action("500"), payment_facts("500", ai_enabled=False))
    assert result.decision is Decision.DENY
    assert status_of(result, "ai_mode_enabled") is CheckStatus.FAIL


def test_human_requester_is_unaffected_by_the_kill_switch(engine):
    human = agent_principal(kind=PrincipalKind.HUMAN, id="USR-003", forbidden=frozenset())
    action = payment_action(
        "500", principal_kind=PrincipalKind.HUMAN, principal_id="USR-003", origin=Origin.MANUAL
    )
    facts = payment_facts("500", principal=human, ai_enabled=False)
    assert engine.evaluate(action, facts).decision is Decision.ALLOW


# ---- policy engine ----------------------------------------------------------

def test_blocked_supplier_is_denied(engine):
    facts = payment_facts("500")
    blocked = facts.supplier.model_copy(update={"status": "BLOCKED", "risk": "HIGH"})
    result = engine.evaluate(payment_action("500"), facts.model_copy(update={"supplier": blocked}))
    assert result.decision is Decision.DENY
    assert status_of(result, "supplier_approved") is CheckStatus.FAIL
    assert result.risk_level is RiskLevel.CRITICAL


def test_invoice_above_purchase_order_is_denied(engine):
    facts = payment_facts("27500")
    po = facts.purchase_order.model_copy(update={"approved_amount": Decimal("20000")})
    result = engine.evaluate(payment_action("27500"), facts.model_copy(update={"purchase_order": po}))
    assert result.decision is Decision.DENY
    assert status_of(result, "invoice_matches_po") is CheckStatus.FAIL


def test_earlier_payments_count_against_the_purchase_order(engine):
    facts = payment_facts("500", paid_against_po=Decimal("100"))
    result = engine.evaluate(payment_action("500"), facts)
    assert status_of(result, "invoice_matches_po") is CheckStatus.FAIL


def test_purchase_order_for_another_supplier_is_denied(engine):
    facts = payment_facts("500")
    po = facts.purchase_order.model_copy(update={"supplier_id": "SUP-OTHER"})
    result = engine.evaluate(payment_action("500"), facts.model_copy(update={"purchase_order": po}))
    assert status_of(result, "po_exists") is CheckStatus.FAIL


def test_amount_above_supplier_limit_is_denied(engine):
    facts = payment_facts("500")
    supplier = facts.supplier.model_copy(update={"payment_limit": Decimal("100")})
    result = engine.evaluate(payment_action("500"), facts.model_copy(update={"supplier": supplier}))
    assert status_of(result, "supplier_limit") is CheckStatus.FAIL


def test_already_paid_invoice_is_a_duplicate(engine):
    result = engine.evaluate(payment_action("500"), payment_facts("500", invoice_already_paid=True))
    assert result.decision is Decision.DENY
    assert result.failed("duplicate_payment")


def test_request_in_progress_for_the_same_invoice_is_a_duplicate(engine):
    result = engine.evaluate(payment_action("500"), payment_facts("500", in_flight_action_id="ACT-9"))
    assert result.failed("duplicate_payment")


@pytest.mark.parametrize(
    "claim",
    [{"amount": Decimal("55000")}, {"supplier_id": "SUP-EVIL"}, {"purchase_order_id": "PO-OTHER"}],
)
def test_claims_that_differ_from_the_record_are_denied(engine, claim):
    """A hallucinated amount or a swapped supplier never reaches a human for approval."""
    action = payment_action("50000").model_copy(update=claim)
    result = engine.evaluate(action, payment_facts("50000"))
    assert result.decision is Decision.DENY
    assert result.failed("request_matches_record")


def test_ai_request_without_evidence_is_denied(engine):
    result = engine.evaluate(payment_action("500", evidence_ids=()), payment_facts("500"))
    assert result.failed("evidence_present")


def test_ai_request_citing_nonexistent_evidence_is_denied(engine):
    facts = payment_facts("500", unresolved_evidence_ids=("policy:made_up#9",))
    assert engine.evaluate(payment_action("500"), facts).failed("evidence_present")


def test_compromised_run_denies_an_otherwise_valid_payment(engine):
    result = engine.evaluate(payment_action("500"), payment_facts("500", run_compromised=True))
    assert result.decision is Decision.DENY
    assert result.failed("run_integrity")


def test_instruction_like_invoice_text_forces_human_review_below_the_limit(engine):
    result = engine.evaluate(
        payment_action("500"), payment_facts("500", untrusted_content_flagged=True)
    )
    assert result.decision is Decision.REQUIRE_APPROVAL
    assert result.required_approval == "FINANCE_MANAGER"
    assert result.risk_level is RiskLevel.HIGH


@pytest.mark.parametrize(
    "recommendation", [Recommendation.PAYMENT_NOT_RECOMMENDED, Recommendation.MANUAL_REVIEW]
)
def test_model_doubt_adds_review_but_never_decides(engine, recommendation):
    """The model's opinion can tighten the outcome. It cannot loosen it."""
    doubtful = payment_action("500", recommendation=recommendation)
    assert engine.evaluate(doubtful, payment_facts("500")).decision is Decision.REQUIRE_APPROVAL

    confident = payment_action("50000", recommendation=Recommendation.PAYMENT_RECOMMENDED)
    assert engine.evaluate(confident, payment_facts("50000")).decision is Decision.REQUIRE_APPROVAL


def test_medium_risk_supplier_raises_risk(engine):
    facts = payment_facts("500")
    supplier = facts.supplier.model_copy(update={"risk": "MEDIUM"})
    result = engine.evaluate(payment_action("500"), facts.model_copy(update={"supplier": supplier}))
    assert result.risk_level is RiskLevel.MEDIUM
    assert result.decision is Decision.ALLOW


# ---- approval engine --------------------------------------------------------

@pytest.fixture(scope="module")
def approvals() -> ApprovalEngine:
    return ApprovalEngine(load_rules(POLICIES))


MANAGER = Approver("USR-001", "FINANCE_MANAGER", Decimal("100000"), True)
CFO = Approver("USR-002", "CFO", Decimal("1000000"), True)
CLERK = Approver("USR-003", "AP_CLERK", Decimal("0"), True)


def problems(approvals: ApprovalEngine, approver: Approver, role: str, amount: str, requester="AGENT"):
    return approvals.approver_problems(
        approver, required_role=role, amount=Decimal(amount), requester_id=requester
    )


def test_manager_may_approve_within_limit(approvals):
    assert problems(approvals, MANAGER, "FINANCE_MANAGER", "50000") == []


def test_cfo_may_approve_what_a_manager_may(approvals):
    assert problems(approvals, CFO, "FINANCE_MANAGER", "50000") == []


def test_manager_may_not_approve_a_cfo_level_payment(approvals):
    found = problems(approvals, MANAGER, "CFO", "250000")
    assert any("CFO is required" in p for p in found)
    assert any("Approval limit" in p for p in found)


def test_clerk_may_not_approve(approvals):
    assert problems(approvals, CLERK, "FINANCE_MANAGER", "5000")


def test_role_alone_is_not_enough_when_the_limit_is_too_low(approvals):
    junior = Approver("USR-009", "FINANCE_MANAGER", Decimal("10000"), True)
    assert problems(approvals, junior, "FINANCE_MANAGER", "50000") == [
        "Approval limit 10000.00 is below the amount 50000.00."
    ]


def test_requester_may_not_approve_their_own_request(approvals):
    found = problems(approvals, MANAGER, "FINANCE_MANAGER", "5000", requester="USR-001")
    assert found == ["The requester cannot approve their own request."]


def test_inactive_approver_is_refused(approvals):
    inactive = Approver("USR-001", "FINANCE_MANAGER", Decimal("100000"), False)
    assert problems(approvals, inactive, "FINANCE_MANAGER", "5000")
