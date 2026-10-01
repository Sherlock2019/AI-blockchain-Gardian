"""Receipts, verification, audit trail, and the demo-only tamper controls."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api import presenters
from app.api.schemas import TamperRequest
from app.container import AppContainer, Services
from app.errors import ForbiddenError, LedgerUnavailableError
from app.models.db import ReceiptRow
from app.security.auth import current_user, get_container, get_services
from app.services.receipts import compute_receipt_hash

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


def demo_only(container: AppContainer = Depends(get_container)) -> None:
    if not container.settings.demo_mode:
        raise ForbiddenError("Demo controls are disabled (DEMO_MODE=false).")


@router.get("/receipts")
def list_receipts(services: Services = Depends(get_services)) -> list[dict[str, Any]]:
    rows = services.session.scalars(select(ReceiptRow).order_by(ReceiptRow.seq.desc()))
    return [presenters.receipt(row) for row in rows]


@router.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    return presenters.receipt(services.receipts.get(receipt_id))


@router.post("/receipts/{receipt_id}/verify")
def verify_receipt(receipt_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    return services.receipts.verify(receipt_id)


@router.post("/receipts/{receipt_id}/anchor")
def anchor_receipt(receipt_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    """Retries anchoring for a receipt whose hash is not yet on the ledger."""
    return presenters.receipt(services.receipts.anchor(services.receipts.get(receipt_id)))


@router.get("/ledger/records")
def ledger_records(
    container: AppContainer = Depends(get_container),
    services: Services = Depends(get_services),
) -> list[dict[str, Any]]:
    """Each receipt next to what the ledger currently holds for it."""
    records = []
    for row in services.session.scalars(select(ReceiptRow).order_by(ReceiptRow.seq.desc())):
        onchain_hash: str | None = None
        onchain_block: int | None = None
        reachable = True
        try:
            record = container.ledger.get_execution(row.action_hash)
            if record is not None:
                onchain_hash, onchain_block = record.receipt_hash, record.block_number
        except LedgerUnavailableError:
            reachable = False
        recomputed = compute_receipt_hash(row.payload)
        records.append(
            {
                "receipt_id": row.receipt_id,
                "invoice_id": row.payload.get("invoice_id"),
                "action_hash": row.action_hash,
                "receipt_hash": recomputed,
                "onchain_hash": onchain_hash,
                "block_number": onchain_block,
                "blockchain_tx_hash": row.blockchain_tx_hash,
                "anchor_status": row.anchor_status,
                "ledger_reachable": reachable,
                "matches": onchain_hash == recomputed if onchain_hash else None,
            }
        )
    return records


@router.get("/audit")
def audit_trail(
    limit: int = Query(default=200, ge=1, le=1000),
    correlation_id: str | None = Query(default=None, max_length=64),
    services: Services = Depends(get_services),
) -> list[dict[str, Any]]:
    return [presenters.audit_event(e) for e in services.audit.list(limit, correlation_id)]


@router.get("/audit/verify")
def verify_audit_chain(services: Services = Depends(get_services)) -> dict[str, Any]:
    return services.audit.verify_chain()


@router.post("/demo/receipts/{receipt_id}/tamper", dependencies=[Depends(demo_only)])
def tamper_receipt(
    receipt_id: str, body: TamperRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    row = services.receipts.tamper(receipt_id, recompute_hash=body.recompute_hash)
    return presenters.receipt(row)


@router.post("/demo/receipts/{receipt_id}/restore", dependencies=[Depends(demo_only)])
def restore_receipt(receipt_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    return presenters.receipt(services.receipts.restore(receipt_id))


@router.post("/demo/reset", dependencies=[Depends(demo_only)])
def reset_demo(
    container: AppContainer = Depends(get_container),
    services: Services = Depends(get_services),
) -> dict[str, str]:
    services.session.close()
    container.reset()
    return {"status": "reset"}
