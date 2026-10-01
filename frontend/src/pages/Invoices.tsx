import { useNavigate } from "react-router-dom";
import { Badge, Card, LoadState, PageHeader, money } from "../components/ui";
import { api } from "../services/api";
import { useApp } from "../services/AppContext";
import { useAsync } from "../services/useAsync";

export function InvoicesPage() {
  const { version } = useApp();
  const { data, loading, error } = useAsync(api.invoices, [version]);
  const navigate = useNavigate();

  return (
    <>
      <PageHeader title="Invoices" subtitle="Synthetic supplier invoices. Each one exercises a different control." />
      <LoadState loading={loading && !data} error={error} />
      {data && (
        <Card>
          <div className="table-wrap">
            <table className="clickable">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Supplier</th>
                  <th className="numeric">Amount</th>
                  <th>Status</th>
                  <th>Latest request</th>
                  <th>What it demonstrates</th>
                </tr>
              </thead>
              <tbody>
                {data.map((invoice) => (
                  <tr
                    key={invoice.id}
                    tabIndex={0}
                    onClick={() => navigate(`/technical/invoices/${invoice.id}`)}
                    onKeyDown={(event) => event.key === "Enter" && navigate(`/technical/invoices/${invoice.id}`)}
                  >
                    <td className="nowrap">
                      <strong>{invoice.id}</strong>
                    </td>
                    <td>{invoice.supplier_name ?? invoice.supplier_id}</td>
                    <td className="numeric">{money(invoice.amount)}</td>
                    <td>
                      <Badge status={invoice.status} />
                    </td>
                    <td>
                      <Badge status={invoice.latest_action_status} />
                    </td>
                    <td className="muted">{invoice.scenario}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
