"""Composition root: where the pieces are wired together, and nowhere else."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import LLMProvider, MockLLMProvider, OpenAICompatibleProvider
from app.blockchain.ledger import LedgerClient
from app.blockchain.memory_ledger import InMemoryLedger
from app.blockchain.web3_ledger import Web3Ledger
from app.config import Settings
from app.governance.engine import GovernanceEngine
from app.governance.facts import FactLoader
from app.governance.rules import PolicyRules, load_rules
from app.models.db import ActionRow, Database
from app.models.domain import ActionStatus
from app.observability.audit import AuditLog
from app.observability.logging import log_event
from app.rag.retriever import Retriever, build_retriever
from app.security.rate_limit import RateLimiter
from app.security.signing import ApprovalSigner
from app.services.payment import MockPaymentService
from app.services.receipts import ReceiptService
from app.services.requests import AgentRunService, ManualRequestService
from app.services.seed import seed_if_empty
from app.services.state import SystemState
from app.services.workflow import PaymentWorkflow

logger = logging.getLogger("trustchain.container")


@dataclass
class Services:
    """Request-scoped services sharing one database session."""

    session: Session
    audit: AuditLog
    state: SystemState
    facts: FactLoader
    receipts: ReceiptService
    workflow: PaymentWorkflow
    agent_runs: AgentRunService
    manual: ManualRequestService


def build_llm(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAICompatibleProvider(
            settings.openai_base_url, settings.openai_api_key, settings.openai_model
        )
    return MockLLMProvider(obeys_injection=settings.mock_llm_obeys_injection)


def build_ledger(settings: Settings) -> LedgerClient:
    if settings.ledger_mode == "hardhat":
        return Web3Ledger(settings.ledger_rpc_url, settings.ledger_deployment_file)
    ledger = InMemoryLedger()
    # Stands in for the deploy script, which registers agents on the real contract.
    ledger.bootstrap(json.loads((settings.data_dir / "agents.json").read_text(encoding="utf-8")))
    return ledger


class AppContainer:
    def __init__(
        self,
        settings: Settings,
        *,
        ledger: LedgerClient | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self.settings = settings
        self.db = Database(settings.database_url)
        self.rules: PolicyRules = load_rules(settings.data_dir / "policies")
        self.governance = GovernanceEngine(self.rules)
        self.retriever: Retriever = build_retriever(settings.data_dir)
        self.ledger: LedgerClient = ledger or build_ledger(settings)
        self.llm: LLMProvider = llm or build_llm(settings)
        self.signer = ApprovalSigner(settings.approval_signing_secret)
        self.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    def initialise(self) -> None:
        self.db.create_all()
        with self.db.session() as session:
            seeded = seed_if_empty(session, self.settings.data_dir)
            recovered = self._recover_interrupted(session)
        log_event(
            logger,
            "startup",
            seeded=seeded,
            recovered_actions=recovered,
            ledger_mode=self.settings.ledger_mode,
            llm_provider=self.llm.name,
            policy_version=self.rules.version,
            demo_mode=self.settings.demo_mode,
        )

    @staticmethod
    def _recover_interrupted(session: Session) -> int:
        """Releases actions left EXECUTING by a process that died mid-execution.

        Payment, receipt and the EXECUTED status commit in one transaction, so an
        action still EXECUTING at startup has not paid anything. It goes back to
        AUTHORIZED, where execution re-checks governance before doing anything.
        Correct for a single instance only; several would need a lease instead.
        """
        stuck = list(
            session.scalars(
                select(ActionRow).where(ActionRow.status == ActionStatus.EXECUTING.value)
            )
        )
        audit = AuditLog(session)
        for row in stuck:
            row.status = ActionStatus.AUTHORIZED.value
            row.last_error = "Execution was interrupted by a restart. Retry to continue."
            audit.record("EXECUTION_RECOVERED", actor="system", subject=row.id)
        session.commit()
        return len(stuck)

    def reset(self) -> None:
        """Demo only: back to the seeded state. The ledger keeps its history."""
        self.db.drop_all()
        self.initialise()

    def services(self, session: Session) -> Services:
        audit = AuditLog(session)
        facts = FactLoader(session, self.rules, self.retriever)
        receipts = ReceiptService(session, self.ledger, audit)
        workflow = PaymentWorkflow(
            session,
            self.governance,
            facts,
            MockPaymentService(session),
            receipts,
            self.ledger,
            audit,
            self.signer,
        )
        return Services(
            session=session,
            audit=audit,
            state=SystemState(session),
            facts=facts,
            receipts=receipts,
            workflow=workflow,
            agent_runs=AgentRunService(session, self.llm, self.retriever, facts, workflow, audit),
            manual=ManualRequestService(session, workflow),
        )
