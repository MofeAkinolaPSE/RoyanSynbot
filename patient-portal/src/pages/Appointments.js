import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";
function fmtDate(ts) {
    if (!ts)
        return "—";
    return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
export default function Appointments() {
    const [appts, setAppts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    useEffect(() => {
        portalApi.appointments()
            .then(r => setAppts(r.appointments))
            .catch(e => setError(e.message))
            .finally(() => setLoading(false));
    }, []);
    if (loading)
        return _jsx("div", { style: s.spinner, children: "Loading\u2026" });
    if (error)
        return _jsx("div", { style: s.error, children: error });
    return (_jsxs("div", { style: s.section, children: [_jsx("h2", { style: s.h2, children: "My Appointments" }), appts.length === 0 ? (_jsx("p", { style: s.empty, children: "No upcoming appointments found." })) : (_jsx("div", { style: { display: "flex", flexDirection: "column", gap: 12 }, children: appts.map((a, i) => (_jsxs("div", { style: s.row, children: [_jsxs("div", { children: [_jsx("p", { style: s.bold, children: String(a.appointment_type ?? a.service ?? "Appointment") }), _jsx("p", { style: s.muted, children: fmtDate(String(a.appointment_date ?? a.scheduled_at ?? "")) }), !!a.doctor_name && _jsxs("p", { style: s.muted, children: ["Dr. ", String(a.doctor_name)] }), !!a.department && _jsx("p", { style: s.muted, children: String(a.department) })] }), _jsx("span", { style: { ...s.badge, ...(a.status === "confirmed" ? s.badgeGreen : s.badgeBlue) }, children: String(a.status ?? "booked") })] }, String(a.id ?? i)))) }))] }));
}
