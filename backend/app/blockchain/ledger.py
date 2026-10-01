"""The ledger as the backend sees it.

The interface has no admin operations. Registering an agent or granting a
permission is done by the admin key outside the application (the deploy script
and Hardhat tasks), so the backend cannot widen its own agent's authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TxRef:
    tx_hash: str
    block_number: int


@dataclass(frozen=True)
class AgentRecord:
    registered: bool
    active: bool
    policy_hash: str
    registered_at: int


@dataclass(frozen=True)
class ExecutionRecord:
    agent_id: str
    permission: str
    policy_hash: str
    approval_hash: str
    receipt_hash: str
    timestamp: int
    block_number: int
    success: bool


@dataclass(frozen=True)
class LedgerInfo:
    mode: str
    connected: bool
    contract_address: str | None
    chain_id: int | None
    block_number: int | None
    recorder: str | None
    detail: str


class LedgerClient(Protocol):
    """Raises LedgerUnavailableError when unreachable, LedgerRejectedError on a revert."""

    def info(self) -> LedgerInfo: ...

    def get_agent(self, agent_hash: str) -> AgentRecord | None: ...

    def is_authorized(self, agent_hash: str, permission_hash: str) -> bool: ...

    def get_approval_hash(self, action_hash: str) -> str | None: ...

    def record_approval(self, action_hash: str, approval_hash: str, role_hash: str) -> TxRef: ...

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
    ) -> TxRef: ...

    def get_execution(self, action_hash: str) -> ExecutionRecord | None: ...
