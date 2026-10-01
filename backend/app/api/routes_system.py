"""Status, kill switch, identities and the agent passport."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api import presenters
from app.api.schemas import AIModeRequest
from app.container import AppContainer, Services
from app.errors import LedgerUnavailableError, NotFoundError
from app.models.db import ActionRow, AgentRow, ReceiptRow, UserRow
from app.models.domain import ActionStatus
from app.observability.metrics import collect_metrics
from app.security.auth import current_user, get_container, get_services, require_roles
from app.security.hashing import id_hash, money_str

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/users")
def list_users(services: Services = Depends(get_services)) -> list[dict[str, Any]]:
    """Public on purpose: it feeds the mock identity picker."""
    return [presenters.user(u) for u in services.session.scalars(select(UserRow).order_by(UserRow.id))]


@router.get("/system")
def system(
    container: AppContainer = Depends(get_container),
    services: Services = Depends(get_services),
    _: UserRow = Depends(current_user),
) -> dict[str, Any]:
    return {
        "ai_enabled": services.state.ai_enabled(),
        "demo_mode": container.settings.demo_mode,
        "policy_version": container.rules.version,
        "policy_hash": container.rules.policy_hash,
        "llm": {"provider": container.llm.name, "model": container.llm.model},
        "ledger": asdict(container.ledger.info()),
    }


@router.post("/system/ai-mode")
def set_ai_mode(
    body: AIModeRequest,
    services: Services = Depends(get_services),
    user: UserRow = Depends(require_roles("FINANCE_MANAGER", "CFO")),
) -> dict[str, bool]:
    services.state.set_ai_enabled(body.enabled)
    services.audit.record(
        "AI_MODE_CHANGED", actor=user.id, subject="system", enabled=body.enabled
    )
    services.session.commit()
    return {"ai_enabled": body.enabled}


def _count(services: Services, *conditions: Any) -> int:
    return services.session.scalar(select(func.count()).select_from(ActionRow).where(*conditions)) or 0


@router.get("/overview")
def overview(
    services: Services = Depends(get_services), _: UserRow = Depends(current_user)
) -> dict[str, Any]:
    session = services.session
    metrics = collect_metrics(session)
    return {
        "ai_enabled": services.state.ai_enabled(),
        "active_agents": session.scalar(
            select(func.count()).select_from(AgentRow).where(AgentRow.status == "ACTIVE")
        ),
        "pending_approvals": _count(services, ActionRow.status == ActionStatus.PENDING_APPROVAL),
        "executed_actions": _count(services, ActionRow.status == ActionStatus.EXECUTED),
        "blocked_actions": _count(
            services, ActionRow.status.in_([ActionStatus.DENIED, ActionStatus.REJECTED])
        ),
        "verified_receipts": metrics["verified_receipts"],
        "total_receipts": session.scalar(select(func.count()).select_from(ReceiptRow)),
        "metrics": metrics,
    }


@router.get("/metrics")
def metrics(
    services: Services = Depends(get_services), _: UserRow = Depends(current_user)
) -> dict[str, int]:
    return collect_metrics(services.session)


@router.get("/agents/{agent_id}/passport")
def passport(
    agent_id: str,
    container: AppContainer = Depends(get_container),
    services: Services = Depends(get_services),
    _: UserRow = Depends(current_user),
) -> dict[str, Any]:
    agent = services.session.get(AgentRow, agent_id)
    if agent is None:
        raise NotFoundError(f"Agent {agent_id} not found.")

    ledger = container.ledger
    info = ledger.info()
    agent_hash = id_hash("agent", agent.id)
    onchain_permissions: dict[str, bool] = {}
    try:
        record = ledger.get_agent(agent_hash)
        if record is None:
            registration = "NOT_REGISTERED"
        else:
            registration = "VERIFIED" if record.active else "DEACTIVATED"
            # Forbidden actions are queried too: the chain should say "no" for each.
            for permission in [*agent.allowed_actions, *agent.forbidden_actions]:
                onchain_permissions[permission] = ledger.is_authorized(
                    agent_hash, id_hash("permission", permission)
                )
    except LedgerUnavailableError:
        registration = "UNAVAILABLE"

    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "version": agent.version,
        "status": agent.status,
        "allowed_actions": agent.allowed_actions,
        "forbidden_actions": agent.forbidden_actions,
        "autonomous_payment_limit": money_str(agent.autonomous_payment_limit),
        "human_approval_above": money_str(agent.autonomous_payment_limit),
        "policy": agent.policy,
        "agent_hash": agent_hash,
        "blockchain": {
            "registration": registration,
            "onchain_permissions": onchain_permissions,
            "contract_address": info.contract_address,
            "ledger_mode": info.mode,
            "chain_id": info.chain_id,
        },
    }
