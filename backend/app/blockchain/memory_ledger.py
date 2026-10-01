"""In-process stand-in for TrustChainRegistry.

Used by the test suite and by `LEDGER_MODE=memory`, where the app runs without
a node. It applies the same rules as the Solidity contract and is reported as
SIMULATED everywhere it is shown. It proves nothing to a third party: it lives
in the same process as the data it vouches for.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from app.blockchain.ledger import AgentRecord, ExecutionRecord, LedgerInfo, TxRef
from app.errors import LedgerRejectedError, LedgerUnavailableError
from app.security.hashing import ZERO_HASH, id_hash, sha256_hex


class InMemoryLedger:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}
        self._permissions: set[tuple[str, str]] = set()
        self._approvals: dict[str, str] = {}
        self._executions: dict[str, ExecutionRecord] = {}
        self._block = 0
        self.available = True  # tests flip this to simulate an outage

    # -- admin side: what the deploy script does against the real contract ----

    def register_agent(self, agent_hash: str, policy_hash: str) -> None:
        if agent_hash in self._agents:
            raise LedgerRejectedError("AgentAlreadyRegistered")
        self._agents[agent_hash] = AgentRecord(True, True, policy_hash, int(time.time()))
        self._mine()

    def deactivate_agent(self, agent_hash: str) -> None:
        agent = self._agents.get(agent_hash)
        if agent is None:
            raise LedgerRejectedError("AgentNotRegistered")
        self._agents[agent_hash] = AgentRecord(True, False, agent.policy_hash, agent.registered_at)
        self._mine()

    def set_agent_permission(self, agent_hash: str, permission_hash: str, allowed: bool) -> None:
        if agent_hash not in self._agents:
            raise LedgerRejectedError("AgentNotRegistered")
        key = (agent_hash, permission_hash)
        self._permissions.add(key) if allowed else self._permissions.discard(key)
        self._mine()

    def bootstrap(self, agents: Iterable[dict[str, Any]]) -> None:
        for agent in agents:
            agent_hash = id_hash("agent", agent["id"])
            if agent_hash in self._agents:
                continue
            self.register_agent(agent_hash, id_hash("policy", agent["policy"]))
            for permission in agent["allowed_actions"]:
                self.set_agent_permission(agent_hash, id_hash("permission", permission), True)

    # -- LedgerClient ---------------------------------------------------------

    def _require_available(self) -> None:
        if not self.available:
            raise LedgerUnavailableError("Ledger is unreachable.")

    def _mine(self) -> TxRef:
        self._block += 1
        return TxRef(sha256_hex(f"simulated-tx:{self._block}"), self._block)

    def info(self) -> LedgerInfo:
        return LedgerInfo(
            mode="SIMULATED",
            connected=self.available,
            contract_address=None,
            chain_id=None,
            block_number=self._block if self.available else None,
            recorder=None,
            detail="In-memory simulation of the registry. Not independently verifiable.",
        )

    def get_agent(self, agent_hash: str) -> AgentRecord | None:
        self._require_available()
        return self._agents.get(agent_hash)

    def is_authorized(self, agent_hash: str, permission_hash: str) -> bool:
        self._require_available()
        agent = self._agents.get(agent_hash)
        return bool(agent and agent.active and (agent_hash, permission_hash) in self._permissions)

    def get_approval_hash(self, action_hash: str) -> str | None:
        self._require_available()
        return self._approvals.get(action_hash)

    def record_approval(self, action_hash: str, approval_hash: str, role_hash: str) -> TxRef:
        self._require_available()
        if action_hash in self._approvals:
            raise LedgerRejectedError("ApprovalAlreadyRecorded")
        self._approvals[action_hash] = approval_hash
        return self._mine()

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
        self._require_available()
        if action_hash in self._executions:
            raise LedgerRejectedError("ExecutionAlreadyRecorded")
        if agent_hash != ZERO_HASH:
            agent = self._agents.get(agent_hash)
            if agent is None:
                raise LedgerRejectedError("AgentNotRegistered")
            if not agent.active:
                raise LedgerRejectedError("AgentNotActive")
            if (agent_hash, permission_hash) not in self._permissions:
                raise LedgerRejectedError("PermissionNotGranted")
        if approval_hash != ZERO_HASH and self._approvals.get(action_hash) != approval_hash:
            raise LedgerRejectedError("ApprovalMismatch")
        ref = self._mine()
        self._executions[action_hash] = ExecutionRecord(
            agent_id=agent_hash,
            permission=permission_hash,
            policy_hash=policy_hash,
            approval_hash=approval_hash,
            receipt_hash=receipt_hash,
            timestamp=int(time.time()),
            block_number=ref.block_number,
            success=success,
        )
        return ref

    def get_execution(self, action_hash: str) -> ExecutionRecord | None:
        self._require_available()
        return self._executions.get(action_hash)
