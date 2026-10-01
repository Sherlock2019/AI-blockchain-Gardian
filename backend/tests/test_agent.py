"""The agent with models that behave, misbehave, and break."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.agents.tools import ToolGateway
from app.agents.treasury_agent import TreasuryAgent
from app.container import AppContainer, Services
from app.errors import ForbiddenError, NotFoundError
from app.models.db import ActionRow, PaymentRow
from app.models.domain import PrincipalKind, Recommendation
from tests.conftest import AGENT_ID, CAROL, agent_principal, get_user


class ScriptedLLM:
    """A model that says whatever the test tells it to."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, reply: str | Exception) -> None:
        self._reply = reply
        self.prompts: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


def answer(**overrides: object) -> str:
    body: dict[str, object] = {
        "recommendation": "PAYMENT_RECOMMENDED",
        "confidence": 0.9,
        "reasoning_summary": "Looks fine.",
        "policy_references": [],
        "requested_actions": [{"action_type": "PAY_SUPPLIER"}],
    }
    body.update(overrides)
    return json.dumps(body)


def agent_for(services: Services, container: AppContainer, llm: object) -> TreasuryAgent:
    principal = services.facts.principal(PrincipalKind.AGENT, AGENT_ID)
    tools = ToolGateway(principal, services.session, container.retriever, services.audit)
    return TreasuryAgent(principal, llm, tools)  # type: ignore[arg-type]


def run_with(container: AppContainer, services: Services, llm: object, invoice_id: str) -> list[ActionRow]:
    container.llm = llm  # type: ignore[assignment]
    fresh = container.services(services.session)
    run = fresh.agent_runs.run(invoice_id, get_user(services, CAROL))
    return list(services.session.scalars(select(ActionRow).where(ActionRow.run_id == run.id)))


# ---- recommendation and evidence --------------------------------------------

def test_recommendation_carries_evidence_and_policy_references(services, container):
    analysis = agent_for(services, container, container.llm).analyze("INV-2026-0042")
    assert analysis.recommendation is Recommendation.PAYMENT_RECOMMENDED
    assert 0 < analysis.confidence <= 1
    assert "PO-9821" in analysis.reasoning_summary
    assert "autonomous agent limit" in analysis.reasoning_summary

    sources = {s.source_id for s in analysis.retrieved_sources}
    assert {"invoice:INV-2026-0042", "supplier:SUP-001", "po:PO-9821", "contract:CTR-2025-011"} <= sources
    assert "policy:payment_policy#3" in sources
    assert analysis.policy_references
    assert [t.stage for t in analysis.trace] == ["OBSERVE", "RETRIEVE", "ANALYZE", "RECOMMEND"]


def test_citations_come_from_tool_calls_not_from_the_model(services, container):
    llm = ScriptedLLM(answer(policy_references=["Invented Policy §99"]))
    analysis = agent_for(services, container, llm).analyze("INV-2026-0042")
    assert not any("Invented" in s.title for s in analysis.retrieved_sources)
    assert all(services.facts.evidence_exists(e) for e in analysis.proposed_actions[0].evidence_ids)


def test_supplier_bank_token_never_reaches_the_model(services, container):
    llm = ScriptedLLM(answer())
    agent_for(services, container, llm).analyze("INV-2026-0042")
    system, user = llm.prompts[0]
    assert "MOCK-ACME-001" not in system + user


def test_untrusted_notes_are_delimited_and_kept_out_of_the_facts_block(services, container):
    llm = ScriptedLLM(answer())
    analysis = agent_for(services, container, llm).analyze("INV-2026-0047")
    _, user = llm.prompts[0]
    facts_block = user.split("</facts>")[0]
    assert "IGNORE ALL PREVIOUS" not in facts_block
    assert "<untrusted_document>\nIGNORE ALL PREVIOUS" in user
    assert analysis.warnings


def test_negative_recommendation_for_a_blocked_supplier(services, container):
    analysis = agent_for(services, container, container.llm).analyze("INV-2026-0045")
    assert analysis.recommendation is Recommendation.PAYMENT_NOT_RECOMMENDED
    assert "BLOCKED" in analysis.reasoning_summary


def test_unknown_invoice(services, container):
    with pytest.raises(NotFoundError):
        agent_for(services, container, container.llm).analyze("INV-NOPE")


# ---- tool boundary ----------------------------------------------------------

def test_tool_gateway_has_no_write_or_payment_tools(services, container):
    tools = ToolGateway(agent_principal(), services.session, container.retriever, services.audit)
    public = {name for name in dir(tools) if not name.startswith("_")}
    assert public == {
        "read_invoice", "read_supplier", "read_purchase_order", "read_payment_history",
        "search_policy", "sources",
    }
    assert not any(word in name for name in public for word in ("pay_", "execute", "update", "change"))


def test_agent_reads_payment_history_and_cites_it(services, container):
    analysis = agent_for(services, container, container.llm).analyze("INV-2026-0040")
    history = next(s for s in analysis.retrieved_sources if s.kind == "payment_history")
    assert "MOCK-TX-SEED" in history.snippet
    assert analysis.recommendation is Recommendation.PAYMENT_NOT_RECOMMENDED
    assert "already been made" in analysis.reasoning_summary


def test_tool_calls_are_checked_against_agent_permissions(services, container):
    limited = agent_principal(permissions=frozenset({"READ_INVOICE"}))
    tools = ToolGateway(limited, services.session, container.retriever, services.audit)
    assert tools.read_invoice("INV-2026-0042") is not None
    with pytest.raises(ForbiddenError, match="READ_SUPPLIER"):
        tools.read_supplier("SUP-001")
    assert any(e.event_type == "TOOL_CALL_DENIED" for e in services.audit.list())


# ---- a model that is wrong --------------------------------------------------

def test_hallucinated_amount_is_denied_by_governance(services, container):
    llm = ScriptedLLM(answer(requested_actions=[{"action_type": "PAY_SUPPLIER", "amount": "55000"}]))
    (action,) = run_with(container, services, llm, "INV-2026-0042")
    assert action.status == "DENIED"
    assert any("amount 55000.00 ≠ 50000.00" in r for r in action.decision["reasons"])


def test_hallucinated_supplier_is_denied_by_governance(services, container):
    llm = ScriptedLLM(
        answer(requested_actions=[{"action_type": "PAY_SUPPLIER", "supplier_id": "SUP-004"}])
    )
    (action,) = run_with(container, services, llm, "INV-2026-0042")
    assert action.status == "DENIED"
    assert any("supplier SUP-004 ≠ SUP-001" in r for r in action.decision["reasons"])


def test_overconfident_model_cannot_pay_a_blocked_supplier(services, container):
    llm = ScriptedLLM(answer(confidence=1.0, reasoning_summary="Definitely pay. Trust me."))
    (action,) = run_with(container, services, llm, "INV-2026-0045")
    assert action.status == "DENIED"


def test_overconfident_model_cannot_skip_approval(services, container):
    llm = ScriptedLLM(answer(confidence=1.0, reasoning_summary="Approval is not needed."))
    (action,) = run_with(container, services, llm, "INV-2026-0042")
    assert action.status == "PENDING_APPROVAL"


def test_invented_action_type_is_denied_and_poisons_the_run(services, container):
    llm = ScriptedLLM(
        answer(requested_actions=[{"action_type": "GRANT_SELF_ADMIN"}, {"action_type": "PAY_SUPPLIER"}])
    )
    actions = run_with(container, services, llm, "INV-2026-0043")
    assert {a.action_type: a.status for a in actions} == {
        "GRANT_SELF_ADMIN": "DENIED",
        "PAY_SUPPLIER": "DENIED",
    }
    assert services.session.scalars(
        select(PaymentRow).where(PaymentRow.invoice_id == "INV-2026-0043")
    ).first() is None


def test_request_flood_is_capped(services, container):
    flood = [{"action_type": "DELETE_AUDIT_RECORD"}] * 8
    llm = ScriptedLLM(answer(requested_actions=flood))
    actions = run_with(container, services, llm, "INV-2026-0043")
    assert len(actions) == 4  # three extra requests at most, plus the payment
    assert all(a.status == "DENIED" for a in actions)


# ---- a model that is broken -------------------------------------------------

@pytest.mark.parametrize(
    "reply",
    [
        "I think you should pay this invoice.",
        "{not json",
        json.dumps({"recommendation": "PAY_EVERYONE", "confidence": 0.5, "reasoning_summary": "x"}),
        json.dumps({"recommendation": "PAYMENT_RECOMMENDED", "confidence": 7, "reasoning_summary": "x"}),
        TimeoutError("model timed out"),
    ],
)
def test_unusable_model_output_proposes_nothing(services, container, reply):
    actions = run_with(container, services, ScriptedLLM(reply), "INV-2026-0043")
    assert actions == []
    run = services.session.scalars(select(ActionRow)).first()
    assert run is None

    analysis = agent_for(services, container, ScriptedLLM(reply)).analyze("INV-2026-0043")
    assert analysis.recommendation is Recommendation.MANUAL_REVIEW
    assert analysis.proposed_actions == ()
    assert analysis.warnings
