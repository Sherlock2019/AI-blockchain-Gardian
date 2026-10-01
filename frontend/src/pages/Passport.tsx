import { Badge, Card, Field, Hash, LoadState, Notice, PageHeader, money } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";

const AGENT_ID = "AGENT-TREASURY-001";
const readable = (action: string) => action.replace(/_/g, " ").toLowerCase();

export function PassportPage() {
  const { version } = useApp();
  const { data: passport, loading, error } = useAsync(() => api.passport(AGENT_ID), [version]);

  if (!passport) return <LoadState loading={loading} error={error} />;
  const chain = passport.blockchain;

  return (
    <>
      <PageHeader
        title="Agent Passport"
        subtitle="Who the agent is, what it may do, and where that is independently recorded."
      />
      <div className="grid-2">
        <Card title={passport.name} aside={<Badge status={passport.status} />}>
          <dl className="fields">
            <Field label="Agent ID">{passport.id}</Field>
            <Field label="Role">{passport.role.replace(/_/g, " ")}</Field>
            <Field label="Version">{passport.version}</Field>
            <Field label="Policy">{passport.policy}</Field>
            <Field label="Autonomous financial limit">{money(passport.autonomous_payment_limit)}</Field>
            <Field label="Human approval">Required above {money(passport.human_approval_above)}</Field>
          </dl>
        </Card>

        <Card title="Blockchain registration" aside={<Badge status={chain.registration} />}>
          <dl className="fields">
            <Field label="Ledger">{chain.ledger_mode.replace("_", " ")}</Field>
            <Field label="Chain ID">{chain.chain_id ?? "—"}</Field>
            <Field label="Contract">
              <Hash value={chain.contract_address} />
            </Field>
            <Field label="Agent identifier hash">
              <Hash value={passport.agent_hash} />
            </Field>
          </dl>
          {chain.ledger_mode === "SIMULATED" && (
            <Notice tone="warn">
              The ledger is simulated in the backend process. Start the Hardhat node for a real contract.
            </Notice>
          )}
          <p className="muted">
            The registry is written by an admin key the application does not hold. The backend can read
            this record but cannot change it.
          </p>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Allowed">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Application</th>
                <th>On-chain</th>
              </tr>
            </thead>
            <tbody>
              {passport.allowed_actions.map((action) => (
                <tr key={action}>
                  <td className="capitalize">{readable(action)}</td>
                  <td>
                    <Badge status="PASS" label="GRANTED" />
                  </td>
                  <td>
                    {action in chain.onchain_permissions ? (
                      <Badge
                        status={chain.onchain_permissions[action] ? "PASS" : "FAIL"}
                        label={chain.onchain_permissions[action] ? "GRANTED" : "NOT GRANTED"}
                      />
                    ) : (
                      <Badge status={null} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Restricted">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Application</th>
                <th>On-chain</th>
              </tr>
            </thead>
            <tbody>
              {passport.forbidden_actions.map((action) => (
                <tr key={action}>
                  <td className="capitalize">{readable(action)}</td>
                  <td>
                    <Badge status="FAIL" label="FORBIDDEN" />
                  </td>
                  <td>
                    {action in chain.onchain_permissions ? (
                      <Badge
                        status={chain.onchain_permissions[action] ? "ESCALATE" : "FAIL"}
                        label={chain.onchain_permissions[action] ? "GRANTED" : "NOT GRANTED"}
                      />
                    ) : (
                      <Badge status={null} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  );
}
