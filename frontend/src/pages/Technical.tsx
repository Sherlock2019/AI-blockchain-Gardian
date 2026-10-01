import { Card, LoadState, PageHeader } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";

const STACK = [
  ["Python 3.12 · FastAPI", "Thin HTTP routes over typed services. No business logic in routes.", "backend/app/api, main.py"],
  ["Agent orchestration", "TreasuryAgent with read-only tools; output parsed against a schema, fail-closed.", "backend/app/agents"],
  ["RAG", "Policies chunked by clause, hashed embeddings, in-memory index behind a vector-store interface.", "backend/app/rag"],
  ["Policy engine", "Pure function of request and facts on record: identity, permission, policy, risk, approval.", "backend/app/governance"],
  ["RBAC and four-eyes", "Role rank, approval limits, no self-approval; approvals bound to the action hash.", "governance/approval.py, services/workflow.py"],
  ["Human-in-the-loop", "Governance is re-evaluated at approval and again at execution.", "services/workflow.py"],
  ["Idempotent execution", "One state transition, one payment per invoice enforced by unique constraints.", "services/payment.py"],
  ["Solidity smart contract", "Agent registry and write-once approval and execution hashes. Admin and recorder keys are separate.", "blockchain/contracts/TrustChainRegistry.sol"],
  ["Hash verification", "SHA-256 of canonical JSON, receipts chained, compared with the on-chain hash.", "services/receipts.py"],
  ["Observability", "JSON logs, correlation id per request, hash-chained audit events, metrics derived from them.", "backend/app/observability"],
  ["Testing", "Unit, scenario, API, contract and backend-to-contract tests.", "backend/tests, blockchain/test"],
  ["Docker · CI/CD", "Compose stack and a GitHub Actions pipeline that runs every suite against a live local chain.", "docker-compose.yml, .github/workflows"],
];

const METRIC_LABELS: Record<string, string> = {
  total_agent_requests: "Agent requests",
  actions_allowed: "Actions allowed",
  actions_requiring_approval: "Actions requiring approval",
  actions_denied: "Actions denied",
  human_approvals: "Human approvals",
  human_rejections: "Human rejections",
  prompt_injection_blocks: "Prompt-injection blocks",
  duplicate_payment_blocks: "Duplicate-payment blocks",
  verified_receipts: "Verified receipts",
};

export function TechnicalPage() {
  const { version, system } = useApp();
  const { data, loading, error } = useAsync(api.overview, [version]);

  return (
    <>
      <PageHeader title="What is underneath" subtitle="Each row names the code that implements it." />
      <Card>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Capability</th>
                <th>How it is implemented</th>
                <th>Where</th>
              </tr>
            </thead>
            <tbody>
              {STACK.map(([name, how, where]) => (
                <tr key={name}>
                  <td className="nowrap">
                    <strong>{name}</strong>
                  </td>
                  <td>{how}</td>
                  <td>
                    <code>{where}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <LoadState loading={loading && !data} error={error} />
      {data && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <span className="stat-label">Model</span>
              <span className="stat-text">
                {system?.llm.provider} / {system?.llm.model}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Active agents</span>
              <span className="stat-value">{data.active_agents}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Pending approvals</span>
              <span className={`stat-value ${data.pending_approvals ? "text-warn" : ""}`}>{data.pending_approvals}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Executed actions</span>
              <span className="stat-value text-good">{data.executed_actions}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Blocked actions</span>
              <span className={`stat-value ${data.blocked_actions ? "text-bad" : ""}`}>{data.blocked_actions}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Verified receipts</span>
              <span className="stat-value">
                {data.verified_receipts}
                <span className="stat-of"> / {data.total_receipts}</span>
              </span>
            </div>
          </div>
          <Card title="Operational metrics" aside={<span className="muted">derived from the audit trail</span>}>
            <div className="table-wrap">
              <table>
                <tbody>
                  {Object.entries(METRIC_LABELS).map(([key, label]) => (
                    <tr key={key}>
                      <td>{label}</td>
                      <td className="numeric">{data.metrics[key] ?? 0}</td>
                      <td className="muted">
                        <code>{key}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </>
  );
}
