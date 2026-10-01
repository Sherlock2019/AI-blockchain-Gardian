# TrustChain AI

**Human-Governed, Web3-Verifiable Autonomous AI Agents**

> AI investigates. Policy controls. Humans decide. Blockchain proves what happened.

A runnable proof of concept: an AI treasury agent that does the investigative
work on supplier invoices, inside a system where it has no authority to move
money. Mock data, mock payments, local blockchain. No API key, cloud account or
cryptocurrency needed.

## The problem

A finance team checks every supplier invoice by hand: find the supplier, find
the purchase order, check the contract, find the right policy, compare amounts,
work out who must approve. An AI agent can do that investigation in seconds.

The moment an agent can also *act*, an organisation has to be able to answer:

- Who authorised the agent, and what was it allowed to do?
- What evidence did it use?
- Who approved the action?
- What was actually executed?
- Has the audit record been changed since?

## The solution

**AI is powerful, but AI is not the authority.**

| | |
|---|---|
| The model | recommends |
| The agent | requests an action |
| The policy engine | decides whether it is permitted, in deterministic code |
| A human | approves where policy requires it |
| The smart contract | refuses records that break the agent registry's rules |
| The blockchain | makes later edits to the record detectable |

```mermaid
flowchart TD
    U[Finance user] --> D[Dashboard]
    D --> API[FastAPI]
    API --> AG[Treasury agent<br/>read-only tools]
    AG --> LLM[LLM<br/>mock or OpenAI-compatible]
    AG --> RAG[RAG over policies<br/>and contracts]
    AG -->|proposed action| GOV
    API -->|manual request<br/>when AI is off| GOV

    subgraph GOV[Governance engine: deterministic, outside the model]
        ID[Identity] --> PERM[Permissions] --> POL[Policy] --> RISK[Risk]
    end

    GOV -->|DENY| X[Denied and audited]
    GOV -->|ALLOW| EXEC
    GOV -->|REQUIRE_APPROVAL| H[Human approver<br/>role, limit, four-eyes]
    H -->|approve: governance re-evaluated| EXEC
    H -->|reject| X

    EXEC[Workflow: single executor] --> REG{On-chain registry:<br/>agent active and permitted?}
    REG -->|no| X
    REG -->|yes| PAY[Mock payment tool<br/>idempotent]
    PAY --> RCP[Execution receipt<br/>SHA-256 of canonical JSON]
    RCP --> SC[TrustChainRegistry.sol]
    SC --> V[Verification:<br/>recompute and compare]
```

## Quick start

Requires Python 3.12, Node 20+ and `make`. Or just Docker.

```bash
git clone <this repository> && cd trustchain-ai

# Option A: Docker
docker compose up --build

# Option B: local processes
make install
make demo
```

Open **http://localhost:5173** and choose *Run the 5-minute demo*.
API documentation is at http://localhost:8000/docs.

**On a server (AWS EC2):** `WEB_PORT=80 docker compose up --build -d`, then
open the address printed by `scripts/public-url.sh 80`. Only the web UI port is
published; the API and the chain stay on loopback. The demo has mock
authentication, so restrict the security group to your own IP. See
[docs/DEPLOY_EC2.md](docs/DEPLOY_EC2.md).

`make demo-lite` starts without the Hardhat node. The ledger is then simulated
inside the backend and labelled SIMULATED wherever it appears.

Check a running stack from the command line:

```bash
python3 scripts/smoke.py     # runs every demo story over HTTP and asserts the outcomes
```

## Screenshots

| | |
|---|---|
| ![Landing page](docs/screenshots/landing.png) | ![Guided demo: approval required](docs/screenshots/demo-approval.png) |
| ![Prompt injection blocked](docs/screenshots/demo-attack.png) | ![Tamper detected](docs/screenshots/demo-tamper.png) |

## Demo scenarios

The guided demo page covers the first four. All of them are in
[docs/DEMO.md](docs/DEMO.md) and asserted by the test suite.

| # | Invoice | Scenario | Outcome |
|---|---|---|---|
| 1 | INV-2026-0043 | $500, approved supplier | Released automatically |
| 2 | INV-2026-0042 | $50,000 | Finance Manager approval |
| 3 | INV-2026-0044 | $250,000 | CFO approval; the manager is refused |
| 4 | INV-2026-0045 | Blocked supplier | Denied |
| 5 | INV-2026-0046 | Invoice exceeds purchase order | Denied |
| 6 | INV-2026-0047 | Prompt injection in invoice notes | Bank-account change denied; whole run refused |
| 7 | INV-2026-0040 | Already paid | Denied as duplicate |
| 8 | INV-2026-0048 | AI switched off | Processed manually under the same controls |
| 9 | any receipt | Stored amount edited after execution | TAMPER DETECTED |

## Features

- **Treasury agent** with read-only tools, a local RAG pipeline with citations,
  and a mock model so everything runs offline. An OpenAI-compatible provider is optional.
- **Governance engine** as a pure function: identity, allow-list permissions,
  payment policy, risk scoring, approval routing. Facts come from the system of
  record; the request's amount and supplier are claims that get checked.
- **Human approval** with role rank, approval limits and no self-approval. An
  approval is signed over the hash of the exact action it was given for.
- **Idempotent execution**: one executor, a compare-and-set state transition,
  one payment per invoice enforced by a unique constraint.
- **Execution receipts**: canonical JSON, SHA-256, hash-chained, anchored in a
  Solidity contract, verifiable from the dashboard.
- **Kill switch**: with AI off, the agent is refused and people process invoices
  through the same governance, approval and execution path.
- **Observability**: JSON logs with a correlation id per request, a hash-chained
  audit trail, and metrics derived from it.

## Security model

The LLM is never the security boundary. Short version:

| Threat | What stops it |
|---|---|
| Prompt injection | The agent has no tool that changes anything; the requested action fails the permission allow-list; the rest of that run is refused |
| Hallucinated amount or supplier | The request is compared with the invoice on record |
| Agent exceeds authority | Autonomous limit and approval tiers in code; on-chain registry the backend cannot write to |
| Approver exceeds authority | Role rank, approval limit and four-eyes checks |
| Approve A, execute B | Approval is bound to the action hash and re-verified at execution |
| Duplicate payment | In-flight check, state transition, unique constraint, idempotency key |
| Edited audit record | Recomputed receipt hash compared with the on-chain hash |

Authentication is mocked, the approval signature is a server-side HMAC, and the
chain is a single local node. The full threat model and every known limitation
are in [docs/SECURITY.md](docs/SECURITY.md).

## Web3 design

The contract ([TrustChainRegistry.sol](blockchain/contracts/TrustChainRegistry.sol))
does two things:

1. **Agent registry.** Agents and their permissions are registered by an *admin*
   key. The backend holds only a *recorder* key and cannot register an agent or
   grant a permission. Before an agent's action executes, the workflow asks the
   contract whether that agent is active and permitted.
2. **Write-once evidence.** Approval and receipt hashes are recorded once per
   action. `recordExecution` reverts for an unregistered, inactive or
   unpermitted agent, for a second write, and for an approval hash that does not
   match the one already recorded.

Only hashes go on-chain. No invoice content, prompt, retrieved text or personal data.

**Why not just a database?** For one organisation with one trusted
administrator, a signed append-only log is simpler and sufficient. A ledger is
worth its cost when several parties must verify the same record without
trusting each other's database. This repository runs one local node, so it
demonstrates the mechanism and not that trust property. The longer answer,
including what blockchain does *not* prove, is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#why-not-just-use-a-database).

## Human-SAFE AI

An engineering principle, not a philosophy: **S**ustainable, **A**ugmentative,
**F**ail-safe, **E**mpowering. Each maps to something testable in this
repository. See [docs/HUMAN_SAFE_AI.md](docs/HUMAN_SAFE_AI.md).

## Tests

```bash
make test          # 147 backend tests + 24 contract tests
make test-chain    # backend against the real contract (needs `make chain` and `make deploy`)
make lint
```

CI runs all of it, including the backend-to-contract tests against a live
Hardhat node, and fails if those are skipped.

## Repository layout

```
backend/app/
  agents/         LLM abstraction, tool gateway, TreasuryAgent
  rag/            chunking, embeddings, index, retriever
  governance/     identity, permissions, policy, risk, approval, engine, facts
  services/       workflow (the executor), payment, receipts, requests
  blockchain/     ledger interface, web3 client, in-memory double
  security/       mock auth, signing, hashing, injection tripwire, rate limit
  observability/  logging, audit trail, metrics
  api/            routes, request schemas, presenters
blockchain/       Solidity contract, Hardhat tests, deploy script, admin tasks
frontend/src/     guided demo, audit and verification, architecture, technical details
data/             synthetic suppliers, invoices, POs, contracts, users, agents, policies
docs/             ARCHITECTURE, SECURITY, DEMO, DEPLOY_EC2, HUMAN_SAFE_AI, ENGINEERING_REVIEW
```

## Limitations

- **Authentication is mocked.** Identity is an `X-User-Id` header.
- **The approval signature is not non-repudiable.** It is an HMAC with a server secret.
- **One local chain, one operator.** Admin and recorder are separate accounts on
  the same Hardhat node. No real key management.
- **Anchoring proves integrity since anchoring**, not that the receipt was true,
  and not that the AI was right.
- **The mock model is rule-based.** The optional OpenAI-compatible provider is
  implemented but has not been exercised against a live endpoint in tests.
- **Retrieval is lexical.** Fine for a few dozen policy clauses; not for a real corpus.
- **Single instance.** Rate limiting, the audit hash chain and crash recovery
  assume one backend process.
- **The payment is in the same database as the receipt**, so they commit
  together. A real payment provider breaks that; see SECURITY.md.

## Roadmap

1. Real identity (OIDC) and approver-held signing keys (WebAuthn or EIP-712).
2. Outbox and background worker for ledger anchoring and for a real payment provider.
3. Embedding model and a vector database behind the existing `Embedder` and `VectorIndex` interfaces.
4. Policy rules in a policy language (OPA/Cedar) with the same decision record.
5. Multi-party deployment: registry admin held by a risk function, verification by an external auditor.
6. Evaluation harness for the agent: recommendation accuracy and injection resistance across models.

## License

MIT. See [LICENSE](LICENSE).
