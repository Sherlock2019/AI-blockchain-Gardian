"""Value objects passed between layers. No persistence, no I/O."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

from app.security.hashing import hash_object, money_str


def _two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


Money = Annotated[
    Decimal,
    AfterValidator(_two_places),
    PlainSerializer(money_str, return_type=str),
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"  # blocks the action
    ESCALATE = "ESCALATE"  # does not block, but a human must approve


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    DENIED = "DENIED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


IN_FLIGHT_STATUSES = (
    ActionStatus.PENDING_APPROVAL,
    ActionStatus.AUTHORIZED,
    ActionStatus.EXECUTING,
)


class PrincipalKind(StrEnum):
    AGENT = "AGENT"
    HUMAN = "HUMAN"


class Origin(StrEnum):
    AI = "AI"
    MANUAL = "MANUAL"


class Recommendation(StrEnum):
    PAYMENT_RECOMMENDED = "PAYMENT_RECOMMENDED"
    PAYMENT_NOT_RECOMMENDED = "PAYMENT_NOT_RECOMMENDED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


PAY_SUPPLIER = "PAY_SUPPLIER"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Principal(Frozen):
    """Who is asking. An AI agent and a human requester are evaluated by the same rules."""

    kind: PrincipalKind
    id: str
    name: str
    role: str
    active: bool
    permissions: frozenset[str]
    forbidden: frozenset[str] = frozenset()
    autonomous_limit: Money
    version: str | None = None


class ProposedAction(Frozen):
    """A request to do something. Every field below `origin` is a claim to be checked."""

    action_id: str
    action_type: str
    principal_kind: PrincipalKind
    principal_id: str
    origin: Origin
    invoice_id: str | None = None
    supplier_id: str | None = None
    purchase_order_id: str | None = None
    amount: Money | None = None
    params: dict[str, str] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    recommendation: Recommendation | None = None
    run_id: str | None = None

    def action_hash(self) -> str:
        """Identity of this request. Approvals and on-chain records bind to it."""
        return hash_object(
            {
                "action_id": self.action_id,
                "action_type": self.action_type,
                "principal_kind": self.principal_kind.value,
                "principal_id": self.principal_id,
                "origin": self.origin.value,
                "invoice_id": self.invoice_id,
                "supplier_id": self.supplier_id,
                "purchase_order_id": self.purchase_order_id,
                "amount": money_str(self.amount) if self.amount is not None else None,
                "params": dict(self.params),
            }
        )


class InvoiceFact(Frozen):
    id: str
    supplier_id: str
    purchase_order_id: str
    amount: Money
    status: str


class SupplierFact(Frozen):
    id: str
    name: str
    status: str
    risk: str
    payment_limit: Money


class PurchaseOrderFact(Frozen):
    id: str
    supplier_id: str
    approved_amount: Money
    status: str


class Facts(Frozen):
    """What the system of record says. Loaded by governance, never supplied by the requester."""

    principal: Principal | None
    ai_enabled: bool
    invoice: InvoiceFact | None = None
    supplier: SupplierFact | None = None
    purchase_order: PurchaseOrderFact | None = None
    paid_against_po: Money = Decimal("0")
    invoice_already_paid: bool = False
    in_flight_action_id: str | None = None
    unresolved_evidence_ids: tuple[str, ...] = ()
    untrusted_content_flagged: bool = False
    run_compromised: bool = False


class Check(Frozen):
    name: str
    status: CheckStatus
    detail: str
    policy_ref: str | None = None


class GovernanceDecision(Frozen):
    decision_id: str
    action_id: str
    agent_id: str
    requested_action: str
    risk_level: RiskLevel
    risk_factors: tuple[str, ...]
    permission_checks: tuple[Check, ...]
    policy_checks: tuple[Check, ...]
    required_approval: str | None
    decision: Decision
    reasons: tuple[str, ...]
    policy_version: str
    policy_hash: str
    evaluated_at: str

    @property
    def permission_denied(self) -> bool:
        return any(c.status is CheckStatus.FAIL for c in self.permission_checks)

    def failed(self, name: str) -> bool:
        return any(
            c.name == name and c.status is CheckStatus.FAIL
            for c in (*self.permission_checks, *self.policy_checks)
        )


class PaymentResult(Frozen):
    transaction_id: str
    invoice_id: str
    supplier_id: str
    amount: Money
    status: str
    timestamp: str


class RetrievedSource(Frozen):
    source_id: str
    kind: str
    title: str
    snippet: str
    score: float | None = None


class TraceStep(Frozen):
    stage: str
    title: str
    detail: str
    status: str = "DONE"
    timestamp: str = Field(default_factory=utc_now_iso)


class AgentAnalysis(Frozen):
    run_id: str
    invoice_id: str
    agent_id: str
    recommendation: Recommendation
    confidence: float
    reasoning_summary: str
    retrieved_sources: tuple[RetrievedSource, ...]
    policy_references: tuple[str, ...]
    warnings: tuple[str, ...]
    model_provider: str
    model_name: str
    proposed_actions: tuple[ProposedAction, ...]
    trace: tuple[TraceStep, ...]


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
