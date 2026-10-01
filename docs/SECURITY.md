# Security

This is a proof of concept. It implements the controls that make the
architecture's argument, and it is explicit about the ones it fakes. Nothing
here should be read as "secure"; read it as "this is where each control goes
and this is how far the PoC takes it".

## Principle

**The LLM is never the security boundary.** Authorisation, permissions,
financial thresholds and execution controls are deterministic code outside the
model. The model's output is untrusted input.

## Trust boundaries

| Boundary | Untrusted side | Control | Strength |
|---|---|---|---|
| Invoice text → model | Third-party text | Delimiting in the prompt; heuristic detector | Weak, advisory |
| Model → agent | Model output | Schema validation; discard on failure | Real |
| Agent → governance | The request | Facts re-loaded from the database; allow-list; thresholds | Real |
| Caller → API | HTTP input | Pydantic schemas, unknown fields rejected, id patterns | Real |
| Caller → identity | `X-User-Id` header | None | **Mock** |
| Person → approval | The approver | Role rank, limit, four-eyes, action-hash binding | Real, on top of mock identity |
| Workflow → payment tool | The caller | State transition, unique constraints, idempotency key | Real |
| Backend → contract | The backend | Recorder role, registry checks, write-once | Real in mechanism, single operator in practice |
| Database → verifier | Stored records | Recomputed hash compared with on-chain hash | Real in mechanism |

## Threat model

### LLM hallucination
*Risk:* the model states a wrong amount, supplier or conclusion.
*Controls:* the request is compared with the invoice on record
(`request_matches_record`); cited evidence must exist; a non-positive
recommendation forces human review; malformed output is discarded and nothing
is proposed.
*Residual:* a wrong but plausible *explanation* can still mislead an approver.
The approval screen shows the deterministic checks beside the model's text for
that reason.

### Prompt injection
*Risk:* text in an invoice instructs the model.
*Controls, weakest first:*
1. The prompt delimits third-party text and says to treat it as data. Helps; cannot be relied on.
2. A regex tripwire flags instruction-like text. Trivially evaded. It can only *add* human review.
3. The agent has no tool that changes anything.
4. Any requested action passes the permission allow-list. The agent holds five permissions.
5. If one request in a run is out of scope, all requests from that run are denied.

The demo sets the mock model to *obey* the injection, so what is demonstrated
is controls 3 to 5 holding after 1 and 2 have failed.
*Residual:* injection that stays inside the agent's scope, such as text that
talks the model into recommending a legitimate-looking payment. It still meets
policy checks and, above $1,000, a human.

### Tool abuse
*Risk:* the agent uses a tool for something unintended.
*Controls:* read-only tools; per-call permission check and audit event; the
supplier account token is not returned to the agent; at most three extra
requested actions per run.

### Privilege escalation
*Risk:* the agent or the backend widens the agent's authority.
*Controls:* agent permissions are data the agent cannot write; no endpoint
changes them; on-chain permissions are set by an admin key the backend does not
use, and checked before agent-originated execution.
*Residual:* anyone with database write access can edit the `agents` table. The
on-chain registry then still refuses, which is the point of having two.
In this PoC both keys live on one Hardhat node.

### Malicious user
*Risk:* an insider approves beyond their authority, or their own request.
*Controls:* role rank, approval limit, requester ≠ approver, one decision per
action (unique constraint), approval bound to the action hash and re-verified
at execution.
*Residual:* **identity is mocked.** Any caller can claim to be any user, and the
guided demo deliberately acts as each persona. Collusion between two real
approvers is out of scope.

### Compromised agent
*Risk:* the agent process is attacker-controlled.
*Controls:* everything it can do is `submit` a request; governance treats the
request as claims. The kill switch refuses agent requests, including those
awaiting approval. On-chain deactivation stops agent-originated execution
independently of the application database.

### Duplicate execution
*Risk:* an invoice is paid twice through retries, double clicks or races.
*Controls:* governance denies when a payment exists or another request is in
flight; execution is claimed by a compare-and-set update; the payments table
has a unique constraint on `invoice_id` and on the idempotency key (the action
hash); the contract refuses a second record for the same action.
*Residual:* the mock payment lives in the same database as the receipt, so both
commit atomically. A real provider would not. That needs the provider's own
idempotency key, an outbox, and reconciliation for "paid but not recorded".
At startup, actions left EXECUTING by a crashed process are returned to
AUTHORIZED; this is correct for one instance and would need a lease for several.

### Audit tampering
*Risk:* someone edits a receipt or audit event after the fact.
*Controls:* receipts are hashed over canonical JSON, chained, and anchored
on-chain; verification recomputes and compares. Editing the amount *and* the
stored hash leaves the database self-consistent and is caught only by the
on-chain hash. Audit events are hash-chained.
*Residual:* the audit-event chain is not anchored, so a full rewrite of that
table is undetectable; only receipts are. A record altered before anchoring is
anchored altered. A local chain can be reset by its operator.

### Sensitive-data leakage
*Risk:* business or personal data reaches logs, the model or the chain.
*Controls:* only hashes go on-chain; logs redact secret-like keys and invoice
free text; the agent does not receive supplier account tokens; error responses
carry a correlation id, not internals.
*Residual:* with a hosted model, invoice content leaves the organisation. That
is a data-processing decision this PoC does not make for you. Hashes of
low-entropy identifiers are guessable.

### Smart-contract bugs
*Risk:* a flaw in the registry.
*Controls:* small contract, no external calls, no value held, custom errors,
24 tests including unauthorised callers. Solidity 0.8 checked arithmetic.
*Residual:* not audited. No upgrade or pause mechanism. A single admin key
with no multisig or timelock. Local network only, by configuration.

## Implemented PoC controls

- Input validation with Pydantic; unknown fields rejected; identifier patterns.
- Role-based authorisation and approval limits.
- Agent permissions by allow-list, with explicit denies.
- AI reasoning separated from deterministic authorisation.
- No secrets in the repository. `.env` is ignored; `.env.example` holds no
  secret values. No private key is configured anywhere: transactions use the
  Hardhat node's unlocked account.
- Sanitised structured logs.
- Nothing sensitive on-chain.
- Idempotent payment execution.
- Per-user rate limiting (in-process).
- Demo-only endpoints (`/api/demo/*`) gated by `DEMO_MODE`.

## Known gaps, stated plainly

| Gap | What a real deployment needs |
|---|---|
| Mock authentication | OIDC/SAML, session management, MFA for approvers |
| HMAC "signature" held by the server | Approver-held keys: WebAuthn, HSM-backed user keys, or EIP-712 |
| `DEMO_MODE` defaults to true | False by default; the tamper endpoint must not exist in production builds |
| Single chain operator | Separate custody of admin and recorder keys; multisig admin; a network other parties can read |
| No TLS, no CSRF consideration | Terminate TLS; cookie-based sessions would need CSRF protection |
| In-process rate limiter | Gateway or shared store |
| Audit events not anchored | Periodic anchoring of the chain head |
| No background retry for anchoring | Outbox and worker |
| SQLite | A database with row-level locking and proper isolation |
| Injection detection is regex | Treat as defence in depth only; evaluate models against an injection corpus |

## Reporting

This is a portfolio project with no production deployment. Open an issue.
