"""Allow-list permission checks. Anything not granted is denied."""

from __future__ import annotations

from app.governance.rules import PolicyRules
from app.models.domain import Check, CheckStatus, Principal, PrincipalKind, ProposedAction


class PermissionEngine:
    def __init__(self, rules: PolicyRules) -> None:
        self._rules = rules

    def check(self, action: ProposedAction, principal: Principal | None) -> list[Check]:
        required = self._rules.action_permissions.get(action.action_type)
        if required is None:
            # An action nobody defined. A model can emit any string; only known ones proceed.
            return [
                Check(
                    name="action_known",
                    status=CheckStatus.FAIL,
                    detail=f"{action.action_type!r} is not a defined action.",
                    policy_ref="AI Agent Policy §2",
                )
            ]
        checks = [
            Check(
                name="action_known",
                status=CheckStatus.PASS,
                detail=f"{action.action_type} requires the {required} permission.",
            )
        ]
        if principal is None:
            return checks

        label = "Agent" if principal.kind is PrincipalKind.AGENT else "User"
        if required in principal.forbidden:
            detail = f"{label} {principal.id} is explicitly forbidden from {required}."
            granted = False
        elif required not in principal.permissions:
            detail = f"{label} {principal.id} does not possess {required} permission."
            granted = False
        else:
            detail = f"{label} {principal.id} holds {required}."
            granted = True
        checks.append(
            Check(
                name="permission",
                status=CheckStatus.PASS if granted else CheckStatus.FAIL,
                detail=detail,
                policy_ref="Security Policy §1",
            )
        )
        if granted and action.action_type not in self._rules.executable_actions:
            checks.append(
                Check(
                    name="action_executable",
                    status=CheckStatus.FAIL,
                    detail=f"No execution path exists for {action.action_type} in this system.",
                )
            )
        return checks
