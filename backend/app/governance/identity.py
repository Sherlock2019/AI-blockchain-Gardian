"""Who is asking, and are they allowed to ask at all right now?"""

from __future__ import annotations

from app.models.domain import Check, CheckStatus, Facts, PrincipalKind, ProposedAction


class AgentIdentityService:
    def check(self, action: ProposedAction, facts: Facts) -> list[Check]:
        principal = facts.principal
        if principal is None:
            return [
                Check(
                    name="identity_valid",
                    status=CheckStatus.FAIL,
                    detail=f"Unknown {action.principal_kind.value.lower()} {action.principal_id}.",
                    policy_ref="AI Agent Policy §2",
                )
            ]

        checks = [
            Check(
                name="identity_valid",
                status=CheckStatus.PASS if principal.active else CheckStatus.FAIL,
                detail=(
                    f"{principal.name} ({principal.id}) is active."
                    if principal.active
                    else f"{principal.name} ({principal.id}) is not active."
                ),
                policy_ref="AI Agent Policy §2",
            )
        ]
        if principal.kind is PrincipalKind.AGENT:
            checks.append(
                Check(
                    name="ai_mode_enabled",
                    status=CheckStatus.PASS if facts.ai_enabled else CheckStatus.FAIL,
                    detail=(
                        "AI mode is ON."
                        if facts.ai_enabled
                        else "AI mode is OFF. Agent requests are refused; use the manual workflow."
                    ),
                    policy_ref="AI Agent Policy §6",
                )
            )
        return checks
