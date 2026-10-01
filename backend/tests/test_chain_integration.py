"""The backend against the real contract on a local Hardhat node.

Skipped unless a node is running with TrustChainRegistry deployed:

    make chain        # terminal 1
    make deploy       # terminal 2
    make test-chain
"""

from __future__ import annotations

import os
import uuid
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.blockchain.web3_ledger import Web3Ledger
from app.config import Settings
from app.container import AppContainer
from app.errors import LedgerRejectedError, LedgerUnavailableError
from app.models.db import ReceiptRow
from app.security.hashing import ZERO_HASH, id_hash, sha256_hex
from tests.conftest import AGENT_ID, ALICE, CAROL, get_user

pytestmark = pytest.mark.chain

DEFAULTS = Settings()
RPC_URL = os.environ.get("LEDGER_RPC_URL", DEFAULTS.ledger_rpc_url)
AGENT = id_hash("agent", AGENT_ID)
PROPOSE = id_hash("permission", "PROPOSE_PAYMENT")


def unique(label: str) -> str:
    return sha256_hex(f"{label}:{uuid.uuid4()}")


@pytest.fixture(scope="module")
def chain() -> Web3Ledger:
    ledger = Web3Ledger(RPC_URL, DEFAULTS.ledger_deployment_file)
    info = ledger.info()
    if not info.connected:
        pytest.skip(f"no Hardhat node with a deployed contract: {info.detail}")
    return ledger


def record(chain: Web3Ledger, action: str, **overrides: object):
    args: dict[str, object] = {
        "action_hash": action,
        "agent_hash": AGENT,
        "permission_hash": PROPOSE,
        "policy_hash": unique("policy"),
        "approval_hash": ZERO_HASH,
        "receipt_hash": unique("receipt"),
        "success": True,
    }
    args.update(overrides)
    return chain.record_execution(**args)  # type: ignore[arg-type]


def test_agent_from_the_deploy_script_is_registered_with_its_scope(chain):
    agent = chain.get_agent(AGENT)
    assert agent is not None and agent.active
    assert chain.is_authorized(AGENT, PROPOSE)
    assert not chain.is_authorized(AGENT, id_hash("permission", "CHANGE_SUPPLIER_BANK_ACCOUNT"))
    assert chain.get_agent(id_hash("agent", "AGENT-NOBODY")) is None


def test_execution_is_recorded_and_read_back(chain):
    action, receipt = unique("action"), unique("receipt")
    ref = record(chain, action, receipt_hash=receipt)
    assert ref.tx_hash.startswith("0x") and ref.block_number > 0

    stored = chain.get_execution(action)
    assert stored.receipt_hash == receipt
    assert stored.agent_id == AGENT
    assert stored.block_number == ref.block_number
    assert chain.get_execution(unique("never-recorded")) is None


def test_contract_reverts_are_reported_by_name(chain):
    action = unique("action")
    record(chain, action)
    with pytest.raises(LedgerRejectedError, match="ExecutionAlreadyRecorded"):
        record(chain, action)
    with pytest.raises(LedgerRejectedError, match="PermissionNotGranted"):
        record(chain, unique("action"), permission_hash=id_hash("permission", "CREATE_SUPPLIER"))
    with pytest.raises(LedgerRejectedError, match="AgentNotRegistered"):
        record(chain, unique("action"), agent_hash=id_hash("agent", "AGENT-NOBODY"))
    with pytest.raises(LedgerRejectedError, match="ApprovalMismatch"):
        record(chain, unique("action"), approval_hash=unique("approval"))


def test_approval_binding_on_chain(chain):
    action, approval = unique("action"), unique("approval")
    chain.record_approval(action, approval, id_hash("role", "FINANCE_MANAGER"))
    assert chain.get_approval_hash(action) == approval
    with pytest.raises(LedgerRejectedError, match="ApprovalAlreadyRecorded"):
        chain.record_approval(action, unique("other"), id_hash("role", "CFO"))
    record(chain, action, approval_hash=approval)


def test_unreachable_node_is_unavailable_not_a_crash():
    dead = Web3Ledger("http://127.0.0.1:1", DEFAULTS.ledger_deployment_file, timeout_seconds=1)
    assert dead.info().connected is False
    with pytest.raises(LedgerUnavailableError):
        dead.get_execution(unique("action"))


def test_receipt_to_blockchain_to_verification(chain):
    """invoice → governance → approval → mock payment → receipt → contract → verify → tamper."""
    settings = replace(
        DEFAULTS,
        database_url="sqlite:///:memory:",
        ledger_mode="hardhat",
        approval_signing_secret="test-secret",
    )
    container = AppContainer(settings, ledger=chain)
    container.initialise()
    with container.db.session() as session:
        services = container.services(session)
        run = services.agent_runs.run("INV-2026-0042", get_user(services, CAROL))
        action_id = run.analysis["proposed_actions"][0]["action_id"]
        decided = services.workflow.decide(
            action_id, get_user(services, ALICE), approve=True, comment="chain test"
        )
        assert decided.status == "EXECUTED"

        receipt = session.scalars(select(ReceiptRow)).one()
        assert receipt.anchor_status == "ANCHORED"
        assert receipt.blockchain_tx_hash.startswith("0x")

        onchain = chain.get_execution(receipt.action_hash)
        assert onchain.receipt_hash == receipt.receipt_hash
        assert onchain.approval_hash == receipt.payload["approval_hash"]

        verified = services.receipts.verify(receipt.receipt_id)
        assert verified["status"] == "VERIFIED"
        assert verified["ledger_mode"] == "HARDHAT_LOCAL"
        assert verified["contract_address"]

        services.receipts.tamper(receipt.receipt_id, recompute_hash=True)
        assert services.receipts.verify(receipt.receipt_id)["status"] == "TAMPER_DETECTED"
