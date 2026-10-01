# Engineering review

A review of this repository written the way a staff engineer would review a
candidate's project: where does it look like a tutorial, a hackathon entry,
generated boilerplate, fake enterprise architecture, gratuitous blockchain or
unsafe agent design? Each finding says what was done about it, or that nothing
was and why.

The repository was built from an empty directory, so the "before" in each
finding is the obvious first implementation of the brief, which is what most
projects of this kind ship.

## 1. Insecure agentic design

| Finding in the obvious implementation | Status | What this repository does |
|---|---|---|
| Governance trusts the fields of the agent's request | Fixed | `FactLoader` re-reads everything from the database; request fields are compared with the record (`request_matches_record`) |
| The agent holds a payment tool guarded by a prompt or an `if` | Fixed | The tool gateway has no write tools; only `PaymentWorkflow` can call the payment service |
| "Prompt-injection defence" is a regex | Reframed | The regex exists and is documented as a tripwire that can only add review. The control is the permission allow-list, demonstrated with a model configured to *obey* the injection |
| Approval is a boolean on the action | Fixed | Approval is a signed record bound to the action hash; execution re-verifies binding, signature and the approver's authority |
| Checks run once, at request time | Fixed | Governance is re-evaluated at approval and at execution. Tests block a supplier between request and approval |
| The model's confidence gates autonomy | Fixed | Confidence is displayed and never read by governance. A negative recommendation adds review; nothing the model says removes one |
| Unknown action types crash or pass | Fixed | `action_type` is a free string so it can be recorded; anything not in the rules is denied |
| One bad request in a run, the rest proceed | Fixed | An out-of-scope request poisons the run |

## 2. Fake enterprise architecture

| Finding | Status | Detail |
|---|---|---|
| Five "engines" that are one function split into classes | Partly accepted | Identity, permission, policy, risk and approval are separate because they are tested separately and change for different reasons. They are plain classes composed in `GovernanceEngine`; there is no bus, no plugin system, no service per engine |
| Repository layer wrapping the ORM one-to-one | Avoided | Services use SQLAlchemy sessions directly. The one deliberate seam is `FactLoader`, because it is what keeps governance pure |
| Dependency-injection framework | Avoided | One composition root, `container.py`, about 130 lines |
| Microservices | Avoided | One API process |
| Metrics kept in process counters | Fixed | Counted from the audit trail |
| "Digital signature" that is a random string | Reframed | It is an HMAC, it is verified at execution, and it is labelled mock with the reason it is not non-repudiation |

## 3. Unnecessary blockchain usage

The question an interviewer should ask is "what does the chain do that a
database row does not?".

| Finding | Status | Detail |
|---|---|---|
| Contract is a `mapping(bytes32 => bytes32)` notary | Fixed | The contract holds an agent registry with separated admin and recorder roles and refuses records that violate it |
| Backend holds the owner key and can do anything | Fixed | The backend's ledger interface has no admin operations; registration is done by the deploy script with a different account |
| Tamper demo only changes the amount | Fixed | The demo also rewrites the stored hash. Only then does the external anchor matter, and a test asserts `local_match is True` while `chain_match is False` |
| Claims that blockchain makes the AI trustworthy | Avoided | The UI and docs state that it proves integrity since anchoring and nothing about truth |
| "Why not a database?" unanswered | Answered | `ARCHITECTURE.md` lists the conventional tool that suffices for each need and when a ledger earns its cost |
| Local chain presented as decentralised trust | Disclosed | Stated in the README, the architecture page and the docs: one node, one operator |

Not fixed: admin and recorder are two accounts on the same Hardhat node. Real
separation needs separate custody, which a single-machine demo cannot show.

## 4. Tutorial and hackathon tells

| Tell | Status |
|---|---|
| Floats for money | Fixed: `Decimal`, integer cents, canonical strings; floats rejected from hashed data |
| Happy-path tests only | Fixed: forged approvals, edited amounts, ledger outage, crash mid-execution, malformed model output, request floods |
| Tests that pass because the mock ledger differs from the contract | Mitigated: six tests run the backend against the real contract; CI fails if they are skipped |
| Business logic in route handlers | Avoided: routes validate, call a service, present |
| `except Exception: pass` | Avoided, with two deliberate broad catches (model call, ledger transport), each converting to a typed outcome |
| Secrets in the repository | None. No private key exists anywhere; the Hardhat node's unlocked account signs |
| README promises more than the code does | Checked: every scenario in the README is asserted by `scripts/smoke.py` and the test suite |

## 5. Findings from reviewing the finished code

Problems found after the first complete pass, and what happened to each.

1. **A crash between claiming an action and paying stranded the invoice.** The
   action stayed `EXECUTING`, which also blocked any new request as a
   duplicate. *Fixed:* interrupted actions return to `AUTHORIZED` at startup,
   with a test. Single-instance only; noted in SECURITY.md.
2. **One broad RAG query missed the approval-threshold clause.** *Fixed:* one
   focused query per control.
3. **The injected run was shown under a green "payment appears valid" banner.**
   Accurate (it is what the manipulated model said) and misleading at a glance.
   *Fixed:* a manipulated run is labelled as such.
4. **"Previous payment history" was claimed as an AI source but only governance
   read it.** *Fixed:* a read tool, cited and passed to the model.
5. **The verified-receipts metric stayed true after tampering.** *Fixed.*
6. **The audit hash chain races under concurrent writers.** Two requests can
   read the same previous hash. *Not fixed:* SQLite serialises writers in
   practice; a real database needs a sequence lock or a single writer. Documented.
7. **Audit events are chained but not anchored.** A full rewrite of that table
   is undetectable. *Not fixed.* Documented; on the roadmap.
8. **No background retry for anchoring.** Retry is a manual endpoint. *Not
   fixed.* Documented.
9. **`DEMO_MODE` defaults to true**, which exposes an endpoint that edits audit
   records. Correct for a demo, wrong anywhere else. Documented, gated, tested
   when off.
10. **The guided demo acts as each persona.** That is the mock authentication
    made visible. Documented; Technical Details still has the identity picker
    and the API enforces authority per caller.

## 6. What I would challenge in an interview

- The mock model is rules in a trench coat. The architecture's claim does not
  depend on model quality, but nothing here measures a real model's
  recommendation accuracy or injection resistance.
- The rules file and the prose policies can drift. The policy hash makes drift
  visible, not impossible.
- Risk scoring is a few additive factors. It is deterministic and explainable,
  and that is all it is.
- The contract has a single admin key, no multisig, no pause, no upgrade path.
- SQLite hides concurrency problems that Postgres would surface.
