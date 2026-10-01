"""Deterministic payment controls.

Every check compares the request against the system of record in `Facts`.
Nothing here reads model output except to test it.
"""

from __future__ import annotations

from app.models.domain import (
    Check,
    CheckStatus,
    Facts,
    Origin,
    ProposedAction,
    Recommendation,
)
from app.security.hashing import money_str

P = CheckStatus.PASS
F = CheckStatus.FAIL
E = CheckStatus.ESCALATE


def _check(name: str, ok: bool, passed: str, failed: str, ref: str) -> Check:
    return Check(name=name, status=P if ok else F, detail=passed if ok else failed, policy_ref=ref)


class PolicyEngine:
    def check_payment(self, action: ProposedAction, facts: Facts) -> list[Check]:
        checks: list[Check] = []
        invoice, supplier, po = facts.invoice, facts.supplier, facts.purchase_order

        if facts.run_compromised:
            checks.append(
                Check(
                    name="run_integrity",
                    status=F,
                    detail="The same agent run requested an action outside the agent's scope. "
                    "Every request from that run is refused.",
                    policy_ref="Security Policy §5",
                )
            )

        if invoice is None:
            checks.append(
                Check(
                    name="invoice_exists",
                    status=F,
                    detail=f"Invoice {action.invoice_id} not found.",
                    policy_ref="Payment Policy §2",
                )
            )
            return checks
        checks.append(
            Check(
                name="invoice_exists",
                status=P,
                detail=f"Invoice {invoice.id} found.",
                policy_ref="Payment Policy §2",
            )
        )

        # A paid invoice is reported as a duplicate and nothing else: that is the
        # one fact the operator needs, and the remaining checks would only add noise.
        duplicate_ok = not facts.invoice_already_paid and facts.in_flight_action_id is None
        if facts.invoice_already_paid:
            duplicate_detail = f"Invoice {invoice.id} has already been paid."
        else:
            duplicate_detail = (
                f"Request {facts.in_flight_action_id} for invoice {invoice.id} is already in progress."
            )
        checks.append(
            _check(
                "duplicate_payment",
                duplicate_ok,
                "No prior or in-progress payment for this invoice.",
                duplicate_detail,
                "Payment Policy §4",
            )
        )
        if facts.invoice_already_paid:
            return checks
        checks.append(
            _check(
                "invoice_payable",
                invoice.status == "PENDING",
                "Invoice is PENDING.",
                f"Invoice status is {invoice.status}.",
                "Payment Policy §4",
            )
        )

        # The request's amount and supplier are claims. A hallucinated amount or
        # a swapped supplier fails here regardless of how the request was produced.
        mismatches = []
        if action.supplier_id != invoice.supplier_id:
            mismatches.append(f"supplier {action.supplier_id} ≠ {invoice.supplier_id}")
        if action.amount is None or action.amount != invoice.amount:
            claimed = money_str(action.amount) if action.amount is not None else "none"
            mismatches.append(f"amount {claimed} ≠ {money_str(invoice.amount)}")
        if action.purchase_order_id != invoice.purchase_order_id:
            mismatches.append(f"PO {action.purchase_order_id} ≠ {invoice.purchase_order_id}")
        checks.append(
            _check(
                "request_matches_record",
                not mismatches,
                "Requested supplier, amount and PO match the invoice on record.",
                "Request does not match the invoice on record: " + "; ".join(mismatches) + ".",
                "Payment Policy §2",
            )
        )

        if supplier is None:
            checks.append(
                Check(
                    name="supplier_approved",
                    status=F,
                    detail=f"Supplier {invoice.supplier_id} not found.",
                    policy_ref="Payment Policy §1",
                )
            )
        else:
            checks.append(
                _check(
                    "supplier_approved",
                    supplier.status == "APPROVED",
                    f"Supplier {supplier.id} is APPROVED.",
                    f"Supplier {supplier.id} is {supplier.status}.",
                    "Payment Policy §1",
                )
            )
            checks.append(
                _check(
                    "supplier_limit",
                    invoice.amount <= supplier.payment_limit,
                    f"Amount is within the supplier limit of {money_str(supplier.payment_limit)}.",
                    f"Amount {money_str(invoice.amount)} exceeds the supplier limit of "
                    f"{money_str(supplier.payment_limit)}.",
                    "Payment Policy §1",
                )
            )

        if po is None:
            checks.append(
                Check(
                    name="po_exists",
                    status=F,
                    detail=f"Purchase order {invoice.purchase_order_id} not found.",
                    policy_ref="Payment Policy §2",
                )
            )
        else:
            po_ok = po.status == "APPROVED" and po.supplier_id == invoice.supplier_id
            checks.append(
                _check(
                    "po_exists",
                    po_ok,
                    f"Purchase order {po.id} is APPROVED for supplier {po.supplier_id}.",
                    f"Purchase order {po.id} is {po.status} for supplier {po.supplier_id}.",
                    "Payment Policy §2",
                )
            )
            remaining = po.approved_amount - facts.paid_against_po
            checks.append(
                _check(
                    "invoice_matches_po",
                    invoice.amount <= remaining,
                    f"Amount is within the {money_str(remaining)} remaining on {po.id}.",
                    f"Amount {money_str(invoice.amount)} exceeds the {money_str(remaining)} "
                    f"remaining on {po.id}.",
                    "Payment Policy §2",
                )
            )

        if action.origin is Origin.AI:
            checks.append(self._evidence_check(action, facts))
            if action.recommendation is not Recommendation.PAYMENT_RECOMMENDED:
                # The model's opinion can add scrutiny. It can never remove any.
                checks.append(
                    Check(
                        name="ai_recommendation",
                        status=E,
                        detail="The agent did not recommend payment. A human must decide.",
                        policy_ref="AI Agent Policy §1",
                    )
                )

        if facts.untrusted_content_flagged:
            checks.append(
                Check(
                    name="untrusted_content",
                    status=E,
                    detail="The invoice text contains instruction-like content. "
                    "It cannot be released without human review.",
                    policy_ref="AI Agent Policy §4",
                )
            )

        principal = facts.principal
        if principal is not None:
            within = invoice.amount <= principal.autonomous_limit
            checks.append(
                Check(
                    name="autonomous_threshold",
                    status=P if within else E,
                    detail=(
                        f"Amount is within the autonomous limit of "
                        f"{money_str(principal.autonomous_limit)}."
                        if within
                        else f"Amount {money_str(invoice.amount)} exceeds the autonomous limit of "
                        f"{money_str(principal.autonomous_limit)}."
                    ),
                    policy_ref="Payment Policy §3",
                )
            )
        return checks

    @staticmethod
    def _evidence_check(action: ProposedAction, facts: Facts) -> Check:
        required = {
            f"invoice:{action.invoice_id}",
            f"supplier:{facts.invoice.supplier_id}" if facts.invoice else "",
            f"po:{facts.invoice.purchase_order_id}" if facts.invoice else "",
        }
        missing = sorted(required - set(action.evidence_ids))
        if missing:
            detail = "Recommendation does not cite required evidence: " + ", ".join(missing) + "."
            ok = False
        elif facts.unresolved_evidence_ids:
            detail = "Cited evidence does not exist: " + ", ".join(facts.unresolved_evidence_ids) + "."
            ok = False
        else:
            detail = f"{len(action.evidence_ids)} cited sources resolve to real records."
            ok = True
        return Check(
            name="evidence_present",
            status=P if ok else F,
            detail=detail,
            policy_ref="Payment Policy §6",
        )
