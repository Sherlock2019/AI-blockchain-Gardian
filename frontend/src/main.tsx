import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout, Section } from "./components/Layout";
import { AgentActivityPage } from "./pages/AgentActivity";
import { ApprovalsPage } from "./pages/Approvals";
import { ArchitecturePage } from "./pages/Architecture";
import { AuditTrailPage } from "./pages/AuditTrail";
import { BlockchainPage } from "./pages/Blockchain";
import { DemoPage } from "./pages/Demo";
import { InvoiceDetailPage } from "./pages/InvoiceDetail";
import { InvoicesPage } from "./pages/Invoices";
import { LandingPage } from "./pages/Landing";
import { PassportPage } from "./pages/Passport";
import { ReceiptsPage } from "./pages/Receipts";
import { TechnicalPage } from "./pages/Technical";
import { AppProvider } from "./services/AppContext";
import "./styles.css";

const AUDIT_TABS = [
  { to: "/audit", label: "Receipts", end: true },
  { to: "/audit/ledger", label: "Blockchain records" },
  { to: "/audit/trail", label: "Audit trail" },
];

const TECHNICAL_TABS = [
  { to: "/technical", label: "Stack & metrics", end: true },
  { to: "/technical/invoices", label: "Invoices" },
  { to: "/technical/agent", label: "Agent runs" },
  { to: "/technical/approvals", label: "Approval queue" },
  { to: "/technical/passport", label: "Agent passport" },
];

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<LandingPage />} />
            <Route path="demo" element={<DemoPage />} />
            <Route
              path="audit"
              element={
                <Section
                  title="Audit & Verify"
                  intro="Every executed action leaves a receipt. Check any of them against the fingerprint recorded on the blockchain."
                  tabs={AUDIT_TABS}
                />
              }
            >
              <Route index element={<ReceiptsPage />} />
              <Route path="receipts/:receiptId" element={<ReceiptsPage />} />
              <Route path="ledger" element={<BlockchainPage />} />
              <Route path="trail" element={<AuditTrailPage />} />
            </Route>
            <Route path="architecture" element={<ArchitecturePage />} />
            <Route
              path="technical"
              element={
                <Section
                  title="Technical Details"
                  intro="The implementation underneath the demo: every record, decision and check, as the system stores it."
                  tabs={TECHNICAL_TABS}
                />
              }
            >
              <Route index element={<TechnicalPage />} />
              <Route path="invoices" element={<InvoicesPage />} />
              <Route path="invoices/:invoiceId" element={<InvoiceDetailPage />} />
              <Route path="agent" element={<AgentActivityPage />} />
              <Route path="approvals" element={<ApprovalsPage />} />
              <Route path="passport" element={<PassportPage />} />
            </Route>
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
