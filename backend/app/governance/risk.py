"""Deterministic risk scoring. Risk informs the approver and can force escalation."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.governance.rules import PolicyRules
from app.models.domain import Check, CheckStatus, Facts, ProposedAction, RiskLevel

_LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
_SUPPLIER_BUMP = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


class RiskEngine:
    def __init__(self, rules: PolicyRules) -> None:
        self._rules = rules

    def assess(
        self, action: ProposedAction, facts: Facts, checks: Sequence[Check]
    ) -> tuple[RiskLevel, tuple[str, ...]]:
        if any(c.status is CheckStatus.FAIL for c in checks):
            failed = [c.name for c in checks if c.status is CheckStatus.FAIL]
            return RiskLevel.CRITICAL, tuple(f"control failed: {name}" for name in failed)

        factors: list[str] = []
        amount = facts.invoice.amount if facts.invoice else (action.amount or Decimal("0"))
        tiers_exceeded = sum(1 for tier in self._rules.approval_tiers if amount > tier.above)
        score = tiers_exceeded
        if tiers_exceeded:
            factors.append(f"amount exceeds {tiers_exceeded} approval threshold(s)")

        if facts.supplier is not None:
            bump = _SUPPLIER_BUMP.get(facts.supplier.risk, 2)
            if bump:
                score += bump
                factors.append(f"supplier risk rating {facts.supplier.risk}")

        if facts.untrusted_content_flagged:
            score = max(score, _LEVELS.index(RiskLevel.HIGH))
            factors.append("instruction-like text in invoice")

        level = _LEVELS[min(score, _LEVELS.index(RiskLevel.HIGH))]
        return level, tuple(factors) or ("no risk factors",)
