// Static explanatory blocks shared by the landing page, the demo and the architecture page.

export const PITCH = "AI investigates. Policy controls. Humans decide. Blockchain proves what happened.";

const STORY = [
  { stage: "Without AI", text: "A person searches every system by hand." },
  { stage: "With AI", text: "AI investigates and prepares a recommendation." },
  { stage: "Governance", text: "Deterministic rules control authority." },
  { stage: "Human", text: "A person approves the consequential action." },
  { stage: "Execution", text: "The business action occurs." },
  { stage: "Web3", text: "A cryptographic proof records what happened." },
  { stage: "Audit", text: "Anyone authorised can verify the record." },
];

export function StoryStrip() {
  return (
    <ol className="story">
      {STORY.map((step) => (
        <li key={step.stage}>
          <strong>{step.stage}</strong>
          <span>{step.text}</span>
        </li>
      ))}
    </ol>
  );
}

const MANUAL_CHECKS = ["Invoice", "Supplier", "Purchase order", "Contract", "Payment policy", "Approval rules"];
const AGENT_WORK = [
  "gathers evidence",
  "checks records",
  "retrieves policy",
  "identifies anomalies",
  "prepares a recommendation",
  "routes the approval",
];

export function BeforeAfter() {
  return (
    <div className="before-after">
      <div className="before">
        <span className="eyebrow">Before</span>
        <h3>A Finance Manager checks by hand</h3>
        <ul className="plain-list">
          {MANUAL_CHECKS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="muted">Several separate lookups for every invoice, repeated hundreds of times.</p>
      </div>
      <div className="after">
        <span className="eyebrow">With TrustChain AI</span>
        <h3>The AI agent</h3>
        <ul className="tick-list">
          {AGENT_WORK.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p>
          <strong>The human</strong> reviews the evidence and makes the consequential decisions.
        </p>
      </div>
    </div>
  );
}

const VALUE = [
  { name: "Efficiency", text: "AI performs the repetitive information gathering and policy retrieval." },
  { name: "Decision quality", text: "Humans receive structured evidence before deciding." },
  { name: "Safety", text: "The AI cannot grant itself additional authority." },
  { name: "Accountability", text: "High-risk actions retain human approval." },
  { name: "Auditability", text: "Consequential actions generate verifiable receipts." },
  { name: "Resilience", text: "The business workflow continues when AI is disabled." },
];

export function BusinessValue() {
  return (
    <section className="band">
      <h2 className="band-title">What does TrustChain AI improve?</h2>
      <div className="value-grid">
        {VALUE.map((item) => (
          <div key={item.name} className="value">
            <h3>{item.name}</h3>
            <p>{item.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
