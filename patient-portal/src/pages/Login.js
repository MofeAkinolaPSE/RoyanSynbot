import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";
export default function Login({ onLogin }) {
    const [mrn, setMrn] = useState("");
    const [phone, setPhone] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    async function handleSubmit(e) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            const res = await portalApi.login(mrn.trim(), phone.trim());
            sessionStorage.setItem("portal_token", res.token);
            onLogin(res.token, res.patient);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "Login failed. Check your MRN and phone number.");
        }
        finally {
            setLoading(false);
        }
    }
    return (_jsx("div", { style: s.center, children: _jsxs("div", { style: s.card, children: [_jsxs("div", { style: { textAlign: "center", marginBottom: 24 }, children: [_jsx("div", { style: s.logo, children: "R" }), _jsx("h1", { style: s.h1, children: "Royan Hospital" }), _jsx("p", { style: s.sub, children: "Patient Portal" })] }), _jsxs("form", { onSubmit: handleSubmit, style: { display: "flex", flexDirection: "column", gap: 16 }, children: [_jsxs("div", { children: [_jsx("label", { style: s.label, children: "Hospital Number (MRN)" }), _jsx("input", { style: s.input, value: mrn, onChange: e => setMrn(e.target.value), placeholder: "e.g. RYN-00123", required: true, autoComplete: "username" })] }), _jsxs("div", { children: [_jsx("label", { style: s.label, children: "Phone Number" }), _jsx("input", { style: s.input, value: phone, onChange: e => setPhone(e.target.value), placeholder: "+234 800 000 0000", required: true, autoComplete: "tel" })] }), error && _jsx("p", { style: s.error, children: error }), _jsx("button", { type: "submit", style: { ...s.btn, opacity: loading ? 0.7 : 1 }, disabled: loading, children: loading ? "Signing in…" : "Sign In" })] }), _jsx("p", { style: { textAlign: "center", fontSize: 12, color: "#64748b", marginTop: 20 }, children: "Use the MRN on your hospital card and the phone number registered at reception." })] }) }));
}
