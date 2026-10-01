"""The decision gate: a pure function of a request and the facts on record."""

from __future__ import annotations

from decimal import Decimal

from app.governance.approval import ApprovalEngine
from app.governance.identity import AgentIdentityService
from app.governance.permissions import PermissionEngine
from app.governance.policy import PolicyEngine
from app.governance.risk import RiskEngine
from app.governance.rules import PolicyRules
from app.models.domain import (
    PAY_SUPPLIER,
    Check,
    CheckStatus,
    Decision,
    Facts,
    GovernanceDecision,
    ProposedAction,
    new_id,
    utc_now_iso,
)


class GovernanceEngine:
    def __init__(self, rules: PolicyRules) -> None:
        self.rules = rules
        self._identity = AgentIdentityService()
        self._permissions = PermissionEngine(rules)
        self._policy = PolicyEngine()
        self._risk = RiskEngine(rules)
        self.approvals = ApprovalEngine(rules)

    def evaluate(self, action: ProposedAction, facts: Facts) -> GovernanceDecision:
        permission_checks: list[Check] = [
            *self._identity.check(action, facts),
            *self._permissions.check(action, facts.principal),
        ]
        permitted = all(c.status is CheckStatus.PASS for c in permission_checks)

        # Business checks only run for a requester who is allowed to ask.
        policy_checks: list[Check] = []
        if permitted and action.action_type == PAY_SUPPLIER:
            policy_checks = self._policy.check_payment(action, facts)

        all_checks = [*permission_checks, *policy_checks]
        risk, factors = self._risk.assess(action, facts, all_checks)
        failures = [c for c in all_checks if c.status is CheckStatus.FAIL]

        required_role: str | None = None
        if failures:
            decision = Decision.DENY
            reasons = tuple(c.detail for c in failures)
        else:
            amount = facts.invoice.amount if facts.invoice else Decimal("0")
            required_role = self.approvals.required_role(amount, risk, all_checks)
            if required_role:
                decision = Decision.REQUIRE_APPROVAL
                reasons = tuple(
                    c.detail for c in all_checks if c.status is CheckStatus.ESCALATE
                ) or (f"Risk level {risk.value} requires human approval.",)
            else:
                decision = Decision.ALLOW
                reasons = ("All controls passed within the autonomous limit.",)

        return GovernanceDecision(
            decision_id=new_id("DEC"),
            action_id=action.action_id,
            agent_id=action.principal_id,
            requested_action=action.action_type,
            risk_level=risk,
            risk_factors=factors,
            permission_checks=tuple(permission_checks),
            policy_checks=tuple(policy_checks),
            required_approval=required_role,
            decision=decision,
            reasons=reasons,
            policy_version=self.rules.version,
            policy_hash=self.rules.policy_hash,
            evaluated_at=utc_now_iso(),
        )
