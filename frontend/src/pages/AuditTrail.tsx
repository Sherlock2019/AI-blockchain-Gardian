import { useSearchParams } from "react-router-dom";
import { Card, Hash, LoadState, Notice, PageHeader, when } from "../components/ui";
import type { Tone } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";

function eventTone(type: string): Tone {
  if (/DENY|DENIED|BLOCKED|REFUSED|REJECTED|FAILED|TAMPERED/.test(type)) return "bad";
  if (/REQUIRE_APPROVAL|DEFERRED|RECHECK|AI_MODE/.test(type)) return "warn";
  if (/ALLOW|GRANTED|EXECUTED|ANCHORED|VERIFIED|CREATED/.test(type)) return "good";
  return "neutral";
}

export function AuditTrailPage() {
  const { version, system, refresh } = useApp();
  const [params, setParams] = useSearchParams();
  const correlationId = params.get("correlation_id") ?? "";
  const events = useAsync(() => api.audit(correlationId || undefined), [correlationId, version]);
  const chain = useAsync(api.auditChain, [version]);

  const reset = () => {
    if (window.confirm("Reset all demo data to its initial state?")) {
      api.resetDemo().finally(refresh);
    }
  };

  return (
    <>
      <PageHeader
        title="Audit Trail"
        subtitle="Append-only, hash-chained events. Every request carries one correlation id from agent run to ledger."
        actions={system?.demo_mode ? <button onClick={reset}>Reset demo data</button> : undefined}
      />
      {chain.data && (
        <Notice tone={chain.data.intact ? "good" : "bad"}>
          {chain.data.intact
            ? `Hash chain intact across ${chain.data.events} events.`
            : `Hash chain broken at event ${chain.data.broken_at_seq}.`}{" "}
          <span className="muted">
            The chain lives in the application database, so it shows edits to individual rows, not a
            rewrite of the whole table. Receipts are anchored on the ledger for that reason.
          </span>
        </Notice>
      )}
      {correlationId && (
        <p>
          Showing correlation <code>{correlationId}</code>.{" "}
          <button className="link" onClick={() => setParams({})}>
            Show all events
          </button>
        </p>
      )}
      <LoadState loading={events.loading && !events.data} error={events.error} />
      {events.data && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="numeric">#</th>
                  <th>Time</th>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Subject</th>
                  <th>Detail</th>
                  <th>Correlation</th>
                  <th>Hash</th>
                </tr>
              </thead>
              <tbody>
                {events.data.map((event) => (
                  <tr key={event.seq}>
                    <td className="numeric muted">{event.seq}</td>
                    <td className="nowrap muted">{when(event.timestamp)}</td>
                    <td>
                      <span className={`badge badge-${eventTone(event.event_type)}`}>
                        {event.event_type.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="nowrap">{event.actor}</td>
                    <td className="nowrap">{event.subject}</td>
                    <td className="audit-data">
                      <code>{JSON.stringify(event.data)}</code>
                    </td>
                    <td>
                      <button
                        className="link"
                        onClick={() => setParams({ correlation_id: event.correlation_id })}
                      >
                        <code>{event.correlation_id.slice(0, 8)}</code>
                      </button>
                    </td>
                    <td>
                      <Hash value={event.event_hash} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
