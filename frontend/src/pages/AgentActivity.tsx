import { Link } from "react-router-dom";
import { Timeline } from "../components/Governance";
import { Badge, Card, LoadState, PageHeader, when } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";

export function AgentActivityPage() {
  const { version } = useApp();
  const { data, loading, error } = useAsync(api.runs, [version]);

  return (
    <>
      <PageHeader
        title="AI Agent"
        subtitle="Each run from observation to verification. The agent's part ends at Recommend; everything after it is decided elsewhere."
      />
      <LoadState loading={loading && !data} error={error} />
      {data?.length === 0 && (
        <p className="muted">
          No agent runs yet. Open an <Link to="/technical/invoices">invoice</Link> and choose “Analyse with AI agent”.
        </p>
      )}
      {data?.map((run) => (
        <Card
          key={run.run_id}
          title={`${run.invoice_id} · ${run.run_id}`}
          aside={<Badge status={run.recommendation} />}
        >
          <p className="muted">
            {when(run.created_at)} · requested by {run.requested_by} · model {run.model_provider}/
            {run.model_name} · correlation{" "}
            <Link to={`/audit/trail?correlation_id=${run.correlation_id}`}>
              <code>{run.correlation_id.slice(0, 12)}</code>
            </Link>
          </p>
          <Timeline steps={run.timeline} />
          <Link to={`/technical/invoices/${run.invoice_id}`}>Open invoice</Link>
        </Card>
      ))}
    </>
  );
}
