import { Link, NavLink, Outlet } from "react-router-dom";
import { useApp } from "../services/AppContext";
import { Badge, Notice } from "./ui";

const NAVIGATION = [
  { to: "/demo", label: "Demo" },
  { to: "/audit", label: "Audit & Verify" },
  { to: "/architecture", label: "Architecture" },
  { to: "/technical", label: "Technical Details" },
];

export function Layout() {
  const { system, backendError } = useApp();
  const ledger = system?.ledger;

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <strong>TrustChain AI</strong>
        </Link>
        <nav>
          {NAVIGATION.map((item) => (
            <NavLink key={item.to} to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="row topbar-status">
          {system && <Badge status={system.ai_enabled ? "ACTIVE" : "BLOCKED"} label={`AI ${system.ai_enabled ? "ON" : "OFF"}`} />}
          {ledger && (
            <Badge
              status={ledger.connected ? (ledger.mode === "SIMULATED" ? "SIMULATED" : "VERIFIED") : "UNAVAILABLE"}
              label={ledger.connected ? (ledger.mode === "SIMULATED" ? "SIMULATED LEDGER" : "LOCAL BLOCKCHAIN") : "LEDGER UNREACHABLE"}
            />
          )}
        </div>
      </header>
      <main className="content">
        {backendError && <Notice tone="bad">{backendError}</Notice>}
        <Outlet />
      </main>
    </div>
  );
}

export interface Tab {
  to: string;
  label: string;
  end?: boolean;
}

/** A section with its own tabs. The identity picker lives here: the guided demo does not need it. */
export function Section({ title, intro, tabs }: { title: string; intro: string; tabs: Tab[] }) {
  const { users, user, switchUser } = useApp();
  return (
    <>
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p className="muted">{intro}</p>
        </div>
        <label className="row">
          <span className="muted">Acting as</span>
          <select value={user?.id ?? ""} onChange={(event) => switchUser(event.target.value)}>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} ({u.role.replace("_", " ")})
              </option>
            ))}
          </select>
        </label>
      </div>
      <nav className="tabs">
        {tabs.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end}>
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}
