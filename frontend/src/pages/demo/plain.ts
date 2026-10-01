// Plain-language wording for the guided demo. Every statement shown to the
// viewer is derived from what the backend actually returned; nothing here
// decides an outcome.

import type { Check, GovernanceDecision, RetrievedSource, User } from "../../types";

/** The demo performs each step as the person that step belongs to. */
export const REQUESTER_ID = "USR-003";
export const SWITCH_OPERATOR_ID = "USR-001";

export interface DemoCase {
  key: string;
  invoiceId: string;
  title: string;
  amount: string;
  condition: string;
  expected: string;
  tone: "good" | "warn" | "bad";
  action: string;
}

export const DEMO_CASES: DemoCase[] = [
  {
    key: "normal",
    invoiceId: "INV-2026-0043",
    title: "Normal invoice",
    amount: "$500",
    condition: "Approved supplier",
    expected: "AI verifies it. Policy releases the payment automatically.",
    tone: "good",
    action: "Analyze with AI",
  },
  {
    key: "high-value",
    invoiceId: "INV-2026-0042",
    title: "High-value invoice",
    amount: "$50,000",
    condition: "Approved supplier",
    expected: "AI investigates and requests human approval.",
    tone: "warn",
    action: "Analyze with AI",
  },
  {
    key: "suspicious",
    invoiceId: "INV-2026-0045",
    title: "Suspicious invoice",
    amount: "$50,000",
    condition: "Blocked supplier",
    expected: "AI identifies the risk and governance blocks the payment.",
    tone: "bad",
    action: "Analyze with AI",
  },
  {
    key: "malicious",
    invoiceId: "INV-2026-0047",
    title: "Malicious invoice",
    amount: "$8,000",
    condition: "Contains a prompt-injection attempt",
    expected: "The AI may be manipulated. Security controls outside the AI still block the action.",
    tone: "bad",
    action: "Run prompt-injection attack",
  },
];

export const WORK_STEPS = [
  "Reading invoice",
  "Checking supplier",
  "Finding purchase order",
  "Retrieving contract",
  "Searching payment policies",
  "Comparing invoice with purchase order",
  "Checking payment rules",
  "Assessing risk",
  "Preparing recommendation",
];

export const RECOMMENDATION_HEADLINE: Record<string, string> = {
  PAYMENT_RECOMMENDED: "Payment appears valid",
  PAYMENT_NOT_RECOMMENDED: "Payment not recommended",
  MANUAL_REVIEW: "Needs human review",
};

export const DECISION_HEADLINE: Record<string, string> = {
  ALLOW: "Approved automatically",
  REQUIRE_APPROVAL: "Human approval required",
  DENY: "Payment blocked",
};

const ROLE_NAME: Record<string, string> = {
  FINANCE_MANAGER: "Finance Manager",
  CFO: "CFO",
  AP_CLERK: "AP Clerk",
};
const ROLE_THRESHOLD: Record<string, string> = { FINANCE_MANAGER: "$1,000", CFO: "$100,000" };

export const roleName = (role: string | null | undefined) =>
  (role && ROLE_NAME[role]) || role?.replace(/_/g, " ") || "";

export interface Finding {
  ok: boolean;
  text: string;
}

const PASSED_WORDING: Record<string, string> = {
  supplier_approved: "Supplier is approved",
  po_exists: "Purchase order found and approved",
  invoice_matches_po: "Amount is within the approved purchase order",
  supplier_limit: "Amount is within the supplier's payment limit",
  duplicate_payment: "No duplicate payment detected",
  evidence_present: "Required documentation found",
  request_matches_record: "Request matches the invoice on record",
};

/** The "Why?" list: what the controls confirmed, and what they refused, in plain words. */
export function findings(decision: GovernanceDecision | null, sources: RetrievedSource[]): Finding[] {
  if (!decision) return [];
  const list: Finding[] = [];
  const checks: Check[] = [...decision.permission_checks, ...decision.policy_checks];
  for (const check of checks) {
    if (check.status === "FAIL") list.push({ ok: false, text: check.detail });
    else if (check.status === "PASS" && PASSED_WORDING[check.name]) {
      list.push({ ok: true, text: PASSED_WORDING[check.name] });
    }
  }
  if (sources.some((s) => s.kind === "contract")) list.push({ ok: true, text: "Contract found" });
  // Problems first: they are what the reader needs to see.
  return list.sort((a, b) => Number(a.ok) - Number(b.ok));
}

/** One sentence on why a person is needed, or why not. */
export function decisionReason(decision: GovernanceDecision): string {
  if (decision.decision === "ALLOW") {
    return "Every control passed and the amount is within the limit for release without a second approver.";
  }
  if (decision.decision === "DENY") {
    return "A control failed. Nobody is asked to approve a payment that policy forbids.";
  }
  const role = decision.required_approval ?? "";
  const escalations = decision.policy_checks.filter((c) => c.status === "ESCALATE");
  const overLimit = escalations.some((c) => c.name === "autonomous_threshold");
  const others = escalations.filter((c) => c.name !== "autonomous_threshold").map((c) => c.detail);
  const sentences = [];
  if (overLimit && ROLE_THRESHOLD[role]) {
    sentences.push(
      `Company policy requires ${roleName(role)} approval for payments above ${ROLE_THRESHOLD[role]}.`,
    );
  }
  return [...sentences, ...others].join(" ") || `Policy requires ${roleName(role)} approval.`;
}

export function approverFor(decision: GovernanceDecision | null, users: User[]): User | null {
  if (!decision?.required_approval) return null;
  return users.find((u) => u.role === decision.required_approval) ?? null;
}

const KNOWLEDGE: Array<{ kind: string; label: string }> = [
  { kind: "policy", label: "Payment policy" },
  { kind: "supplier", label: "Supplier records" },
  { kind: "purchase_order", label: "Purchase order" },
  { kind: "contract", label: "Contract" },
  { kind: "payment_history", label: "Previous payment history" },
];

export function knowledgeSearched(sources: RetrievedSource[]): Array<{ label: string; found: boolean }> {
  return KNOWLEDGE.map(({ kind, label }) => ({ label, found: sources.some((s) => s.kind === kind) }));
}
