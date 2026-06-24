import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";
function fmtDate(ts) {
    if (!ts)
        return "—";
    return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
}
const INTERP_COLORS = {
    normal: "#22c55e",
    abnormal: "#f97316",
    critical: "#ef4444",
    inconclusive: "#94a3b8",
};
export default function Results() {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    useEffect(() => {
        portalApi.labResults()
            .then(r => setResults(r.results))
            .catch(e => setError(e.message))
            .finally(() => setLoading(false));
    }, []);
    if (loading)
        return _jsx("div", { style: s.spinner, children: "Loading\u2026" });
    if (error)
        return _jsx("div", { style: s.error, children: error });
    return (_jsxs("div", { style: s.section, children: [_jsx("h2", { style: s.h2, children: "Lab Results" }), results.length === 0 ? (_jsx("p", { style: s.empty, children: "No lab results available yet." })) : (_jsx("div", { style: { display: "flex", flexDirection: "column", gap: 12 }, children: results.map((r, i) => {
                    const interp = String(r.interpretation ?? "");
                    const color = INTERP_COLORS[interp] ?? "#64748b";
                    return (_jsxs("div", { style: s.row, children: [_jsxs("div", { style: { flex: 1 }, children: [_jsx("p", { style: s.bold, children: String(r.test_name ?? "Test") }), !!r.result_value && (_jsxs("p", { style: { fontSize: 14, color: "#0f172a", marginTop: 2 }, children: ["Result: ", _jsx("strong", { children: String(r.result_value) }), r.result_unit ? ` ${r.result_unit}` : ""] })), !!r.reference_range && (_jsxs("p", { style: s.muted, children: ["Reference: ", String(r.reference_range)] })), _jsx("p", { style: s.muted, children: fmtDate(String(r.resulted_at ?? r.updated_at ?? "")) })] }), interp && (_jsx("span", { style: { ...s.badge, backgroundColor: color + "22", color, border: `1px solid ${color}55`, textTransform: "capitalize" }, children: interp }))] }, String(r.id ?? i)));
                }) }))] }));
}
