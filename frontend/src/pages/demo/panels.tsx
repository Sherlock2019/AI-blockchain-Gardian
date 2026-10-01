// The steps of the guided demo, each a plain-language view of one backend result.

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { EvidenceList } from "../../components/Governance";
import { Field, Hash, Notice, money, when } from "../../components/ui";
import { api } from "../../services/api";
import { useAsync } from "../../services/useAsync";
import type { Action, AgentRun, GovernanceDecision, Invoice, Receipt, Supplier, User } from "../../types";
import {
  DECISION_HEADLINE,
  RECOMMENDATION_HEADLINE,
  WORK_STEPS,
  decisionReason,
  findings,
  knowledgeSearched,
  roleName,
} from "./plain";

const DECISION_TONE: Record<string, string> = { ALLOW: "good", REQUIRE_APPROVAL: "warn", DENY: "bad" };
const RISK_TONE: Record<string, string> = { LOW: "good", MEDIUM: "warn", HIGH: "bad", CRITICAL: "bad" };

export function Step({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  return (
    <section className="step">
      <span className="eyebrow">{label}</span>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

/** The agent's work made visible. `done` is how many steps have finished. */
export function WorkProgress({ done }: { done: number }) {
  return (
    <Step label="AI at work" title="AI Treasury Agent is working…">
      <ol className="work" aria-live="polite">
        {WORK_STEPS.map((step, index) => (
          <li key={step} className={index < done ? "work-done" : index === done ? "work-active" : ""}>
            {step}
          </li>
        ))}
      </ol>
    </Step>
  );
}

export function AiResult({
  run,
  decision,
  invoice,
  supplier,
  manipulated,
}: {
  run: AgentRun;
  decision: GovernanceDecision | null;
  invoice: Invoice;
  supplier: Supplier | null;
  /** The run asked for something outside the agent's scope: its advice is not to be trusted. */
  manipulated: boolean;
}) {
  const tone = manipulated
    ? "bad"
    : run.recommendation === "PAYMENT_RECOMMENDED"
      ? "good"
      : run.recommendation === "MANUAL_REVIEW"
        ? "warn"
        : "bad";
  return (
    <Step label="AI recommendation" title={manipulated ? "What the AI said" : "What the AI found"}>
      <div className={`headline headline-${tone}`}>
        <span className="headline-title">
          {manipulated ? "The AI was manipulated" : RECOMMENDATION_HEADLINE[run.recommendation]}
        </span>
        <span className="headline-sub">
          {manipulated
            ? "It recommended payment and asked for an action it is not allowed to take"
            : `${money(invoice.amount)} · ${supplier?.name ?? invoice.supplier_id}`}
        </span>
      </div>
      <p>
        {manipulated && <strong>The AI's words: </strong>}
        {run.reasoning_summary}
      </p>
      <p className="muted">A recommendation is advice. It does not authorise anything.</p>

      <div className="two-col">
        <div>
          <h3>Why?</h3>
          <ul className="finding-list">
            {findings(decision, run.retrieved_sources).map((finding) => (
              <li key={finding.text} className={finding.ok ? "finding-ok" : "finding-bad"}>
                {finding.text}
              </li>
            ))}
          </ul>
          <p className="muted">Each line was checked against company records by the policy engine, not by the AI.</p>
        </div>
        <div>
          <h3>How did the AI know?</h3>
          <p>The AI searched trusted company knowledge:</p>
          <ul className="finding-list">
            {knowledgeSearched(run.retrieved_sources).map((item) => (
              <li key={item.label} className={item.found ? "finding-ok" : "finding-none"}>
                {item.label}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <details>
        <summary>Sources used and technical details (RAG retrieval, source IDs)</summary>
        <p className="muted">
          Records are fetched by exact ID. Policy clauses are found by vector retrieval over the company
          policy documents; the similarity score is shown. Citations are the documents the agent's tools
          returned, so the model cannot cite something it never read.
        </p>
        <EvidenceList sources={run.retrieved_sources} />
        <p className="muted">
          Model {run.model_provider}/{run.model_name} · run {run.run_id} · <Link to={`/technical/invoices/${invoice.id}`}>full record</Link>
        </p>
      </details>
    </Step>
  );
}

export function GovernanceResult({
  action,
  approver,
  busy,
  onDecide,
}: {
  action: Action;
  approver: User | null;
  busy: boolean;
  onDecide: (approve: boolean) => void;
}) {
  const decision = action.decision;
  if (!decision) return null;
  const waiting = action.status === "PENDING_APPROVAL";
  return (
    <Step label="Governance decision" title="What company policy says">
      <div className="verdict-row">
        <div className={`pill pill-${RISK_TONE[decision.risk_level]}`}>
          <span>Risk</span>
          <strong>{decision.risk_level}</strong>
        </div>
        <div className={`pill pill-${DECISION_TONE[decision.decision]} pill-wide`}>
          <span>Governance decision</span>
          <strong>{DECISION_HEADLINE[decision.decision]}</strong>
        </div>
      </div>
      <h3>Why?</h3>
      <p>{decisionReason(decision)}</p>
      {decision.decision === "DENY" && (
        <ul className="finding-list">
          {decision.reasons.map((reason) => (
            <li key={reason} className="finding-bad">
              {reason}
            </li>
          ))}
        </ul>
      )}
      <p className="muted">
        This decision is made by deterministic rules in code. The AI's recommendation is not an input,
        except that AI doubt can add a human review.
      </p>

      {waiting && approver && (
        <div className="decide">
          <p>
            You are now <strong>{approver.name}</strong> ({roleName(approver.role)}, approval limit{" "}
            {money(approver.approval_limit)}). The decision is yours.
          </p>
          <div className="row">
            <button className="big approve" disabled={busy} onClick={() => onDecide(true)}>
              Approve payment
            </button>
            <button className="big reject" disabled={busy} onClick={() => onDecide(false)}>
              Reject
            </button>
          </div>
        </div>
      )}
      {action.status === "REJECTED" && action.approval && (
        <Notice tone="neutral">
          Rejected by {action.approval.user_id}. No payment was made.
        </Notice>
      )}
      {action.last_error && action.status !== "EXECUTED" && <Notice tone="bad">{action.last_error}</Notice>}
    </Step>
  );
}

/** The prompt-injection story: what was asked, where it was stopped, and why that matters. */
export function AttackResult({ invoice, attack }: { invoice: Invoice; attack: Action }) {
  const reason = attack.decision?.reasons[0] ?? "";
  return (
    <Step label="AI attack" title="The invoice tried to give the AI orders">
      <p>The invoice notes, written by whoever sent the invoice, say:</p>
      <blockquote className="untrusted">{invoice.notes}</blockquote>
      <p>
        In this demo the model is set to obey that text, to simulate an AI that has been successfully
        manipulated.
      </p>
      <div className="gate">
        <div className="gate-box">
          <span className="eyebrow">AI agent request</span>
          <code className="gate-request">{attack.action_type}</code>
          {Object.entries(attack.params).map(([key, value]) => (
            <span key={key} className="muted">
              {key.replace(/_/g, " ")}: {value}
            </span>
          ))}
        </div>
        <div className="gate-arrow" aria-hidden="true">→</div>
        <div className="gate-box">
          <span className="eyebrow">Security gate</span>
          <span>Checking agent permissions…</span>
        </div>
        <div className="gate-arrow" aria-hidden="true">→</div>
        <div className="gate-box gate-blocked">
          <span className="eyebrow">Result</span>
          <strong>Action blocked</strong>
        </div>
      </div>
      <p>
        <strong>Reason:</strong> the Treasury AI Agent does not have permission to modify supplier bank
        information. <span className="muted">({reason})</span>
      </p>
      <p>
        Because the agent asked for something outside its scope, the payment it requested in the same
        run was refused as well. No bank detail changed and no money moved.
      </p>
      <div className="principle-banner">
        <strong>The LLM is not the security boundary.</strong>
        <span>
          Even if an AI model is manipulated or makes a mistake, deterministic authorisation controls
          remain outside the model.
        </span>
      </div>
    </Step>
  );
}

export function Outcome({ action, receipt, users }: { action: Action; receipt: Receipt; users: User[] }) {
  const decision = action.decision;
  const approver = users.find((u) => u.id === action.approval?.user_id);
  const byAgent = action.principal_kind === "AGENT";
  const requester = byAgent ? "Agent" : "Requester";
  return (
    <Step label="Execution" title="What happened next">
      <div className="outcome">
        {action.approval ? (
          <div className="outcome-card">
            <span className="eyebrow">Human approval recorded</span>
            <strong>{approver?.name ?? action.approval.user_id}</strong>
            <span>{money(action.amount)} · Approved</span>
            <span className="muted">{when(action.approval.timestamp)}</span>
          </div>
        ) : (
          <div className="outcome-card">
            <span className="eyebrow">Human approval</span>
            <strong>Not required</strong>
            <span className="muted">Within the limit for release without a second approver.</span>
          </div>
        )}
        <div className="outcome-card">
          <span className="eyebrow">Policy check</span>
          <ul className="finding-list">
            <li className="finding-ok">{requester} identity verified</li>
            <li className="finding-ok">{requester} permission verified</li>
            <li className="finding-ok">
              {action.approval ? "Human authority verified" : "No human authority needed"}
            </li>
            <li className="finding-ok">Payment policy satisfied</li>
          </ul>
          <span className="muted">Re-checked at execution time, policy {decision?.policy_version}.</span>
        </div>
        <div className="outcome-card">
          <span className="eyebrow">Mock payment executed</span>
          <strong>{receipt.execution_result.transaction_id}</strong>
          <span>{receipt.execution_result.status}</span>
          <span className="muted">No real money. No real payment provider.</span>
        </div>
      </div>
    </Step>
  );
}

const PROOF_CHAIN = [
  "AI agent",
  "Evidence",
  "Policy decision",
  "Human approval",
  "Payment result",
  "Execution receipt",
  "SHA-256 fingerprint",
  "Smart contract",
  "Blockchain proof",
];

export function ReceiptProof({ receipt, demoMode, onChanged }: { receipt: Receipt; demoMode: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tampered = receipt.tampered_in_demo;
  // Verification runs by itself, and again whenever the stored record changes.
  const check = useAsync(() => api.verify(receipt.receipt_id), [receipt.receipt_id, tampered, receipt.anchor_status]);
  const result = check.data;
  const simulated = result?.ledger_mode === "SIMULATED";
  const original = tampered ? String(Number(receipt.amount) / 10) : receipt.amount;

  useEffect(() => setError(null), [receipt.receipt_id]);

  const change = (call: () => Promise<unknown>) => {
    setBusy(true);
    call()
      .then(() => setError(null))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => {
        setBusy(false);
        onChanged();
      });
  };

  return (
    <>
      <Step label="Proof" title="Verifiable AI receipt created">
        <p>
          TrustChain creates a cryptographic fingerprint of the AI action, its evidence, the policy
          decision and the human approval. That fingerprint is recorded on a blockchain, so the
          execution record can later be checked independently of this application's database.
        </p>
        <ol className="proof-chain">
          {PROOF_CHAIN.map((link) => (
            <li key={link}>{link}</li>
          ))}
        </ol>

        {check.error && <Notice tone="bad">{check.error}</Notice>}
        {result && !tampered && (
          <div className={`stamp stamp-${result.status === "VERIFIED" ? "good" : "warn"}`} role="status">
            {result.status === "VERIFIED"
              ? simulated
                ? "Verified ✓ (simulated ledger)"
                : "Blockchain verified ✓"
              : result.status.replace(/_/g, " ")}
          </div>
        )}
        {result && !tampered && result.status !== "VERIFIED" && (
          <p className="muted">{result.details.join(" ")}</p>
        )}
        {simulated && (
          <p className="muted">
            This run uses an in-memory stand-in for the chain. Start with <code>make demo</code> for a real
            local blockchain and contract.
          </p>
        )}
        <p className="muted">
          What this proves: the record has not changed since it was written. It does not prove the AI was
          right, or that the record was true to begin with.
        </p>

        <details>
          <summary>View technical details</summary>
          <dl className="fields">
            <Field label="Agent ID">{receipt.agent_id ?? "None (manual workflow)"}</Field>
            <Field label="Policy version">{receipt.policy_version}</Field>
            <Field label="Timestamp">{when(receipt.timestamp)}</Field>
            <Field label="Block number">{receipt.block_number}</Field>
          </dl>
          <dl className="fields single">
            <Field label="Receipt hash (SHA-256)">
              <Hash value={receipt.receipt_hash} full />
            </Field>
            <Field label="Transaction hash">
              <Hash value={receipt.blockchain_tx_hash} full />
            </Field>
            <Field label="Contract address">
              <Hash value={result?.contract_address} full />
            </Field>
          </dl>
          <Link to={`/audit/receipts/${receipt.receipt_id}`}>Open the full receipt</Link>
        </details>
      </Step>

      {demoMode && (
        <Step label="Try to cheat" title="What if someone changes the record afterwards?">
          <p>
            Imagine someone with access to the database changes the stored payment record from{" "}
            <strong>{money(original)}</strong> to <strong>{money(String(Number(original) * 10))}</strong> after
            execution, and covers their tracks inside the database.
          </p>
          {error && <Notice tone="bad">{error}</Notice>}
          {!tampered ? (
            <button className="big danger" disabled={busy} onClick={() => change(() => api.tamper(receipt.receipt_id, true))}>
              Simulate audit record tampering
            </button>
          ) : (
            <>
              <div className="compare">
                <div>
                  <span className="eyebrow">Local record · original</span>
                  <strong>{money(original)}</strong>
                </div>
                <div className="compare-arrow" aria-hidden="true">→</div>
                <div className="compare-bad">
                  <span className="eyebrow">Local record · modified</span>
                  <strong>{money(receipt.amount)}</strong>
                </div>
              </div>
              {result && (
                <div className={`alarm alarm-${result.status === "TAMPER_DETECTED" ? "bad" : "warn"}`} role="alert">
                  <span className="alarm-title">{result.status.replace(/_/g, " ")}</span>
                  <span>
                    The current record no longer matches the cryptographic fingerprint registered when the
                    action occurred.
                  </span>
                  {result.local_match && result.chain_match === false && (
                    <span>
                      The database looks consistent on its own. Only the fingerprint held outside it
                      exposes the change.
                    </span>
                  )}
                </div>
              )}
              <button disabled={busy} onClick={() => change(() => api.restore(receipt.receipt_id))}>
                Restore the original record
              </button>
            </>
          )}
        </Step>
      )}
    </>
  );
}
