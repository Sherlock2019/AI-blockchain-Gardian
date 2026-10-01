import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, Field, Hash, LoadState, Notice, PageHeader } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";
import type { VerificationStatus } from "../types";

export function BlockchainPage() {
  const { version, system } = useApp();
  const { data, loading, error, reload } = useAsync(api.ledgerRecords, [version]);
  const [results, setResults] = useState<Record<string, VerificationStatus>>({});
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const ledger = system?.ledger;

  const verify = (receiptId: string) => {
    api
      .verify(receiptId)
      .then((result) => {
        setResults((current) => ({ ...current, [receiptId]: result.status }));
        setVerifyError(null);
      })
      .catch((reason: Error) => setVerifyError(reason.message))
      .finally(reload);
  };

  return (
    <>
      <PageHeader
        title="Blockchain Verification"
        subtitle="The receipt hash recomputed from the database, next to the hash the contract holds."
      />
      {ledger && (
        <Card
          title="TrustChainRegistry"
          aside={<Badge status={ledger.connected ? "VERIFIED" : "UNAVAILABLE"} label={ledger.connected ? "CONNECTED" : "UNREACHABLE"} />}
        >
          <dl className="fields">
            <Field label="Ledger">{ledger.mode.replace("_", " ")}</Field>
            <Field label="Contract">
              <Hash value={ledger.contract_address} full />
            </Field>
            <Field label="Chain ID">{ledger.chain_id ?? "—"}</Field>
            <Field label="Latest block">{ledger.block_number ?? "—"}</Field>
            <Field label="Recorder account">
              <Hash value={ledger.recorder} />
            </Field>
          </dl>
          <p className="muted">{ledger.detail}</p>
          <p className="muted">
            Only hashes are written: agent id, permission, policy, approval and receipt. No invoice
            content, prompt or personal data leaves the application database.
          </p>
        </Card>
      )}
      {verifyError && <Notice tone="bad">{verifyError}</Notice>}
      <LoadState loading={loading && !data} error={error} />
      {data && (
        <Card title="Recorded executions">
          {data.length === 0 ? (
            <p className="muted">No executions have been recorded yet.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Receipt</th>
                    <th className="numeric">Block</th>
                    <th>Transaction hash</th>
                    <th>Receipt hash (recomputed)</th>
                    <th>Hash on ledger</th>
                    <th>Verification</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.map((record) => {
                    const status =
                      results[record.receipt_id] ??
                      (record.matches === null
                        ? record.ledger_reachable
                          ? "NOT_ANCHORED"
                          : "LEDGER_UNAVAILABLE"
                        : record.matches
                          ? "VERIFIED"
                          : "TAMPER_DETECTED");
                    return (
                      <tr key={record.receipt_id}>
                        <td className="nowrap">
                          <Link to={`/audit/receipts/${record.receipt_id}`}>{record.invoice_id}</Link>
                          <div className="muted">{record.receipt_id}</div>
                        </td>
                        <td className="numeric">{record.block_number ?? "—"}</td>
                        <td>
                          <Hash value={record.blockchain_tx_hash} />
                        </td>
                        <td>
                          <Hash value={record.receipt_hash} />
                        </td>
                        <td>
                          <Hash value={record.onchain_hash} />
                        </td>
                        <td>
                          <Badge status={status} />
                        </td>
                        <td>
                          <button onClick={() => verify(record.receipt_id)}>Verify</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
