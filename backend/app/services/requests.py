"""The two ways a payment request enters the workflow: the agent, or a person."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.agents.llm import LLMProvider
from app.agents.tools import ToolGateway
from app.agents.treasury_agent import TreasuryAgent
from app.errors import AIDisabledError, ForbiddenError, NotFoundError
from app.governance.facts import FactLoader
from app.models.db import ActionRow, AgentRunRow, InvoiceRow, UserRow
from app.models.domain import (
    PAY_SUPPLIER,
    Origin,
    PrincipalKind,
    ProposedAction,
    dump,
    new_id,
    utc_now_iso,
)
from app.observability import metrics
from app.observability.audit import AuditLog
from app.observability.logging import get_correlation_id
from app.rag.retriever import Retriever
from app.services.state import SystemState
from app.services.workflow import PaymentWorkflow

DEFAULT_AGENT_ID = "AGENT-TREASURY-001"


class AgentRunService:
    def __init__(
        self,
        session: Session,
        llm: LLMProvider,
        retriever: Retriever,
        facts: FactLoader,
        workflow: PaymentWorkflow,
        audit: AuditLog,
    ) -> None:
        self._session = session
        self._llm = llm
        self._retriever = retriever
        self._facts = facts
        self._workflow = workflow
        self._audit = audit

    def run(self, invoice_id: str, requested_by: UserRow, agent_id: str = DEFAULT_AGENT_ID) -> AgentRunRow:
        if not SystemState(self._session).ai_enabled():
            self._audit.record(
                "AGENT_RUN_REFUSED", actor=requested_by.id, subject=invoice_id, reason="AI mode is OFF"
            )
            self._session.commit()
            raise AIDisabledError("AI mode is OFF. Use the manual workflow for this invoice.")

        principal = self._facts.principal(PrincipalKind.AGENT, agent_id)
        if principal is None or not principal.active:
            raise ForbiddenError(f"Agent {agent_id} is not registered or not active.")

        tools = ToolGateway(principal, self._session, self._retriever, self._audit)
        analysis = TreasuryAgent(principal, self._llm, tools).analyze(invoice_id)

        run = AgentRunRow(
            id=analysis.run_id,
            invoice_id=invoice_id,
            correlation_id=get_correlation_id(),
            requested_by=requested_by.id,
            analysis=dump(analysis),
            created_at=utc_now_iso(),
        )
        self._session.add(run)
        self._audit.record(
            metrics.AGENT_RUN,
            actor=principal.id,
            subject=analysis.run_id,
            invoice_id=invoice_id,
            requested_by=requested_by.id,
            recommendation=analysis.recommendation.value,
            sources=[s.source_id for s in analysis.retrieved_sources],
            requested=[a.action_type for a in analysis.proposed_actions],
        )
        self._session.commit()

        # The hand-off. From here the agent has no further say.
        self._workflow.submit(list(analysis.proposed_actions))
        return run


class ManualRequestService:
    """A person files the same request the agent would, with no model involved."""

    def __init__(self, session: Session, workflow: PaymentWorkflow) -> None:
        self._session = session
        self._workflow = workflow

    def submit(
        self,
        user: UserRow,
        invoice_id: str,
        *,
        amount: Decimal | None = None,
        supplier_id: str | None = None,
    ) -> ActionRow:
        invoice = self._session.get(InvoiceRow, invoice_id)
        if invoice is None:
            raise NotFoundError(f"Invoice {invoice_id} not found.")
        # Values the person typed are claims too, checked by the same control.
        action = ProposedAction(
            action_id=new_id("ACT"),
            action_type=PAY_SUPPLIER,
            principal_kind=PrincipalKind.HUMAN,
            principal_id=user.id,
            origin=Origin.MANUAL,
            invoice_id=invoice.id,
            supplier_id=supplier_id or invoice.supplier_id,
            purchase_order_id=invoice.purchase_order_id,
            amount=amount if amount is not None else invoice.amount,
            evidence_ids=(
                f"invoice:{invoice.id}",
                f"supplier:{invoice.supplier_id}",
                f"po:{invoice.purchase_order_id}",
            ),
        )
        return self._workflow.submit([action])[0]
