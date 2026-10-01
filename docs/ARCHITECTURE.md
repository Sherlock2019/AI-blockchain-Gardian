# Architecture

## The one rule

**AI is powerful, but AI is not the authority.**

Every design decision below follows from separating two kinds of component:

- **Probabilistic**: the model. Useful, fast, sometimes wrong, sometimes manipulated.
- **Deterministic**: everything that decides or executes. Code with tests.

Nothing probabilistic sits on the path between "requested" and "executed".

## Who may do what

| Component | May | May not |
|---|---|---|
| Model | Summarise evidence, recommend | Decide, approve or execute anything |
| Agent | Read records, request an action | Execute; change its own permissions |
| Policy engine | ALLOW, REQUIRE_APPROVAL or DENY | Be loosened by model output |
| Human approver | Approve or reject within their limit | Approve their own request, or beyond their limit |
| Workflow service | Execute an authorised action once | Execute anything not authorised |
| Smart contract | Refuse records that break registry rules | See business data; judge whether a payment was right |
| Blockchain | Make later edits detectable | Prove the record was true when written |

The one place model output touches a decision: if the model does *not* recommend
payment, governance adds a human review. Model output can tighten an outcome
and can never loosen one. `test_model_doubt_adds_review_but_never_decides`
pins that down.

## Request lifecycle

```
PROPOSED ─┬─> DENIED
          ├─> PENDING_APPROVAL ─┬─> REJECTED
          │                     ├─> DENIED          governance re-evaluated at approval
          │                     └─> AUTHORIZED
          └─> AUTHORIZED ──> EXECUTING ─┬─> EXECUTED
                                        ├─> DENIED     re-evaluated again at execution
                                        └─> AUTHORIZED ledger unreachable; retryable
```

1. **Request.** The agent (`TreasuryAgent`) or a person (`ManualRequestService`)
   produces a `ProposedAction`. Both go to `PaymentWorkflow.submit`. From there
   on the code path is identical.
2. **Governance.** `FactLoader` reads the invoice, supplier, purchase order,
   payment history and requester from the database. `GovernanceEngine.evaluate`
   is a pure function of the action and those facts.
3. **Approval.** For REQUIRE_APPROVAL, a person decides. The approval engine
   checks role rank, approval limit and that approver ≠ requester. The approval
   is signed over the action hash. Governance is evaluated again first: the
   supplier may have been blocked since.
4. **Execution.** `AUTHORIZED → EXECUTING` is a compare-and-set `UPDATE`, so one
   of any number of concurrent callers proceeds. Governance and the approval
   (hash binding, signature, approver authority) are checked once more. For an
   agent-originated action the on-chain registry must also confirm the agent is
   active and permitted.
5. **Receipt.** Payment, invoice status, action status and receipt are written in
   one transaction. The receipt hash is then anchored on-chain. If the ledger is
   unreachable the receipt stays `PENDING` and can be anchored later.

## Why each technology is here

| Technology | Job | Why this and not something else |
|---|---|---|
| SQLite + SQLAlchemy | Operational state | A PoC needs a relational store with transactions and unique constraints; nothing more |
| RAG | Find the policy clauses relevant to an invoice, with citations | Policy is prose and changes; retrieval keeps the model's explanation grounded in the current text |
| LLM | Read, compare and explain | The part of the work that is genuinely language |
| Policy engine | Decide | Authorisation must be reproducible, testable and explainable line by line |
| Human approval | Accountability | Someone answerable must own consequential decisions |
| Smart contract | Registry rules that the writing application cannot bypass | See below |
| Blockchain | Evidence held outside the application database | See below |
| FastAPI | Typed HTTP boundary | Pydantic validation at the edge; routes contain no business logic |

### Decisions worth defending

**Governance is a pure function.** `evaluate(action, facts)` has no I/O. The
governance tests build facts by hand and run in milliseconds. The only impure
piece, `FactLoader`, is small and never reads a value from the request when the
database has its own.

**The request's amount and supplier are claims.** The agent passes through what
the model said. Governance compares it with the invoice on record. A
hallucinated amount is denied before any human is asked to approve it.

**The agent has no write tools.** `ToolGateway` exposes five read methods.
The strongest tool boundary is a tool that does not exist. A test asserts the
public surface of the gateway.

**Records by ID, policy by retrieval.** Invoices, suppliers and purchase orders
are fetched by exact key: similarity search is the wrong tool for "which
purchase order is this". Vector retrieval is used only for unstructured policy
text, one focused query per control.

**Citations come from tool calls.** The evidence list is what the gateway
actually returned, not what the model claims to have read.

**Rules are data, policies are prose.** Thresholds live in
`data/policies/policy_rules.json`. The Markdown policies are for people and for
the model's explanation. The engine never derives a rule from retrieved text.
The policy hash on every decision covers both, so drift is visible. Keeping
them aligned is a change-control task and is not automated here.

**Money is never a float.** `Decimal` in Python, integer cents in SQLite, a
two-decimal string in JSON and in hashed data. `canonical_json` rejects floats.

**A compromised run is refused whole.** If one request in an agent run is
outside the agent's scope, every other request from that run is denied too.

**The kill switch denies in-flight agent requests.** An agent request still
awaiting approval when AI is switched off is denied on re-evaluation and can be
re-submitted by a person. The conservative reading of "off".

**Ledger outage policy.** Agent-originated execution fails closed: if the
registry cannot confirm the agent, the action waits. The manual path does not
depend on the ledger; its receipts are anchored when the ledger returns. AI
degrades, the business does not.

## Web3 design

### What the contract enforces

`TrustChainRegistry` has two roles held by different accounts:

- **admin** registers agents, grants and revokes permissions, deactivates agents.
- **recorder** (the backend) can only append approval and execution records.

`recordExecution` reverts when:

- the action already has a record (`ExecutionAlreadyRecorded`);
- the agent is not registered, not active, or lacks the permission;
- an approval hash is supplied that differs from the one recorded for the action.

So a compromised backend cannot grant its agent a new permission on-chain,
cannot rewrite a recorded receipt hash, and cannot record an agent action after
the admin has deactivated the agent. The backend's `LedgerClient` interface has
no admin methods at all; admin operations are Hardhat tasks.

### What is stored

Only `bytes32` values: hashes of the agent id, permission, policy, approval and
receipt, keyed by the action hash. Plus timestamps and a success flag.

### Why not just use a database?

Honestly: for a single organisation with one trusted administrator, **you
probably should**.

| Need | Sufficient conventional tool |
|---|---|
| Detect edits by ordinary users or a compromised application | Append-only table with a hash chain; database audit logging |
| Detect edits by a database administrator | Hashes signed with a key the DBA does not hold (KMS/HSM), or periodic checkpoints to WORM storage (S3 Object Lock, Azure immutable blobs) |
| Verifiable log with inclusion proofs | A transparency log (Trillian, Sigstore Rekor), or a ledger database |
| Trusted time | RFC 3161 timestamping authority |
| Agent permission registry | A table and a second approver in your change process |

All of those are cheaper to run and easier to reason about than a blockchain.

A shared ledger starts to earn its cost when **several parties need to verify
the same record and none should have to trust another's infrastructure**:

- an enterprise and its supplier disputing whether a payment was authorised;
- a bank and its auditor;
- an AI provider and a customer who wants proof of what the agent was permitted to do;
- a DAO and an agent operator;
- a marketplace and the autonomous agents trading on it.

In those settings "who runs the audit database" is itself the dispute.

### What this PoC does and does not show

- It **does** show the mechanism: registry checks, write-once records, and
  verification by recomputation.
- It **does not** show the trust property. One Hardhat node on a laptop has one
  operator, who can reset the chain. Admin and recorder are two accounts on the
  same node.
- The in-memory ledger used in tests and `demo-lite` proves nothing to anyone.
  It exists so the suite runs without a node and is labelled SIMULATED.

### What blockchain does not solve, anywhere

- **Garbage in.** A hash proves the record has not changed since it was
  written. It says nothing about whether the record was true, or the AI correct.
- **The window before anchoring.** A record altered before its hash is anchored
  is anchored altered.
- **Key custody.** Whoever holds the recorder key can write records. Whoever
  holds the admin key controls the registry.
- **Off-chain enforcement.** The contract cannot stop a payment. It can refuse
  to record one, which makes a missing record evidence of a problem.
- **Privacy by hashing.** Hashes of low-entropy data can be guessed. Receipts
  include a random identifier; agent and permission ids are assumed public.

## RAG pipeline

```
policies/*.md, contracts.json
   → chunk by numbered section        rag/chunking.py     "Payment Policy §3"
   → Embedder.embed                   rag/embeddings.py   hashed bag-of-words
   → VectorIndex.add / search         rag/index.py        IDF-weighted cosine, in memory
   → Retriever.search                 rag/retriever.py
   → ToolGateway.search_policy        agents/tools.py     permission check, audit, citation
   → prompt → LLM → schema-validated answer
```

`Embedder` and `VectorIndex` are protocols. Replacing the hashing embedder with
a model and the in-memory index with pgvector or Qdrant touches two classes.

## Observability

- **Logs**: one JSON object per line, with `correlation_id`. Keys that look like
  secrets, and invoice free text, are redacted.
- **Correlation**: `X-Correlation-ID` is accepted if it is safe to log, otherwise
  generated. It is stored on actions and audit events and returned in every response.
- **Audit trail**: append-only, hash-chained events covering tool calls, agent
  runs, governance decisions, approvals, execution, anchoring and verification.
- **Metrics**: counted from audit events, so they survive restarts and cannot
  disagree with the trail.

## Dashboard

Four entries. **Demo** is one guided page that tells the whole story in plain
language and performs each step as the persona it belongs to. **Audit & Verify**
holds receipts, on-chain records and the audit trail. **Architecture** explains
the roles. **Technical Details** exposes every record as stored, with a mock
identity picker.
