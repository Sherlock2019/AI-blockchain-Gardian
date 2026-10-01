import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  DecisionPanel,
  EvidenceList,
  RecommendationPanel,
  requesterLabel,
} from "../components/Governance";
import { Badge, Card, Field, LoadState, Notice, PageHeader, money, when } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";
import type { Action } from "../types";

function ActionCard({ action }: { action: Action }) {
  return (
    <Card
      title={`${action.action_type.replace(/_/g, " ")} · ${action.id}`}
      aside={<Badge status={action.status} />}
    >
      <dl className="fields">
        <Field label="Requested by">{requesterLabel(action)}</Field>
        <Field label="Origin">{action.origin === "AI" ? "AI agent" : "Manual workflow"}</Field>
        <Field label="Amount">{money(action.amount)}</Field>
        <Field label="Requested">{when(action.created_at)}</Field>
      </dl>
      {Object.keys(action.params).length > 0 && (
        <p className="muted">
          Parameters: <code>{JSON.stringify(action.params)}</code>
        </p>
      )}
      {action.last_error && <Notice tone="bad">{action.last_error}</Notice>}
      {action.decision && <DecisionPanel decision={action.decision} />}
      {action.approval && (
        <p>
          <Badge status={action.approval.decision} /> by {action.approval.user_id} (
          {action.approval.role}) at {when(action.approval.timestamp)}
          {action.approval.comment && <> — “{action.approval.comment}”</>}
        </p>
      )}
      <div className="row">
        {action.status === "PENDING_APPROVAL" && <Link to="/technical/approvals">Go to approvals</Link>}
        {action.receipt_id && <Link to={`/audit/receipts/${action.receipt_id}`}>View execution receipt</Link>}
      </div>
    </Card>
  );
}

export function InvoiceDetailPage() {
  const { invoiceId = "" } = useParams();
  const { version, system, refresh } = useApp();
  const { data, loading, error, reload } = useAsync(() => api.invoice(invoiceId), [invoiceId, version]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const submit = (call: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    call()
      .catch((reason: Error) => setActionError(reason.message))
      .finally(() => {
        setBusy(false);
        reload();
        refresh();
      });
  };

  if (!data) return <LoadState loading={loading} error={error} />;
  const { invoice, supplier, purchase_order: po, contract, actions, latest_run: run } = data;
  const aiEnabled = system?.ai_enabled ?? false;

  return (
    <>
      <PageHeader
        title={invoice.id}
        subtitle={invoice.scenario}
        actions={
          <>
            <button
              className="primary"
              disabled={busy || !aiEnabled}
              title={aiEnabled ? "" : "AI mode is OFF"}
              onClick={() => submit(() => api.analyze(invoice.id))}
            >
              Analyse with AI agent
            </button>
            <button disabled={busy} onClick={() => submit(() => api.manualPayment(invoice.id))}>
              Request payment manually
            </button>
          </>
        }
      />
      {actionError && <Notice tone="bad">{actionError}</Notice>}

      <div className="grid-3">
        <Card title="Invoice" aside={<Badge status={invoice.status} />}>
          <dl className="fields single">
            <Field label="Amount">{money(invoice.amount)}</Field>
            <Field label="Description">{invoice.description}</Field>
            <Field label="Notes (third-party text)">
              <span className="untrusted">{invoice.notes || "—"}</span>
            </Field>
          </dl>
        </Card>
        <Card title="Supplier" aside={<Badge status={supplier?.status} />}>
          {supplier ? (
            <dl className="fields single">
              <Field label="Name">
                {supplier.name} ({supplier.id})
              </Field>
              <Field label="Risk rating">
                <Badge status={supplier.risk} />
              </Field>
              <Field label="Payment limit">{money(supplier.payment_limit)}</Field>
            </dl>
          ) : (
            <p className="muted">No supplier record.</p>
          )}
        </Card>
        <Card title="Purchase order" aside={<Badge status={po?.status} />}>
          {po ? (
            <dl className="fields single">
              <Field label="Reference">{po.id}</Field>
              <Field label="Approved amount">{money(po.approved_amount)}</Field>
              <Field label="Contract">{contract ? `${contract.id} — ${contract.title}` : "—"}</Field>
            </dl>
          ) : (
            <p className="muted">No purchase order.</p>
          )}
        </Card>
      </div>

      {run && (
        <div className="grid-2">
          <Card
            title="AI recommendation"
            aside={
              <span className="muted">
                {run.model_provider}/{run.model_name}
              </span>
            }
          >
            <RecommendationPanel run={run} />
            {run.policy_references.length > 0 && (
              <p className="muted">Policy references: {run.policy_references.join("; ")}</p>
            )}
          </Card>
          <Card title="Retrieved evidence" aside={<span className="muted">{run.retrieved_sources.length} sources</span>}>
            <EvidenceList sources={run.retrieved_sources} />
          </Card>
        </div>
      )}

      <h2 className="section-title">Requests and governance decisions</h2>
      {actions.length === 0 && (
        <p className="muted">
          Nothing has been requested for this invoice yet. Run the agent, or request payment manually.
        </p>
      )}
      {actions.map((action) => (
        <ActionCard key={action.id} action={action} />
      ))}
    </>
  );
}
