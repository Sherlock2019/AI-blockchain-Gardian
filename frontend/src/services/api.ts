import type {
  Action,
  AgentRun,
  AuditChainStatus,
  AuditEvent,
  InvoiceDetail,
  InvoiceListItem,
  LedgerRecord,
  Overview,
  Passport,
  PendingApproval,
  Receipt,
  SystemInfo,
  User,
  Verification,
} from "../types";

const USER_KEY = "trustchain.user";
export const DEFAULT_USER = "USR-003";

export function getUserId(): string {
  try {
    return localStorage.getItem(USER_KEY) ?? DEFAULT_USER;
  } catch {
    return DEFAULT_USER;
  }
}

export function setUserId(id: string): void {
  try {
    localStorage.setItem(USER_KEY, id);
  } catch {
    // Storage unavailable: the choice lasts for this page only.
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
    readonly correlationId?: string,
  ) {
    super(message);
  }
}

/**
 * `asUser` overrides the identity picked in Technical Details. The guided demo
 * uses it to perform each step as the persona that step belongs to.
 */
async function request<T>(path: string, init: RequestInit = {}, asUser?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": asUser ?? getUserId(),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError("The backend is not reachable.", "NETWORK", 0);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      body?.message ??
      (Array.isArray(body?.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ") : null) ??
      `Request failed (${response.status}).`;
    throw new ApiError(message, body?.error ?? "ERROR", response.status, body?.correlation_id);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown, asUser?: string) =>
  request<T>(
    path,
    { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) },
    asUser,
  );

export const api = {
  users: () => request<User[]>("/users"),
  system: () => request<SystemInfo>("/system"),
  setAiMode: (enabled: boolean, asUser?: string) =>
    post<{ ai_enabled: boolean }>("/system/ai-mode", { enabled }, asUser),
  overview: () => request<Overview>("/overview"),

  invoices: () => request<InvoiceListItem[]>("/invoices"),
  invoice: (id: string) => request<InvoiceDetail>(`/invoices/${id}`),
  analyze: (invoiceId: string, asUser?: string) =>
    post<AgentRun>("/agent/analyze", { invoice_id: invoiceId }, asUser),
  manualPayment: (invoiceId: string, asUser?: string) =>
    post<Action>("/payments/manual", { invoice_id: invoiceId }, asUser),
  runs: () => request<AgentRun[]>("/agent/runs"),
  passport: (agentId: string) => request<Passport>(`/agents/${agentId}/passport`),

  actions: () => request<Action[]>("/actions"),
  pendingApprovals: () => request<PendingApproval[]>("/approvals/pending"),
  approve: (id: string, comment: string, asUser?: string) =>
    post<Action>(`/actions/${id}/approve`, { comment }, asUser),
  reject: (id: string, comment: string, asUser?: string) =>
    post<Action>(`/actions/${id}/reject`, { comment }, asUser),
  retryExecution: (id: string) => post<Action>(`/actions/${id}/execute`),

  receipts: () => request<Receipt[]>("/receipts"),
  receipt: (id: string) => request<Receipt>(`/receipts/${id}`),
  verify: (id: string) => post<Verification>(`/receipts/${id}/verify`),
  anchor: (id: string) => post<Receipt>(`/receipts/${id}/anchor`),
  tamper: (id: string, recomputeHash: boolean) =>
    post<Receipt>(`/demo/receipts/${id}/tamper`, { recompute_hash: recomputeHash }),
  restore: (id: string) => post<Receipt>(`/demo/receipts/${id}/restore`),
  resetDemo: () => post<{ status: string }>("/demo/reset"),

  ledgerRecords: () => request<LedgerRecord[]>("/ledger/records"),
  audit: (correlationId?: string) =>
    request<AuditEvent[]>(
      `/audit?limit=300${correlationId ? `&correlation_id=${encodeURIComponent(correlationId)}` : ""}`,
    ),
  auditChain: () => request<AuditChainStatus>("/audit/verify"),
};
