# TrustChain AI — Implementation Plan

Written before the code. Where the implementation later diverged, this file was
updated rather than left stale.

## 1. What this PoC has to prove

One sentence: **AI is powerful, but AI is not the authority.**

| Actor            | May do                                   | May not do                                |
|------------------|------------------------------------------|-------------------------------------------|
| LLM              | Summarise evidence, recommend            | Decide anything                           |
| Agent            | Read records, *request* an action        | Execute, approve, change its permissions  |
| Policy engine    | Decide ALLOW / REQUIRE_APPROVAL / DENY   | Be influenced by model output             |
| Human approver   | Approve or reject within their limit     | Approve their own request                 |
| Workflow service | Execute an *authorised* action once      | Execute anything not authorised           |
| Smart contract   | Refuse records that break registry rules | See business data                         |
| Blockchain       | Make later edits detectable              | Prove the receipt was true when written   |

## 2. Architecture

```
React dashboard ──HTTP──> FastAPI routes (thin: auth, validation, mapping)
                              │
        ┌─────────────────────┼──────────────────────────┐
        ▼                     ▼                          ▼
  TreasuryAgent         PaymentWorkflow            ReceiptService
  (LLM + RAG +          (state machine,            (canonical hash,
   read-only tools)      the only executor)         chain, verify)
        │ ProposedAction      │
        └──────────►  GovernanceEngine  (pure function of action + facts)
                      identity · permission · policy · risk · approval
                              │
                    MockPaymentService   LedgerClient (web3 | in-memory)
                              │                   │
                           SQLite          TrustChainRegistry.sol
```

Rules that shape the code:

1. **Governance is a pure function.** `evaluate(action, facts) -> decision`.
   Facts are loaded from the system of record, never from the agent's proposal.
   The proposal's amount/supplier are *claims* that are checked against the record.
2. **The agent has no execute tool.** Its tool gateway exposes read tools only.
   Everything else is a request that must pass governance.
3. **One executor.** Only `PaymentWorkflow` calls the payment tool, and only via
   an atomic `AUTHORIZED -> EXECUTING` state transition.
4. **Approvals are bound to an action hash**, so approving action A cannot
   authorise action B.
5. **Governance is re-evaluated at approval time** (the supplier may have been
   blocked since the proposal was made).
6. **Manual and AI paths share steps 3–5.** The kill switch removes the agent,
   nothing else.

## 3. Dependencies

Backend: FastAPI, Pydantic v2, SQLAlchemy 2, web3.py, httpx, uvicorn; pytest, ruff (dev).
No numpy, no vector DB, no LLM SDK: the RAG index is ~100 lines of pure Python
and the optional OpenAI-compatible provider is one `httpx` call.

Blockchain: Hardhat 2 + hardhat-toolbox, Solidity 0.8.24. No OpenZeppelin: the
contract needs two roles and three mappings; a dependency would be larger than the code.

Frontend: React 18, TypeScript, Vite, react-router. No component library.

## 4. Domain models

- `Principal` — `AGENT` or `HUMAN`, with permissions and an autonomous limit.
- `ProposedAction` — id, principal, action_type (free string, validated by
  governance, so unknown actions are recorded and denied rather than rejected
  at the schema layer), invoice/supplier/PO/amount claims, evidence ids, origin (`AI`/`MANUAL`).
- `Check` — name, PASS/FAIL/WARN, detail, policy reference.
- `GovernanceDecision` — decision id, permission checks, policy checks, risk
  level, required approver role, decision, policy version.
- `Approval` — approver, role, decision, comment, action hash, HMAC signature (mock).
- `PaymentResult` — `MOCK-TX-…`, status, timestamp.
- `ExecutionReceipt` — the fields in the brief; `receipt_hash` covers every
  field except itself and `blockchain_tx_hash`.
- `AuditEvent` — hash-chained, correlation id on every row.

Money is `Decimal` in Python, integer cents in SQLite, a `"50000.00"` string in
JSON and in the hashed canonical form. No floats.

Action state machine:

```
PROPOSED ─┬─> DENIED
          ├─> PENDING_APPROVAL ─┬─> REJECTED
          │                     ├─> DENIED        (re-evaluation failed)
          │                     └─> AUTHORIZED
          └─> AUTHORIZED ──> EXECUTING ─┬─> EXECUTED
                                        └─> FAILED / back to AUTHORIZED (retryable)
```

## 5. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/system`, `/api/overview`, `/api/metrics` | status |
| POST | `/api/system/ai-mode` | kill switch (manager or CFO) |
| GET | `/api/users` | mock identity picker |
| GET | `/api/invoices`, `/api/invoices/{id}` | invoice + supplier + PO + actions |
| POST | `/api/agent/analyze` | run the agent on an invoice |
| GET | `/api/agent/runs`, `/api/agent/runs/{id}` | agent timeline |
| GET | `/api/agents/{id}/passport` | identity, scope, on-chain registration |
| POST | `/api/payments/manual` | human-initiated request, same governance |
| GET | `/api/actions`, `/api/actions/{id}`, `/api/approvals/pending` | work queue |
| POST | `/api/actions/{id}/approve`, `/reject`, `/execute` | human decision, retry |
| GET | `/api/receipts`, `/api/receipts/{id}` | receipts |
| POST | `/api/receipts/{id}/verify`, `/anchor` | verification, anchor retry |
| POST | `/api/demo/receipts/{id}/tamper`, `/restore`, `/api/demo/reset` | demo only, gated by `DEMO_MODE` |
| GET | `/api/audit`, `/api/audit/verify`, `/api/ledger/records` | audit |

## 6. Smart contract interface

```solidity
registerAgent(bytes32 agentId, bytes32 policyHash)              // admin
deactivateAgent(bytes32 agentId)                                // admin
setAgentPermission(bytes32 agentId, bytes32 perm, bool allowed) // admin
setRecorder(address recorder, bool allowed)                     // admin
recordApproval(bytes32 actionId, bytes32 approvalHash, bytes32 approverRole)   // recorder
recordExecution(bytes32 actionId, bytes32 agentId, bytes32 perm,
                bytes32 policyHash, bytes32 approvalHash, bytes32 receiptHash) // recorder
verifyExecution(bytes32 actionId, bytes32 receiptHash) view returns (bool)
isAuthorized(bytes32 agentId, bytes32 perm) view returns (bool)
```

`recordExecution` reverts when the action is already recorded, when the agent is
unregistered, inactive or lacks the permission, or when the approval hash does
not match the one recorded for that action. The admin key (deploy script) and
the recorder key (backend) are different accounts: the backend cannot grant its
agent a permission.

## 7. Test strategy

- **Unit, no DB:** permission, policy, risk, approval engines on hand-built facts;
  canonical hashing; RAG retrieval; mock LLM.
- **Service, in-memory SQLite + in-memory ledger:** every scenario in the brief,
  plus hallucinated amount, approve-then-supplier-blocked, self-approval,
  insufficient limit, double approval, concurrent execute, ledger outage.
- **API:** auth, validation, correlation ids, demo gating.
- **Contract (Hardhat):** registration, deactivation, permissions, approvals,
  executions, duplicate, unauthorised callers.
- **Chain integration:** backend against a live Hardhat node; skipped when no node.

## 8. Security boundaries

| Boundary | Trusted side | Untrusted side | Control |
|---|---|---|---|
| Invoice text → LLM | prompt | invoice notes | delimiting, detector (both advisory) |
| LLM → agent | agent code | model output | schema parse, fail closed |
| Agent → governance | governance | proposal | re-load facts, allow-list, thresholds |
| Human → approval | approval engine | request | role, limit, four-eyes, action-hash binding |
| Workflow → payment | payment tool | caller | state CAS, unique invoice, idempotency key |
| Backend → chain | contract | backend | recorder role, registry checks, write-once |
| DB → auditor | chain | DB | recomputed hash vs on-chain hash |

## 9. Assumptions

- Authentication is mocked (`X-User-Id`). Authorisation on top of it is real.
- The "digital signature" is an HMAC with a server secret, clearly labelled mock.
- The local Hardhat chain has one operator, so it demonstrates the mechanism,
  not the trust property. `docs/ARCHITECTURE.md` says so.
- `CHANGE_BANK_ACCOUNT` in the brief is named `CHANGE_SUPPLIER_BANK_ACCOUNT`
  everywhere, matching the brief's own prompt-injection example.
- Two additions to the brief's data: `USR-003` (AP clerk, no approval authority)
  so the manual path has a requester distinct from the approver, and `SUP-004`
  with a limit high enough for the $250,000 scenario.
- When the kill switch is OFF, agent-originated actions still awaiting approval
  are denied on re-evaluation and must be re-submitted manually.
- A ledger outage blocks *agent-originated* execution (the on-chain registry
  cannot confirm the agent) but not the manual path; receipts are anchored later.

## 10. Changes made after this plan was written

- **Dashboard.** The ten-screen navigation in the brief was replaced by four
  entries: a single guided Demo page in plain language, Audit & Verify,
  Architecture, and Technical Details (which holds the original screens).
- **Payment history tool.** The agent gained `read_payment_history`, under the
  existing `READ_INVOICE` permission, so the "previous payments" it reports
  are something it actually read.
- **Crash recovery.** Actions left `EXECUTING` by a dead process are returned
  to `AUTHORIZED` at startup.
- **Demo data.** The blocked-supplier invoice is $50,000.

## 11. Phases

1 skeleton + data · 2 API + DB · 3 governance · 4 agent + RAG · 5 approval ·
6 payment · 7 receipts · 8 contract · 9 ledger integration · 10 dashboard ·
11 kill switch · 12 attack demos · 13 tests · 14 Docker · 15 docs + review.
