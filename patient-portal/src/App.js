import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import Login from "./pages/Login";
import Appointments from "./pages/Appointments";
import Results from "./pages/Results";
import Billing from "./pages/Billing";
const TABS = [
    { key: "appointments", label: "Appointments", emoji: "📅" },
    { key: "results", label: "Lab Results", emoji: "🧪" },
    { key: "billing", label: "Billing", emoji: "💳" },
];
export default function App() {
    const [token, setToken] = useState(() => sessionStorage.getItem("portal_token"));
    const [patient, setPatient] = useState(null);
    const [tab, setTab] = useState("appointments");
    if (!token) {
        return _jsx(Login, { onLogin: (t, p) => { setToken(t); setPatient(p); } });
    }
    const name = patient
        ? `${patient.first_name ?? ""} ${patient.last_name ?? ""}`.trim()
        : "Patient";
    return (_jsxs("div", { style: { minHeight: "100vh", background: "#f0f9ff" }, children: [_jsxs("header", { style: {
                    background: "#0ea5e9", color: "#fff",
                    padding: "14px 20px", display: "flex", justifyContent: "space-between", alignItems: "center",
                }, children: [_jsxs("div", { children: [_jsx("p", { style: { fontWeight: 700, fontSize: 16 }, children: "Royan Hospital" }), _jsx("p", { style: { fontSize: 12, opacity: 0.85 }, children: name })] }), _jsx("button", { onClick: () => { sessionStorage.removeItem("portal_token"); setToken(null); setPatient(null); }, style: { background: "rgba(255,255,255,0.2)", border: "none", color: "#fff", borderRadius: 8, padding: "6px 14px", fontSize: 13, cursor: "pointer" }, children: "Sign Out" })] }), _jsx("nav", { style: { background: "#fff", display: "flex", borderBottom: "1px solid #e2e8f0" }, children: TABS.map(t => (_jsxs("button", { onClick: () => setTab(t.key), style: {
                        flex: 1, padding: "12px 4px", border: "none", cursor: "pointer", fontSize: 12,
                        fontWeight: tab === t.key ? 700 : 500,
                        color: tab === t.key ? "#0ea5e9" : "#64748b",
                        background: "transparent",
                        borderBottom: tab === t.key ? "2px solid #0ea5e9" : "2px solid transparent",
                        transition: "all 0.15s",
                    }, children: [_jsx("div", { children: t.emoji }), t.label] }, t.key))) }), _jsxs("main", { style: { maxWidth: 600, margin: "0 auto", padding: 20 }, children: [tab === "appointments" && _jsx(Appointments, {}), tab === "results" && _jsx(Results, {}), tab === "billing" && _jsx(Billing, {})] }), _jsx("footer", { style: { textAlign: "center", padding: "20px 16px", fontSize: 11, color: "#94a3b8" }, children: "Royan Hospital Patient Portal \u00B7 Your data is handled in compliance with NDPA 2023" })] }));
}
