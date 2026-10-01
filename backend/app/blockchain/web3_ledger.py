"""TrustChainRegistry over JSON-RPC (local Hardhat node).

Transactions are sent from the node's unlocked recorder account, so no private
key exists in this repository or its configuration. Pointing this at any
non-local network would need a real signer (KMS/HSM); that is out of scope.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from web3 import Web3
from web3.exceptions import ContractLogicError

from app.blockchain.ledger import AgentRecord, ExecutionRecord, LedgerInfo, TxRef
from app.errors import LedgerRejectedError, LedgerUnavailableError
from app.observability.logging import log_event
from app.security.hashing import ZERO_HASH

logger = logging.getLogger("trustchain.ledger")
T = TypeVar("T")


def _to_bytes32(hex_hash: str) -> bytes:
    raw = bytes.fromhex(hex_hash.removeprefix("0x"))
    if len(raw) != 32:
        raise ValueError("expected a 32-byte hash")
    return raw


def _to_hex(value: bytes) -> str:
    return "0x" + bytes(value).hex()


class Web3Ledger:
    def __init__(self, rpc_url: str, deployment_file: Path, timeout_seconds: float = 5.0) -> None:
        self._rpc_url = rpc_url
        self._deployment_file = deployment_file
        self._w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout_seconds}))
        self._contract: Any = None
        self._deployment: dict[str, Any] | None = None
        self._error_names: dict[str, str] = {}

    # The deployment file is read lazily so the backend can start before the
    # contract is deployed and recover when the node comes back.
    def _load(self) -> Any:
        if self._contract is not None:
            return self._contract
        try:
            deployment = json.loads(self._deployment_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LedgerUnavailableError(
                f"No contract deployment found at {self._deployment_file}."
            ) from exc
        self._deployment = deployment
        self._contract = self._w3.eth.contract(address=deployment["address"], abi=deployment["abi"])
        for entry in deployment["abi"]:
            if entry.get("type") == "error":
                signature = f"{entry['name']}({','.join(i['type'] for i in entry['inputs'])})"
                self._error_names[Web3.keccak(text=signature)[:4].hex()] = entry["name"]
        return self._contract

    def _revert_reason(self, exc: ContractLogicError) -> str:
        data = getattr(exc, "data", None)
        if isinstance(data, str) and len(data) >= 10:
            name = self._error_names.get(data.removeprefix("0x")[:8])
            if name:
                return name
        return exc.message or "transaction reverted"

    def _call(self, operation: Callable[[Any], T]) -> T:
        contract = self._load()
        try:
            return operation(contract)
        except ContractLogicError as exc:
            raise LedgerRejectedError(self._revert_reason(exc)) from exc
        except Exception as exc:  # connection refused, timeout, node restarted without deploy
            self._contract = None
            raise LedgerUnavailableError(f"Ledger is unreachable: {type(exc).__name__}.") from exc

    def _send(self, build: Callable[[Any], Any], label: str) -> TxRef:
        def operation(contract: Any) -> TxRef:
            assert self._deployment is not None
            tx_hash = build(contract).transact({"from": self._deployment["recorder"]})
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            if receipt["status"] != 1:
                raise ContractLogicError("transaction reverted")
            return TxRef(_to_hex(tx_hash), int(receipt["blockNumber"]))

        ref = self._call(operation)
        log_event(logger, "ledger_transaction", method=label, tx=ref.tx_hash, block=ref.block_number)
        return ref

    def info(self) -> LedgerInfo:
        try:
            self._load()
            assert self._deployment is not None
            code = self._w3.eth.get_code(self._deployment["address"])
            if len(code) == 0:
                self._contract = None
                raise LedgerUnavailableError("No contract code at the deployed address.")
            return LedgerInfo(
                mode="HARDHAT_LOCAL",
                connected=True,
                contract_address=self._deployment["address"],
                chain_id=int(self._w3.eth.chain_id),
                block_number=int(self._w3.eth.block_number),
                recorder=self._deployment["recorder"],
                detail="Local Hardhat development chain. Single operator; no real value.",
            )
        except Exception as exc:
            return LedgerInfo(
                mode="HARDHAT_LOCAL",
                connected=False,
                contract_address=self._deployment["address"] if self._deployment else None,
                chain_id=None,
                block_number=None,
                recorder=None,
                detail=getattr(exc, "message", None) or f"Ledger is unreachable: {type(exc).__name__}.",
            )

    def get_agent(self, agent_hash: str) -> AgentRecord | None:
        record = self._call(lambda c: c.functions.getAgent(_to_bytes32(agent_hash)).call())
        registered, active, policy_hash, registered_at = record
        if not registered:
            return None
        return AgentRecord(registered, active, _to_hex(policy_hash), int(registered_at))

    def is_authorized(self, agent_hash: str, permission_hash: str) -> bool:
        return bool(
            self._call(
                lambda c: c.functions.isAuthorized(
                    _to_bytes32(agent_hash), _to_bytes32(permission_hash)
                ).call()
            )
        )

    def get_approval_hash(self, action_hash: str) -> str | None:
        record = self._call(lambda c: c.functions.getApproval(_to_bytes32(action_hash)).call())
        approval_hash = _to_hex(record[0])
        return None if approval_hash == ZERO_HASH else approval_hash

    def record_approval(self, action_hash: str, approval_hash: str, role_hash: str) -> TxRef:
        return self._send(
            lambda c: c.functions.recordApproval(
                _to_bytes32(action_hash), _to_bytes32(approval_hash), _to_bytes32(role_hash)
            ),
            "recordApproval",
        )

    def record_execution(
        self,
        *,
        action_hash: str,
        agent_hash: str,
        permission_hash: str,
        policy_hash: str,
        approval_hash: str,
        receipt_hash: str,
        success: bool,
    ) -> TxRef:
        return self._send(
            lambda c: c.functions.recordExecution(
                _to_bytes32(action_hash),
                _to_bytes32(agent_hash),
                _to_bytes32(permission_hash),
                _to_bytes32(policy_hash),
                _to_bytes32(approval_hash),
                _to_bytes32(receipt_hash),
                success,
            ),
            "recordExecution",
        )

    def get_execution(self, action_hash: str) -> ExecutionRecord | None:
        record = self._call(lambda c: c.functions.getExecution(_to_bytes32(action_hash)).call())
        agent_id, permission, policy_hash, approval_hash, receipt_hash, timestamp, block, success = record
        if _to_hex(receipt_hash) == ZERO_HASH:
            return None
        return ExecutionRecord(
            agent_id=_to_hex(agent_id),
            permission=_to_hex(permission),
            policy_hash=_to_hex(policy_hash),
            approval_hash=_to_hex(approval_hash),
            receipt_hash=_to_hex(receipt_hash),
            timestamp=int(timestamp),
            block_number=int(block),
            success=bool(success),
        )
