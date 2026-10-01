import { StoryStrip } from "../components/Story";
import { Card } from "../components/ui";

const ROLES = [
  { name: "AI agent", does: "Investigates and recommends", word: "Intelligence" },
  { name: "RAG", does: "Finds trusted enterprise knowledge", word: "Knowledge" },
  { name: "Policy engine", does: "Determines what is allowed", word: "Control" },
  { name: "Human", does: "Retains authority over high-risk decisions", word: "Authority" },
  { name: "FastAPI", does: "Connects AI with enterprise systems", word: "Integration" },
  { name: "Database", does: "Stores operational application data", word: "Operations" },
  { name: "Smart contract", does: "Records deterministic verification data", word: "Verification" },
  { name: "Blockchain", does: "Provides tamper-evident proof", word: "Proof" },
];

const EQUATIONS = [
  ["AI", "Intelligence"],
  ["RAG", "Knowledge"],
  ["Policy", "Control"],
  ["Human", "Authority"],
  ["API", "Integration"],
  ["Blockchain", "Proof"],
];

const HUMAN_SAFE = [
  ["Sustainable", "AI produces a durable improvement to a human process, not a dependency to babysit."],
  ["Augmentative", "AI increases human capability. It does not quietly replace human judgement."],
  ["Fail-safe", "Critical workflows stay available when AI is unavailable or switched off."],
  ["Empowering", "Humans keep authority over consequential decisions, and can see why something happened."],
];

const AUTHORITY = [
  ["Model", "Summarise evidence and recommend", "Decide, approve or execute anything"],
  ["Agent", "Read records; request an action", "Execute; change its own permissions"],
  ["Policy engine", "Allow, require approval, or deny", "Be loosened by model output"],
  ["Human approver", "Approve or reject within their limit", "Approve their own request, or beyond their limit"],
  ["Workflow service", "Execute an authorised action once", "Execute anything not authorised"],
  ["Smart contract", "Refuse records that break registry rules", "See business data; judge whether a payment was right"],
  ["Blockchain", "Make later edits detectable", "Prove the record was true when it was written"],
];

export function ArchitecturePage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Architecture</h1>
          <p className="muted">AI is powerful, but AI is not the authority. Each part has one job.</p>
        </div>
      </div>

      <div className="role-grid">
        {ROLES.map((role) => (
          <div key={role.name} className="role">
            <span className="eyebrow">{role.name}</span>
            <strong>{role.does}</strong>
          </div>
        ))}
      </div>

      <div className="equations">
        {EQUATIONS.map(([part, meaning]) => (
          <div key={part}>
            <span>{part}</span>
            <span aria-hidden="true">=</span>
            <strong>{meaning}</strong>
          </div>
        ))}
      </div>

      <section className="band">
        <h2 className="band-title">How one invoice moves through it</h2>
        <StoryStrip />
        <p className="muted">
          With AI switched off, a person files the request instead of the agent. Every step after that is
          the same code.
        </p>
      </section>

      <Card title="Human-SAFE AI">
        <p className="muted">The design principle this system is built to, stated as engineering requirements.</p>
        <div className="principles">
          {HUMAN_SAFE.map(([name, text]) => (
            <div key={name} className="principle">
              <h3>
                <span className="principle-letter">{name[0]}</span>
                {name}
              </h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </Card>

      <details className="card">
        <summary>For engineers: who has authority over what, and why a blockchain at all</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Component</th>
                <th>May</th>
                <th>May not</th>
              </tr>
            </thead>
            <tbody>
              {AUTHORITY.map(([component, may, mayNot]) => (
                <tr key={component}>
                  <td>
                    <strong>{component}</strong>
                  </td>
                  <td>{may}</td>
                  <td>{mayNot}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>Why not just use a database?</h3>
        <p>
          For one organisation with one trusted administrator, you probably should. A signed, append-only
          audit log, or a managed store with object lock, is simpler and cheaper, and gives the same
          tamper evidence against everyone except that administrator.
        </p>
        <p>
          A shared ledger starts to pay for itself when several parties need to verify the same record and
          none should have to trust another's database: an enterprise and its supplier, a bank and its
          auditor, an AI provider and its customer, a marketplace and the agents operating on it.
        </p>
        <p className="muted">
          This demo runs one local development chain, so it shows the mechanism, not that trust property.
          A ledger also cannot tell whether a record was true when written, only that it has not changed
          since. Blockchain does not make an AI truthful.
        </p>
      </details>
    </>
  );
}
