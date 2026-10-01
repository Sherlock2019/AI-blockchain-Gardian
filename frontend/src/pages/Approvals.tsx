import { useState } from "react";
import { Link } from "react-router-dom";
import {
  DecisionPanel,
  EvidenceList,
  RecommendationPanel,
  requesterLabel,
} from "../components/Governance";
import { Badge, Card, Field, LoadState, Notice, PageHeader, money } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";
import type { Action, PendingApproval } from "../types";

function ApprovalCard({
  item,
  onDecided,
}: {
  item: PendingApproval;
  onDecided: (action: Action) => void;
}) {
  const { user } = useApp();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = (approve: boolean) => {
    setBusy(true);
    setError(null);
    (approve ? api.approve(item.id, comment) : api.reject(item.id, comment))
      .then(onDecided)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setBusy(false));
  };

  return (
    <Card
      title={`${item.action_type.replace(/_/g, " ")} · ${money(item.amount)}`}
      aside={<Badge status={item.decision?.risk_level} label={`${item.decision?.risk_level} RISK`} />}
    >
      <dl className="fields">
        <Field label="Invoice">
          <Link to={`/technical/invoices/${item.invoice_id}`}>{item.invoice_id}</Link>
        </Field>
        <Field label="Supplier">{item.supplier?.name ?? item.supplier_id}</Field>
        <Field label="Requested by">{requesterLabel(item)}</Field>
        <Field label="Approval required from">{item.decision?.required_approval}</Field>
      </dl>

      {item.analysis ? (
        <>
          <h3>AI recommendation</h3>
          <RecommendationPanel run={item.analysis} />
          <details>
            <summary>Evidence ({item.analysis.retrieved_sources.length} sources)</summary>
            <EvidenceList sources={item.analysis.retrieved_sources} />
          </details>
        </>
      ) : (
        <p className="muted">Submitted through the manual workflow. No AI recommendation.</p>
      )}

      <details open>
        <summary>Policy checks</summary>
        {item.decision && <DecisionPanel decision={item.decision} />}
      </details>

      {error && <Notice tone="bad">{error}</Notice>}
      <div className="decision-bar">
        <input
          type="text"
          value={comment}
          maxLength={500}
          placeholder="Comment (recorded with your decision)"
          aria-label="Decision comment"
          onChange={(event) => setComment(event.target.value)}
        />
        <button className="approve" disabled={busy} onClick={() => decide(true)}>
          Approve
        </button>
        <button className="reject" disabled={busy} onClick={() => decide(false)}>
          Reject
        </button>
      </div>
      <p className="muted">
        Deciding as {user?.name} ({user?.role.replace("_", " ")}, limit {money(user?.approval_limit)}).
        The approval engine checks your role, your limit and that you are not the requester.
      </p>
    </Card>
  );
}

export function ApprovalsPage() {
  const { version, refresh } = useApp();
  const { data, loading, error } = useAsync(api.pendingApprovals, [version]);
  const [last, setLast] = useState<Action | null>(null);

  const onDecided = (action: Action) => {
    setLast(action);
    refresh();
  };

  return (
    <>
      <PageHeader
        title="Approvals"
        subtitle="Requests that policy will not release without a person. Your signature is bound to the exact request shown."
      />
      {last && (
        // Approval is not the last word: governance is re-evaluated before anything runs.
        <Notice tone={last.status === "EXECUTED" ? "good" : last.status === "REJECTED" ? "neutral" : "bad"}>
          {last.invoice_id}: {last.status.replace(/_/g, " ")}.{" "}
          {last.last_error ?? (last.status === "DENIED" ? last.decision?.reasons.join(" ") : "")}{" "}
          {last.receipt_id ? (
            <Link to={`/audit/receipts/${last.receipt_id}`}>View execution receipt</Link>
          ) : (
            <Link to={`/technical/invoices/${last.invoice_id}`}>Open invoice</Link>
          )}
        </Notice>
      )}
      <LoadState loading={loading && !data} error={error} />
      {data?.length === 0 && <p className="muted">Nothing is waiting for approval.</p>}
      {data?.map((item) => <ApprovalCard key={item.id} item={item} onDecided={onDecided} />)}
    </>
  );
}
