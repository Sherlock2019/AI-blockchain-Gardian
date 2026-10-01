// Mirrors the JSON produced by backend/app/api/presenters.py.

export type CheckStatus = "PASS" | "FAIL" | "ESCALATE";
export type Decision = "ALLOW" | "REQUIRE_APPROVAL" | "DENY";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ActionStatus =
  | "PROPOSED"
  | "DENIED"
  | "PENDING_APPROVAL"
  | "REJECTED"
  | "AUTHORIZED"
  | "EXECUTING"
  | "EXECUTED"
  | "FAILED";
export type VerificationStatus =
  | "VERIFIED"
  | "TAMPER_DETECTED"
  | "NOT_ANCHORED"
  | "LEDGER_UNAVAILABLE";

export interface User {
  id: string;
  name: string;
  role: string;
  approval_limit: string;
}

export interface LedgerInfo {
  mode: string;
  connected: boolean;
  contract_address: string | null;
  chain_id: number | null;
  block_number: number | null;
  recorder: string | null;
  detail: string;
}

export interface SystemInfo {
  ai_enabled: boolean;
  demo_mode: boolean;
  policy_version: string;
  policy_hash: string;
  llm: { provider: string; model: string };
  ledger: LedgerInfo;
}

export interface Overview {
  ai_enabled: boolean;
  active_agents: number;
  pending_approvals: number;
  executed_actions: number;
  blocked_actions: number;
  verified_receipts: number;
  total_receipts: number;
  metrics: Record<string, number>;
}

export interface Invoice {
  id: string;
  supplier_id: string;
  purchase_order_id: string;
  amount: string;
  description: string;
  notes: string;
  status: string;
  scenario: string;
}

export interface InvoiceListItem extends Invoice {
  supplier_name: string | null;
  latest_action_status: ActionStatus | null;
}

export interface Supplier {
  id: string;
  name: string;
  status: string;
  risk: string;
  payment_limit: string;
  account_token: string;
}

export interface PurchaseOrder {
  id: string;
  supplier_id: string;
  approved_amount: string;
  description: string;
  status: string;
}

export interface Contract {
  id: string;
  title: string;
  terms: string;
}

export interface Check {
  name: string;
  status: CheckStatus;
  detail: string;
  policy_ref: string | null;
}

export interface GovernanceDecision {
  decision_id: string;
  action_id: string;
  agent_id: string;
  requested_action: string;
  risk_level: RiskLevel;
  risk_factors: string[];
  permission_checks: Check[];
  policy_checks: Check[];
  required_approval: string | null;
  decision: Decision;
  reasons: string[];
  policy_version: string;
  policy_hash: string;
  evaluated_at: string;
}

export interface Approval {
  approval_id: string;
  user_id: string;
  role: string;
  decision: "APPROVED" | "REJECTED";
  timestamp: string;
  comment: string;
  digital_signature_mock: string;
}

export interface Action {
  id: string;
  action_hash: string;
  correlation_id: string;
  origin: "AI" | "MANUAL";
  principal_kind: "AGENT" | "HUMAN";
  principal_id: string;
  action_type: string;
  invoice_id: string | null;
  supplier_id: string | null;
  purchase_order_id: string | null;
  amount: string | null;
  params: Record<string, string>;
  evidence_ids: string[];
  recommendation: string | null;
  run_id: string | null;
  status: ActionStatus;
  decision: GovernanceDecision | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  approval: Approval | null;
  receipt_id: string | null;
}

export interface RetrievedSource {
  source_id: string;
  kind: string;
  title: string;
  snippet: string;
  score: number | null;
}

export interface TimelineStep {
  stage: string;
  title: string;
  detail: string;
  status: "DONE" | "PENDING" | "BLOCKED" | "SKIPPED" | "FAILED";
}

export interface AgentRun {
  run_id: string;
  invoice_id: string;
  agent_id: string;
  recommendation: string;
  confidence: number;
  reasoning_summary: string;
  retrieved_sources: RetrievedSource[];
  policy_references: string[];
  warnings: string[];
  model_provider: string;
  model_name: string;
  correlation_id: string;
  requested_by: string;
  created_at: string;
  actions: Action[];
  timeline: TimelineStep[];
}

export interface PendingApproval extends Action {
  invoice: Invoice | null;
  supplier: Supplier | null;
  analysis: Pick<
    AgentRun,
    "recommendation" | "confidence" | "reasoning_summary" | "retrieved_sources" | "warnings"
  > | null;
}

export interface InvoiceDetail {
  invoice: Invoice;
  supplier: Supplier | null;
  purchase_order: PurchaseOrder | null;
  contract: Contract | null;
  actions: Action[];
  latest_run: AgentRun | null;
}

export interface Passport {
  id: string;
  name: string;
  role: string;
  version: string;
  status: string;
  allowed_actions: string[];
  forbidden_actions: string[];
  autonomous_payment_limit: string;
  human_approval_above: string;
  policy: string;
  agent_hash: string;
  blockchain: {
    registration: "VERIFIED" | "DEACTIVATED" | "NOT_REGISTERED" | "UNAVAILABLE";
    onchain_permissions: Record<string, boolean>;
    contract_address: string | null;
    ledger_mode: string;
    chain_id: number | null;
  };
}

export interface Receipt {
  receipt_id: string;
  action_id: string;
  action_hash: string;
  agent_id: string | null;
  agent_version: string | null;
  requested_by: string;
  origin: string;
  model_provider: string;
  model_name: string;
  policy_version: string;
  policy_hash: string;
  invoice_id: string;
  supplier_id: string;
  purchase_order_id: string;
  retrieved_source_ids: string[];
  requested_action: string;
  permission_used: string;
  amount: string;
  risk_level: RiskLevel;
  governance_decision: Decision;
  governance_decision_id: string;
  human_approval_id: string | null;
  human_approval_role: string | null;
  approval_hash: string | null;
  tool_executed: string;
  execution_result: { transaction_id: string; status: string };
  timestamp: string;
  previous_receipt_hash: string;
  receipt_hash: string;
  blockchain_tx_hash: string | null;
  block_number: number | null;
  anchor_status: "ANCHORED" | "PENDING" | "REJECTED";
  anchor_error: string | null;
  last_verification: VerificationStatus | null;
  tampered_in_demo: boolean;
}

export interface Verification {
  receipt_id: string;
  status: VerificationStatus;
  recomputed_hash: string;
  stored_hash: string;
  onchain_hash: string | null;
  local_match: boolean;
  chain_match: boolean | null;
  chain_link_ok: boolean;
  block_number: number | null;
  blockchain_tx_hash: string | null;
  contract_address: string | null;
  ledger_mode: string;
  checked_at: string;
  details: string[];
}

export interface LedgerRecord {
  receipt_id: string;
  invoice_id: string;
  action_hash: string;
  receipt_hash: string;
  onchain_hash: string | null;
  block_number: number | null;
  blockchain_tx_hash: string | null;
  anchor_status: string;
  ledger_reachable: boolean;
  matches: boolean | null;
}

export interface AuditEvent {
  seq: number;
  timestamp: string;
  correlation_id: string;
  event_type: string;
  actor: string;
  subject: string;
  data: Record<string, unknown>;
  event_hash: string;
}

export interface AuditChainStatus {
  intact: boolean;
  events: number;
  broken_at_seq: number | null;
}
