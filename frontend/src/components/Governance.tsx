import type { Action, AgentRun, Check, GovernanceDecision, RetrievedSource, TimelineStep } from "../types";
import { Badge, Field, Notice } from "./ui";

export function ChecksTable({ title, checks }: { title: string; checks: Check[] }) {
  if (checks.length === 0) return null;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{title}</th>
            <th>Result</th>
            <th>Detail</th>
            <th>Policy</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((check) => (
            <tr key={check.name}>
              <td>
                <code>{check.name}</code>
              </td>
              <td>
                <Badge status={check.status} />
              </td>
              <td>{check.detail}</td>
              <td className="muted nowrap">{check.policy_ref ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DecisionPanel({ decision }: { decision: GovernanceDecision }) {
  return (
    <div className="stack">
      <dl className="fields">
        <Field label="Decision">
          <Badge status={decision.decision} />
        </Field>
        <Field label="Risk">
          <Badge status={decision.risk_level} />
        </Field>
        <Field label="Required approval">{decision.required_approval ?? "None"}</Field>
        <Field label="Policy version">{decision.policy_version}</Field>
      </dl>
      <ul className="reasons">
        {decision.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <ChecksTable title="Permission check" checks={decision.permission_checks} />
      <ChecksTable title="Policy check" checks={decision.policy_checks} />
    </div>
  );
}

export function EvidenceList({ sources }: { sources: RetrievedSource[] }) {
  return (
    <ul className="evidence">
      {sources.map((source) => (
        <li key={source.source_id}>
          <div className="row">
            <span className="badge badge-info">{source.kind.replace("_", " ")}</span>
            <strong>{source.title}</strong>
            {source.score !== null && <span className="muted">similarity {source.score}</span>}
          </div>
          <p className="muted">{source.snippet}</p>
        </li>
      ))}
    </ul>
  );
}

export function RecommendationPanel({ run }: { run: Pick<AgentRun, "recommendation" | "confidence" | "reasoning_summary" | "warnings"> }) {
  return (
    <div className="stack">
      <div className="row">
        <Badge status={run.recommendation} />
        <span className="muted">confidence {Math.round(run.confidence * 100)}%</span>
        <span className="muted">· advisory only, not an authorisation</span>
      </div>
      <p>{run.reasoning_summary}</p>
      {run.warnings.map((warning) => (
        <Notice key={warning} tone="warn">
          {warning}
        </Notice>
      ))}
    </div>
  );
}

export function Timeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol className="timeline">
      {steps.map((step, index) => (
        <li key={`${step.stage}-${index}`} className={`timeline-${step.status.toLowerCase()}`}>
          <span className="timeline-stage">{step.stage}</span>
          <div>
            <strong>{step.title}</strong>
            <p className="muted">{step.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function requesterLabel(action: Action): string {
  return action.principal_kind === "AGENT" ? `Agent ${action.principal_id}` : `User ${action.principal_id}`;
}
