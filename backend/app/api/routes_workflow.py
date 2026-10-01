"""Invoices, agent runs, payment requests and human decisions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api import presenters
from app.api.schemas import AnalyzeRequest, DecisionRequest, ManualPaymentRequest
from app.container import Services
from app.errors import NotFoundError
from app.models.db import (
    ActionRow,
    AgentRunRow,
    ContractRow,
    InvoiceRow,
    PurchaseOrderRow,
    SupplierRow,
    UserRow,
)
from app.models.domain import ActionStatus
from app.security.auth import current_user, get_services, require_roles

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


@router.get("/invoices")
def list_invoices(services: Services = Depends(get_services)) -> list[dict[str, Any]]:
    session = services.session
    result = []
    for row in session.scalars(select(InvoiceRow).order_by(InvoiceRow.id)):
        supplier = session.get(SupplierRow, row.supplier_id)
        latest = session.scalars(
            select(ActionRow)
            .where(ActionRow.invoice_id == row.id, ActionRow.action_type == "PAY_SUPPLIER")
            .order_by(ActionRow.created_at.desc())
            .limit(1)
        ).first()
        result.append(
            {
                **presenters.invoice(row),
                "supplier_name": supplier.name if supplier else None,
                "latest_action_status": latest.status if latest else None,
            }
        )
    return result


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    session = services.session
    row = session.get(InvoiceRow, invoice_id)
    if row is None:
        raise NotFoundError(f"Invoice {invoice_id} not found.")
    contract = next(
        (
            c
            for c in session.scalars(
                select(ContractRow).where(ContractRow.supplier_id == row.supplier_id)
            )
            if row.purchase_order_id in c.purchase_order_ids
        ),
        None,
    )
    latest_run = session.scalars(
        select(AgentRunRow)
        .where(AgentRunRow.invoice_id == row.id)
        .order_by(AgentRunRow.created_at.desc())
        .limit(1)
    ).first()
    return {
        "invoice": presenters.invoice(row),
        "supplier": presenters.supplier(session.get(SupplierRow, row.supplier_id)),
        "purchase_order": presenters.purchase_order(
            session.get(PurchaseOrderRow, row.purchase_order_id)
        ),
        "contract": presenters.contract(contract),
        "actions": presenters.actions_for(session, invoice_id=row.id),
        "latest_run": presenters.agent_run(session, latest_run) if latest_run else None,
    }


@router.post("/agent/analyze")
def analyze(
    body: AnalyzeRequest,
    services: Services = Depends(get_services),
    user: UserRow = Depends(current_user),
) -> dict[str, Any]:
    run = services.agent_runs.run(body.invoice_id, user)
    return presenters.agent_run(services.session, run)


@router.get("/agent/runs")
def list_runs(services: Services = Depends(get_services)) -> list[dict[str, Any]]:
    rows = services.session.scalars(
        select(AgentRunRow).order_by(AgentRunRow.created_at.desc()).limit(50)
    )
    return [presenters.agent_run(services.session, row) for row in rows]


@router.get("/agent/runs/{run_id}")
def get_run(run_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    row = services.session.get(AgentRunRow, run_id)
    if row is None:
        raise NotFoundError(f"Run {run_id} not found.")
    return presenters.agent_run(services.session, row)


@router.post("/payments/manual")
def manual_payment(
    body: ManualPaymentRequest,
    services: Services = Depends(get_services),
    user: UserRow = Depends(current_user),
) -> dict[str, Any]:
    row = services.manual.submit(
        user, body.invoice_id, amount=body.amount, supplier_id=body.supplier_id
    )
    return presenters.action(services.session, row)


@router.get("/actions")
def list_actions(
    status: ActionStatus | None = Query(default=None),
    services: Services = Depends(get_services),
) -> list[dict[str, Any]]:
    filters = {"status": status.value} if status else {}
    return presenters.actions_for(services.session, **filters)


@router.get("/approvals/pending")
def pending_approvals(services: Services = Depends(get_services)) -> list[dict[str, Any]]:
    session = services.session
    pending = presenters.actions_for(session, status=ActionStatus.PENDING_APPROVAL.value)
    for item in pending:
        invoice = session.get(InvoiceRow, item["invoice_id"]) if item["invoice_id"] else None
        supplier = session.get(SupplierRow, invoice.supplier_id) if invoice else None
        run = session.get(AgentRunRow, item["run_id"]) if item["run_id"] else None
        item["invoice"] = presenters.invoice(invoice) if invoice else None
        item["supplier"] = presenters.supplier(supplier)
        item["analysis"] = (
            {
                k: run.analysis[k]
                for k in ("recommendation", "confidence", "reasoning_summary",
                          "retrieved_sources", "warnings")
            }
            if run
            else None
        )
    return pending


@router.get("/actions/{action_id}")
def get_action(action_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    row = services.session.get(ActionRow, action_id)
    if row is None:
        raise NotFoundError(f"Action {action_id} not found.")
    return presenters.action(services.session, row)


@router.post("/actions/{action_id}/approve")
def approve(
    action_id: str,
    body: DecisionRequest,
    services: Services = Depends(get_services),
    user: UserRow = Depends(current_user),
) -> dict[str, Any]:
    # Whether this user may approve this action is decided by the approval
    # engine, which knows the amount and the required role. Not by the route.
    row = services.workflow.decide(action_id, user, approve=True, comment=body.comment)
    return presenters.action(services.session, row)


@router.post("/actions/{action_id}/reject")
def reject(
    action_id: str,
    body: DecisionRequest,
    services: Services = Depends(get_services),
    user: UserRow = Depends(current_user),
) -> dict[str, Any]:
    row = services.workflow.decide(action_id, user, approve=False, comment=body.comment)
    return presenters.action(services.session, row)


@router.post("/actions/{action_id}/execute")
def retry_execution(
    action_id: str,
    services: Services = Depends(get_services),
    _: UserRow = Depends(require_roles("FINANCE_MANAGER", "CFO")),
) -> dict[str, Any]:
    """Retries an action that is authorised but could not run (e.g. ledger outage)."""
    row = services.workflow.execute(action_id)
    return presenters.action(services.session, row)
