import { useState } from "react";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Appointments from "./pages/Appointments";
import Results from "./pages/Results";
import Billing from "./pages/Billing";
import Medications from "./pages/Medications";
import VitalsHistory from "./pages/VitalsHistory";
import Messages from "./pages/Messages";
import Telemedicine from "./pages/Telemedicine";
import Admissions from "./pages/Admissions";

type Tab = "home" | "appointments" | "results" | "billing"
         | "medications" | "vitals" | "messages" | "telemedicine" | "admissions";

const TABS: { key: Tab; label: string; emoji: string }[] = [
  { key: "home",         label: "Home",         emoji: "🏠" },
  { key: "appointments", label: "Appointments",  emoji: "📅" },
  { key: "results",      label: "Lab Results",   emoji: "🧪" },
  { key: "billing",      label: "Billing",       emoji: "💳" },
  { key: "medications",  label: "Medications",   emoji: "💊" },
  { key: "vitals",       label: "My Vitals",     emoji: "❤️" },
  { key: "messages",     label: "Messages",      emoji: "💬" },
  { key: "telemedicine", label: "Video Consult",  emoji: "📹" },
  { key: "admissions",  label: "My History",    emoji: "🏥" },
];

export default function App() {
  const [token, setToken] = useState<string | null>(
    () => sessionStorage.getItem("portal_token"),
  );
  const [patient, setPatient] = useState<Record<string, unknown> | null>(null);
  const [tab, setTab] = useState<Tab>("home");

  if (!token) {
    return <Login onLogin={(t, p) => { setToken(t); setPatient(p); }} />;
  }

  const name = patient
    ? `${patient.first_name ?? ""} ${patient.last_name ?? ""}`.trim()
    : "Patient";

  return (
    <div style={{ minHeight: "100vh", background: "#f0f9ff" }}>
      {/* Header */}
      <header style={{
        background: "#0ea5e9", color: "#fff",
        padding: "14px 20px", display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <p style={{ fontWeight: 700, fontSize: 16 }}>Royan Hospital</p>
          <p style={{ fontSize: 12, opacity: 0.85 }}>Welcome, {name}</p>
        </div>
        <button
          onClick={() => { sessionStorage.removeItem("portal_token"); setToken(null); setPatient(null); }}
          style={{ background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 8, padding: "6px 14px", fontSize: 13, cursor: "pointer" }}
        >
          Sign Out
        </button>
      </header>

      {/* Tab bar — horizontal scroll for 8 tabs on mobile */}
      <nav style={{
        background: "#fff", display: "flex", borderBottom: "1px solid #e2e8f0",
        overflowX: "auto", WebkitOverflowScrolling: "touch",
      }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              flexShrink: 0, padding: "12px 14px", border: "none", cursor: "pointer", fontSize: 11,
              fontWeight: tab === t.key ? 700 : 500,
              color: tab === t.key ? "#0ea5e9" : "#64748b",
              background: "transparent",
              borderBottom: tab === t.key ? "2px solid #0ea5e9" : "2px solid transparent",
              transition: "all 0.15s", whiteSpace: "nowrap",
            }}
          >
            <div style={{ fontSize: 16, marginBottom: 2 }}>{t.emoji}</div>
            {t.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main style={{ maxWidth: 600, margin: "0 auto", padding: 20 }}>
        {tab === "home"         && <Home patient={patient} />}
        {tab === "appointments" && <Appointments />}
        {tab === "results"      && <Results />}
        {tab === "billing"      && <Billing />}
        {tab === "medications"  && <Medications />}
        {tab === "vitals"       && <VitalsHistory />}
        {tab === "messages"     && <Messages />}
        {tab === "telemedicine" && <Telemedicine />}
        {tab === "admissions"  && <Admissions />}
      </main>

      {/* Footer */}
      <footer style={{ textAlign: "center", padding: "20px 16px", fontSize: 11, color: "#94a3b8" }}>
        Royan Hospital Patient Portal · Your data is handled in compliance with NDPA 2023
      </footer>
    </div>
  );
}
