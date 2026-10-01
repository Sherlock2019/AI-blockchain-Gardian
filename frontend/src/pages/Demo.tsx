import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BeforeAfter, BusinessValue, PITCH, StoryStrip } from "../components/Story";
import { Field, LoadState, Notice, money } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";
import type { Action, InvoiceDetail } from "../types";
import { AiResult, AttackResult, GovernanceResult, Outcome, ReceiptProof, Step, WorkProgress } from "./demo/panels";
import { DEMO_CASES, REQUESTER_ID, SWITCH_OPERATOR_ID, WORK_STEPS, approverFor } from "./demo/plain";
import type { DemoCase } from "./demo/plain";

const STEP_MS = 330;
const STILL_AVAILABLE = [
  "Invoice",
  "Supplier",
  "Purchase order",
  "Policy",
  "Governance",
  "Human approval",
  "Payment workflow",
];

/** The request this page tells the story of: the executed one if there is one, else the latest. */
function primaryPayment(detail: InvoiceDetail): Action | null {
  const payments = detail.actions.filter((a) => a.action_type === "PAY_SUPPLIER");
  return payments.find((a) => a.status === "EXECUTED") ?? payments[0] ?? null;
}

function AiModeToggle() {
  const { system, refresh } = useApp();
  const [error, setError] = useState<string | null>(null);
  if (!system) return null;
  const set = (enabled: boolean) =>
    api
      .setAiMode(enabled, SWITCH_OPERATOR_ID)
      .then(() => setError(null))
      .catch((reason: Error) => setError(reason.message))
      .finally(refresh);
  return (
    <div className="mode">
      <span className="mode-label">AI mode</span>
      <div className="mode-toggle" role="group" aria-label="AI mode">
        <button className={system.ai_enabled ? "mode-on" : ""} aria-pressed={system.ai_enabled} onClick={() => set(true)}>
          On
        </button>
        <button className={!system.ai_enabled ? "mode-off" : ""} aria-pressed={!system.ai_enabled} onClick={() => set(false)}>
          Off
        </button>
      </div>
      {error && <span className="error-text">{error}</span>}
    </div>
  );
}

function CaseCards({ selected, onSelect }: { selected: DemoCase; onSelect: (c: DemoCase) => void }) {
  return (
    <div className="cases">
      {DEMO_CASES.map((item) => (
        <button
          key={item.key}
          className={`case case-${item.tone} ${item.key === selected.key ? "case-selected" : ""}`}
          aria-pressed={item.key === selected.key}
          onClick={() => onSelect(item)}
        >
          <span className="case-title">{item.title}</span>
          <span className="case-amount">{item.amount}</span>
          <span className="case-condition">{item.condition}</span>
          <span className="case-expected">
            <em>Expected:</em> {item.expected}
          </span>
        </button>
      ))}
    </div>
  );
}

export function DemoPage() {
  const { system, users, version, refresh } = useApp();
  // The selected case lives in the URL so a specific story can be linked to.
  const [params, setParams] = useSearchParams();
  const selected = DEMO_CASES.find((c) => c.key === params.get("case")) ?? DEMO_CASES[1];
  const setSelected = (item: DemoCase) => setParams({ case: item.key }, { replace: true });
  const detail = useAsync(() => api.invoice(selected.invoiceId), [selected.invoiceId, version]);
  const [done, setDone] = useState<number | null>(null); // null: no analysis is being played
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const aiEnabled = system?.ai_enabled ?? true;

  useEffect(() => {
    setDone(null);
    setError(null);
  }, [selected.key]);

  const finish = (call: Promise<unknown>) =>
    call
      .then(() => setError(null))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => {
        setBusy(false);
        refresh();
      });

  const analyze = () => {
    setBusy(true);
    setError(null);
    setDone(0);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const request = api.analyze(selected.invoiceId, REQUESTER_ID);
    // The agent answers in milliseconds. The steps are paced so its work can be read.
    const played = new Promise<void>((resolve) => {
      if (reduced) return resolve();
      let step = 0;
      const timer = window.setInterval(() => {
        step += 1;
        setDone(step);
        if (step >= WORK_STEPS.length) {
          window.clearInterval(timer);
          resolve();
        }
      }, STEP_MS);
    });
    finish(
      Promise.all([request, played]).finally(() => {
        setDone(null);
        resultRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }),
    );
  };

  const processManually = () => {
    setBusy(true);
    finish(api.manualPayment(selected.invoiceId, REQUESTER_ID));
  };

  const reset = () => {
    setBusy(true);
    finish(api.resetDemo().then(() => api.setAiMode(true, SWITCH_OPERATOR_ID)));
  };

  const data = detail.data;
  const action = data ? primaryPayment(data) : null;
  // Show the AI's findings only when they belong to the request being shown.
  const run = data?.latest_run && action?.run_id === data.latest_run.run_id ? data.latest_run : null;
  const attack = run?.actions.find((a) => a.action_type !== "PAY_SUPPLIER" && a.status === "DENIED") ?? null;
  const approver = approverFor(action?.decision ?? null, users);
  // A new request can start unless the invoice is paid or a request is still open.
  const canStart =
    data?.invoice.status !== "PAID" &&
    (!action || ["DENIED", "REJECTED", "FAILED"].includes(action.status));
  const playing = done !== null;

  const decide = (approve: boolean) => {
    if (!action || !approver) return;
    setBusy(true);
    finish((approve ? api.approve : api.reject)(action.id, "Decided in the guided demo", approver.id));
  };

  return (
    <div className="demo">
      <header className="demo-head">
        <div>
          <h1>Treasury AI Assistant</h1>
          <p className="pitch">{PITCH}</p>
        </div>
        <AiModeToggle />
      </header>

      <section className="problem">
        <span className="eyebrow">Today's problem</span>
        <p>
          Finance teams spend valuable time manually checking invoices against suppliers, purchase orders,
          contracts and company policies.
        </p>
      </section>
      <BeforeAfter />

      <div className="row spread">
        <h2 className="band-title">Select an invoice</h2>
        {system?.demo_mode && (
          <button disabled={busy} onClick={reset}>
            Reset demo
          </button>
        )}
      </div>
      <CaseCards selected={selected} onSelect={setSelected} />

      {error && <Notice tone="bad">{error}</Notice>}
      <LoadState loading={detail.loading && !data} error={detail.error} />

      {data && (
        <>
          <Step label={data.invoice.id} title={`${money(data.invoice.amount)} from ${data.supplier?.name ?? data.invoice.supplier_id}`}>
            <dl className="fields">
              <Field label="For">{data.invoice.description}</Field>
              <Field label="Purchase order">
                {data.purchase_order ? `${data.purchase_order.id} · ${money(data.purchase_order.approved_amount)}` : "Not found"}
              </Field>
              <Field label="Supplier status">{data.supplier?.status ?? "Not found"}</Field>
              <Field label="Invoice status">{data.invoice.status}</Field>
            </dl>

            {!aiEnabled && (
              <div className="ai-off">
                <div className="ai-off-agent">
                  <strong>AI assistance disabled</strong>
                  <span>The Treasury AI Agent cannot analyse or request anything.</span>
                </div>
                <div>
                  <strong>Still available</strong>
                  <ul className="tick-list inline">
                    {STILL_AVAILABLE.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {!canStart && !playing ? (
              <p className="muted">
                {data.invoice.status === "PAID"
                  ? "This invoice has been paid. The result is below. Use “Reset demo” to run it again."
                  : "A request for this invoice is waiting for a decision below."}
              </p>
            ) : aiEnabled ? (
              <button className="big primary" disabled={busy} onClick={analyze}>
                {action ? "Analyze again" : selected.action}
              </button>
            ) : (
              <button className="big primary" disabled={busy} onClick={processManually}>
                Process this invoice manually
              </button>
            )}
          </Step>

          {playing && <WorkProgress done={done} />}

          <div ref={resultRef}>
            {!playing && action && (
              <>
                {run && (
                  <AiResult
                    run={run}
                    decision={action.decision}
                    invoice={data.invoice}
                    supplier={data.supplier}
                    manipulated={attack !== null}
                  />
                )}
                {!run && (
                  <Step label="Manual workflow" title="Processed without AI">
                    <p>
                      A person filed this payment request. No model was involved. Everything from here on is
                      the same policy engine, the same approval rules and the same payment workflow.
                    </p>
                  </Step>
                )}
                {attack && <AttackResult invoice={data.invoice} attack={attack} />}
                <GovernanceResult action={action} approver={approver} busy={busy} onDecide={decide} />
                {action.status === "EXECUTED" && action.receipt_id && (
                  <Executed action={action} receiptId={action.receipt_id} />
                )}
              </>
            )}
          </div>
        </>
      )}

      <section className="band">
        <h2 className="band-title">The complete story</h2>
        <StoryStrip />
      </section>
      <BusinessValue />
    </div>
  );
}

function Executed({ action, receiptId }: { action: Action; receiptId: string }) {
  const { users, system } = useApp();
  const receipt = useAsync(() => api.receipt(receiptId), [receiptId]);
  if (!receipt.data) return <LoadState loading={receipt.loading} error={receipt.error} />;
  return (
    <>
      <Outcome action={action} receipt={receipt.data} users={users} />
      {action.origin === "MANUAL" && (
        <div className="principle-banner principle-good">
          <strong>Business workflow still operational.</strong>
          <span>AI augments the workflow. AI does not own the workflow.</span>
        </div>
      )}
      <ReceiptProof receipt={receipt.data} demoMode={system?.demo_mode ?? false} onChanged={receipt.reload} />
    </>
  );
}
