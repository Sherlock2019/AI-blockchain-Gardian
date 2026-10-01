"""Machine-readable control configuration.

The thresholds the engine enforces come from `policy_rules.json`, reviewed and
versioned like code. They are *not* derived from the Markdown policies the RAG
pipeline retrieves: prose is for people and for the model's explanation,
this file is what is enforced. Keeping the two in step is a change-control
task, and the policy hash below covers both so a drift in either is visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.security.hashing import hash_object, sha256_hex


@dataclass(frozen=True)
class ApprovalTier:
    above: Decimal
    role: str


@dataclass(frozen=True)
class PolicyRules:
    version: str
    policy_hash: str
    human_autonomous_limit: Decimal
    approval_tiers: tuple[ApprovalTier, ...]
    role_rank: dict[str, int]
    action_permissions: dict[str, str]
    executable_actions: frozenset[str]

    def rank(self, role: str) -> int:
        return self.role_rank.get(role, -1)

    def role_for_amount(self, amount: Decimal) -> str | None:
        """Highest tier whose threshold the amount exceeds, or None below every tier."""
        required: str | None = None
        for tier in self.approval_tiers:
            if amount > tier.above:
                required = tier.role
        return required

    @property
    def lowest_approver_role(self) -> str:
        return self.approval_tiers[0].role


def load_rules(policies_dir: Path) -> PolicyRules:
    raw = json.loads((policies_dir / "policy_rules.json").read_text(encoding="utf-8"))
    documents = {
        path.name: sha256_hex(path.read_text(encoding="utf-8"))
        for path in sorted(policies_dir.glob("*.md"))
    }
    tiers = sorted(
        (ApprovalTier(Decimal(t["above"]), t["role"]) for t in raw["approval_tiers"]),
        key=lambda t: t.above,
    )
    return PolicyRules(
        version=raw["version"],
        policy_hash=hash_object({"rules": raw, "documents": documents}),
        human_autonomous_limit=Decimal(raw["human_autonomous_limit"]),
        approval_tiers=tuple(tiers),
        role_rank=dict(raw["role_rank"]),
        action_permissions=dict(raw["action_permissions"]),
        executable_actions=frozenset(raw["executable_actions"]),
    )
