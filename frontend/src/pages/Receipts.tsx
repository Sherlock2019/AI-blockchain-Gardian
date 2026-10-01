import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge, Card, Field, Hash, LoadState, Notice, PageHeader, money, when } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";
import type { Receipt, Verification } from "../types";

function VerificationResult({ result }: { result: Verification }) {
  const verified = result.status === "VERIFIED";
  const tone = verified ? "good" : result.status === "TAMPER_DETECTED" ? "bad" : "warn";
  return (
    <div className={`verdict verdict-${tone}`} role="status">
      <div className="verdict-title">{result.status.replace(/_/g, " ")}</div>
      <ul>
        {result.details.map((detail) => (
          <li key={detail}>{detail}</li>
        ))}
      </ul>
      <dl className="fields single">
        <Field label="Recomputed from receipt">
          <Hash value={result.recomputed_hash} full />
        </Field>
        <Field label="Stored in database">
          <Hash value={result.stored_hash} full />
        </Field>
        <Field label={`On ledger (${result.ledger_mode.replace("_", " ")})`}>
          <Hash value={result.onchain_hash} full />
        </Field>
      </dl>
    </div>
  );
}

function ReceiptDetail({ receipt, onChanged }: { receipt: Receipt; onChanged: () => void }) {
  const { system } = useApp();
  const [result, setResult] = useState<Verification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setResult(null);
    setError(null);
  }, [receipt.receipt_id]);

  const run = (call: () => Promise<unknown>, verifyAfter = false) => {
    setBusy(true);
    setError(null);
    call()
      .then(() => (verifyAfter ? api.verify(receipt.receipt_id).then(setResult) : setResult(null)))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => {
        setBusy(false);
        onChanged();
      });
  };

  return (
    <Card
      title={receipt.receipt_id}
      aside={
        <div className="row">
          <Badge status={receipt.anchor_status} />
          {receipt.tampered_in_demo && <Badge status="FAIL" label="MODIFIED IN DEMO" />}
        </div>
      }
    >
      <div className="row">
        <button className="primary" disabled={busy} onClick={() => run(() => Promise.resolve(), true)}>
          Verify on blockchain
        </button>
        {receipt.anchor_status !== "ANCHORED" && (
          <button disabled={busy} onClick={() => run(() => api.anchor(receipt.receipt_id))}>
            Retry anchoring
          </button>
        )}
      </div>
      {receipt.anchor_error && <Notice tone="warn">Not anchored: {receipt.anchor_error}</Notice>}
      {error && <Notice tone="bad">{error}</Notice>}
      {result && <VerificationResult result={result} />}

      {system?.demo_mode && (
        <div className="demo-box">
          <strong>Demo: simulate tampering</strong>
          <p className="muted">
            Edits the stored receipt as someone with database access could: the amount is multiplied by
            ten. Then verify again.
          </p>
          <div className="row">
            {receipt.tampered_in_demo ? (
              <button disabled={busy} onClick={() => run(() => api.restore(receipt.receipt_id))}>
                Restore original
              </button>
            ) : (
              <>
                <button disabled={busy} onClick={() => run(() => api.tamper(receipt.receipt_id, false))}>
                  Change the amount
                </button>
                <button disabled={busy} onClick={() => run(() => api.tamper(receipt.receipt_id, true))}>
                  Change the amount and rewrite the stored hash
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <dl className="fields">
        <Field label="Amount">
          <span className={receipt.tampered_in_demo ? "text-bad" : ""}>{money(receipt.amount)}</span>
        </Field>
        <Field label="Requested action">{receipt.requested_action}</Field>
        <Field label="Invoice">{receipt.invoice_id}</Field>
        <Field label="Supplier">{receipt.supplier_id}</Field>
        <Field label="Purchase order">{receipt.purchase_order_id}</Field>
        <Field label="Timestamp">{when(receipt.timestamp)}</Field>
        <Field label="Agent">{receipt.agent_id ?? "None (manual workflow)"}</Field>
        <Field label="Agent version">{receipt.agent_version}</Field>
        <Field label="Requested by">{receipt.requested_by}</Field>
        <Field label="Model">
          {receipt.model_provider} / {receipt.model_name}
        </Field>
        <Field label="Policy version">{receipt.policy_version}</Field>
        <Field label="Risk level">
          <Badge status={receipt.risk_level} />
        </Field>
        <Field label="Governance decision">
          <Badge status={receipt.governance_decision} />
        </Field>
        <Field label="Human approval">
          {receipt.human_approval_id
            ? `${receipt.human_approval_id} (${receipt.human_approval_role})`
            : "Not required"}
        </Field>
        <Field label="Tool executed">
          <code>{receipt.tool_executed}</code>
        </Field>
        <Field label="Execution result">
          {receipt.execution_result.transaction_id} · {receipt.execution_result.status}
        </Field>
      </dl>
      <dl className="fields single">
        <Field label="Retrieved sources">
          <span className="chips">
            {receipt.retrieved_source_ids.map((id) => (
              <code key={id}>{id}</code>
            ))}
          </span>
        </Field>
        <Field label="Previous receipt hash">
          <Hash value={receipt.previous_receipt_hash} full />
        </Field>
        <Field label="Receipt hash (SHA-256 of canonical JSON)">
          <Hash value={receipt.receipt_hash} full />
        </Field>
        <Field label="Blockchain transaction">
          <Hash value={receipt.blockchain_tx_hash} full />
          {receipt.block_number !== null && <span className="muted"> · block {receipt.block_number}</span>}
        </Field>
      </dl>
    </Card>
  );
}

export function ReceiptsPage() {
  const { receiptId } = useParams();
  const { version } = useApp();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useAsync(api.receipts, [version]);
  const selected = data?.find((r) => r.receipt_id === receiptId) ?? data?.[0];

  return (
    <>
      <PageHeader
        title="Execution Receipts"
        subtitle="One receipt per executed action: who asked, on what evidence, who approved, what ran."
      />
      <LoadState loading={loading && !data} error={error} />
      {data?.length === 0 && <p className="muted">No actions have been executed yet.</p>}
      {data && selected && (
        <div className="split">
          <Card title="Receipts">
            <ul className="select-list">
              {data.map((receipt) => (
                <li key={receipt.receipt_id}>
                  <button
                    className={receipt.receipt_id === selected.receipt_id ? "selected" : ""}
                    onClick={() => navigate(`/audit/receipts/${receipt.receipt_id}`)}
                  >
                    <strong>{receipt.invoice_id}</strong>
                    <span>{money(receipt.amount)}</span>
                    <span className="muted">{receipt.receipt_id}</span>
                    <Badge status={receipt.last_verification ?? receipt.anchor_status} />
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <ReceiptDetail receipt={selected} onChanged={reload} />
        </div>
      )}
    </>
  );
}
