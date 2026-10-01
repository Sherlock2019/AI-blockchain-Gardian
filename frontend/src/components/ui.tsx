import type { ReactNode } from "react";

export type Tone = "good" | "warn" | "bad" | "neutral" | "info";

// One place decides what colour a status is: green = verified/allowed,
// amber = a human is needed, red = denied or tampered.
const TONES: Record<string, Tone> = {
  PASS: "good",
  ALLOW: "good",
  EXECUTED: "good",
  VERIFIED: "good",
  ANCHORED: "good",
  APPROVED: "good",
  ACTIVE: "good",
  PAID: "good",
  DONE: "good",
  PAYMENT_RECOMMENDED: "good",
  ESCALATE: "warn",
  REQUIRE_APPROVAL: "warn",
  PENDING_APPROVAL: "warn",
  PENDING: "warn",
  AUTHORIZED: "warn",
  EXECUTING: "warn",
  MEDIUM: "warn",
  MANUAL_REVIEW: "warn",
  NOT_ANCHORED: "warn",
  LEDGER_UNAVAILABLE: "warn",
  UNAVAILABLE: "warn",
  SIMULATED: "warn",
  FAIL: "bad",
  DENY: "bad",
  DENIED: "bad",
  REJECTED: "bad",
  FAILED: "bad",
  BLOCKED: "bad",
  TAMPER_DETECTED: "bad",
  HIGH: "bad",
  CRITICAL: "bad",
  DEACTIVATED: "bad",
  NOT_REGISTERED: "bad",
  PAYMENT_NOT_RECOMMENDED: "bad",
  LOW: "good",
};

export function toneOf(status: string | null | undefined): Tone {
  return (status && TONES[status]) || "neutral";
}

export function Badge({ status, label }: { status: string | null | undefined; label?: string }) {
  if (!status) return <span className="badge badge-neutral">—</span>;
  return (
    <span className={`badge badge-${toneOf(status)}`}>{label ?? status.replace(/_/g, " ")}</span>
  );
}

export function Card({
  title,
  aside,
  children,
}: {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || aside) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h2 className="sub-title">{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>{children ?? "—"}</dd>
    </div>
  );
}

export function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "bad" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function LoadState({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <Notice tone="bad">{error}</Notice>;
  if (loading) return <p className="muted">Loading…</p>;
  return null;
}

/** A hash or address, shortened for display with the full value on hover. */
export function Hash({ value, full = false }: { value: string | null | undefined; full?: boolean }) {
  if (!value) return <span className="muted">—</span>;
  const shown = full || value.length <= 18 ? value : `${value.slice(0, 10)}…${value.slice(-8)}`;
  return (
    <code className="hash" title={value}>
      {shown}
    </code>
  );
}

export function money(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}
