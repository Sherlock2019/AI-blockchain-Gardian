"""Who must approve, and whether a given person may."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.governance.rules import PolicyRules
from app.models.domain import Check, CheckStatus, RiskLevel
from app.security.hashing import money_str


@dataclass(frozen=True)
class Approver:
    user_id: str
    role: str
    approval_limit: Decimal
    active: bool


class ApprovalEngine:
    def __init__(self, rules: PolicyRules) -> None:
        self._rules = rules

    def required_role(
        self, amount: Decimal, risk: RiskLevel, checks: Sequence[Check]
    ) -> str | None:
        """The role that must sign off, or None when the action may proceed alone."""
        escalated = any(c.status is CheckStatus.ESCALATE for c in checks) or risk in (
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        )
        if not escalated:
            return None
        return self._rules.role_for_amount(amount) or self._rules.lowest_approver_role

    def approver_problems(
        self,
        approver: Approver,
        *,
        required_role: str,
        amount: Decimal,
        requester_id: str,
    ) -> list[str]:
        """Reasons this person may not decide this action. Empty means they may."""
        problems: list[str] = []
        if not approver.active:
            problems.append(f"{approver.user_id} is not an active user.")
        if self._rules.rank(approver.role) < self._rules.rank(required_role):
            problems.append(f"Role {approver.role} cannot act where {required_role} is required.")
        if approver.approval_limit < amount:
            problems.append(
                f"Approval limit {money_str(approver.approval_limit)} is below the "
                f"amount {money_str(amount)}."
            )
        if approver.user_id == requester_id:
            problems.append("The requester cannot approve their own request.")
        return problems
