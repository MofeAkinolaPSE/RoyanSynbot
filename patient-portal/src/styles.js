export const s = {
    center: {
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", padding: 16, background: "#f0f9ff",
    },
    card: {
        background: "#fff", borderRadius: 16, padding: 32,
        boxShadow: "0 4px 24px rgba(0,0,0,0.08)", width: "100%", maxWidth: 400,
    },
    logo: {
        width: 52, height: 52, borderRadius: 12, background: "#0ea5e9",
        color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 24, fontWeight: 700, margin: "0 auto 12px",
    },
    h1: { fontSize: 22, fontWeight: 700, color: "#0f172a", textAlign: "center" },
    h2: { fontSize: 18, fontWeight: 700, color: "#0f172a", marginBottom: 16 },
    sub: { fontSize: 13, color: "#64748b", textAlign: "center", marginTop: 4 },
    label: { display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 },
    input: {
        width: "100%", padding: "10px 12px", borderRadius: 8,
        border: "1px solid #d1d5db", fontSize: 14, outline: "none",
        transition: "border-color 0.15s",
    },
    btn: {
        background: "#0ea5e9", color: "#fff", border: "none", borderRadius: 8,
        padding: "11px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer",
        width: "100%", transition: "background 0.15s",
    },
    error: { color: "#dc2626", fontSize: 13, background: "#fef2f2", padding: "8px 12px", borderRadius: 8 },
    spinner: { padding: 32, textAlign: "center", color: "#64748b" },
    empty: { color: "#94a3b8", fontSize: 14, textAlign: "center", padding: "32px 0" },
    section: { padding: "0 0 32px" },
    row: {
        background: "#fff", borderRadius: 12, padding: "14px 16px",
        boxShadow: "0 1px 4px rgba(0,0,0,0.06)", display: "flex",
        justifyContent: "space-between", alignItems: "center", gap: 12,
    },
    bold: { fontWeight: 600, fontSize: 14, color: "#0f172a" },
    muted: { fontSize: 12, color: "#64748b", marginTop: 2 },
    badge: {
        display: "inline-block", padding: "3px 10px", borderRadius: 20,
        fontSize: 11, fontWeight: 600, textTransform: "capitalize", whiteSpace: "nowrap",
    },
    badgeGreen: { background: "#dcfce7", color: "#16a34a", border: "1px solid #86efac" },
    badgeBlue: { background: "#dbeafe", color: "#2563eb", border: "1px solid #93c5fd" },
    badgeOrange: { background: "#fff7ed", color: "#ea580c", border: "1px solid #fdba74" },
};
