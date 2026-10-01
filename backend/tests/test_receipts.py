"""Receipt hashing, chaining, anchoring and tamper detection."""

from __future__ import annotations

from sqlalchemy import select

from app.container import Services
from app.models.db import ReceiptRow
from app.security.hashing import ZERO_HASH
from app.services.receipts import compute_receipt_hash
from tests.conftest import ALICE, CAROL, get_user

EXPECTED_FIELDS = {
    "receipt_id", "agent_id", "agent_version", "model_provider", "model_name", "policy_version",
    "invoice_id", "supplier_id", "purchase_order_id", "retrieved_source_ids", "requested_action",
    "amount", "risk_level", "governance_decision", "human_approval_id", "tool_executed",
    "execution_result", "timestamp", "previous_receipt_hash",
}


def pay(services: Services, invoice_id: str) -> ReceiptRow:
    action = services.manual.submit(get_user(services, CAROL), invoice_id)
    if action.status == "PENDING_APPROVAL":
        services.workflow.decide(action.id, get_user(services, ALICE), approve=True, comment="")
    return services.session.scalars(
        select(ReceiptRow).where(ReceiptRow.action_id == action.id)
    ).one()


def test_receipt_has_every_field_in_the_specification(services):
    receipt = pay(services, "INV-2026-0042")
    assert EXPECTED_FIELDS <= set(receipt.payload)
    assert receipt.payload["tool_executed"] == "MockPaymentService.execute_payment"
    assert receipt.payload["execution_result"]["transaction_id"].startswith("MOCK-TX-")
    assert receipt.blockchain_tx_hash and receipt.block_number


def test_receipt_hash_is_the_hash_of_its_canonical_payload(services):
    receipt = pay(services, "INV-2026-0042")
    assert receipt.receipt_hash == compute_receipt_hash(receipt.payload)
    assert compute_receipt_hash(dict(reversed(receipt.payload.items()))) == receipt.receipt_hash


def test_receipts_form_a_hash_chain(services):
    first = pay(services, "INV-2026-0043")
    second = pay(services, "INV-2026-0048")
    assert first.payload["previous_receipt_hash"] == ZERO_HASH
    assert second.payload["previous_receipt_hash"] == first.receipt_hash


def test_ledger_holds_only_hashes(services, ledger):
    receipt = pay(services, "INV-2026-0042")
    record = ledger.get_execution(receipt.action_hash)
    for value in (record.agent_id, record.permission, record.policy_hash, record.approval_hash,
                  record.receipt_hash):
        assert value.startswith("0x") and len(value) == 66
    assert record.receipt_hash == receipt.receipt_hash
    assert ledger.get_approval_hash(receipt.action_hash) == receipt.payload["approval_hash"]


def test_untouched_receipt_verifies(services):
    result = services.receipts.verify(pay(services, "INV-2026-0042").receipt_id)
    assert result["status"] == "VERIFIED"
    assert result["recomputed_hash"] == result["stored_hash"] == result["onchain_hash"]
    assert result["chain_link_ok"] is True


def test_naive_tampering_is_detected(services):
    """Amount changed, stored hash left alone: caught even without the ledger."""
    receipt = pay(services, "INV-2026-0042")
    tampered = services.receipts.tamper(receipt.receipt_id, recompute_hash=False)
    assert tampered.payload["amount"] == "500000.00"

    result = services.receipts.verify(receipt.receipt_id)
    assert result["status"] == "TAMPER_DETECTED"
    assert result["local_match"] is False
    assert result["chain_match"] is False


def test_tampering_that_also_rewrites_the_stored_hash_is_caught_only_by_the_ledger(services):
    """The case that justifies an anchor outside the database."""
    receipt = pay(services, "INV-2026-0042")
    services.receipts.tamper(receipt.receipt_id, recompute_hash=True)

    result = services.receipts.verify(receipt.receipt_id)
    assert result["local_match"] is True  # the database is self-consistent
    assert result["chain_match"] is False  # the ledger is not fooled
    assert result["status"] == "TAMPER_DETECTED"


def test_restoring_the_receipt_verifies_again(services):
    receipt = pay(services, "INV-2026-0042")
    services.receipts.tamper(receipt.receipt_id, recompute_hash=True)
    services.receipts.restore(receipt.receipt_id)
    assert services.receipts.verify(receipt.receipt_id)["status"] == "VERIFIED"


def test_tampering_is_caught_locally_while_the_ledger_is_down(services, ledger):
    receipt = pay(services, "INV-2026-0042")
    services.receipts.tamper(receipt.receipt_id, recompute_hash=False)
    ledger.available = False
    assert services.receipts.verify(receipt.receipt_id)["status"] == "TAMPER_DETECTED"


def test_rewriting_one_receipt_breaks_the_link_from_the_next(services):
    first = pay(services, "INV-2026-0043")
    second = pay(services, "INV-2026-0048")
    services.receipts.tamper(first.receipt_id, recompute_hash=True)
    assert services.receipts.verify(second.receipt_id)["chain_link_ok"] is False


def test_anchor_is_write_once_and_safe_to_repeat(services, ledger):
    receipt = pay(services, "INV-2026-0042")
    block = receipt.block_number
    assert services.receipts.anchor(receipt).block_number == block

    # A lost response: the hash is on the ledger but the row still says PENDING.
    receipt.anchor_status = "PENDING"
    services.session.commit()
    assert services.receipts.anchor(receipt).anchor_status == "ANCHORED"


def test_a_tampered_receipt_cannot_replace_the_anchored_hash(services):
    receipt = pay(services, "INV-2026-0042")
    services.receipts.tamper(receipt.receipt_id, recompute_hash=True)
    receipt.anchor_status = "PENDING"
    services.session.commit()

    again = services.receipts.anchor(receipt)
    assert again.anchor_status == "REJECTED"
    assert services.receipts.verify(receipt.receipt_id)["status"] == "TAMPER_DETECTED"


def test_verified_receipts_metric(services):
    from app.observability.metrics import collect_metrics

    receipt = pay(services, "INV-2026-0042")
    assert collect_metrics(services.session)["verified_receipts"] == 0
    services.receipts.verify(receipt.receipt_id)
    assert collect_metrics(services.session)["verified_receipts"] == 1
    services.receipts.tamper(receipt.receipt_id, recompute_hash=False)
    assert collect_metrics(services.session)["verified_receipts"] == 0
