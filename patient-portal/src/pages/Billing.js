import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";
function fmtCurrency(n) {
    return "₦" + Number(n ?? 0).toLocaleString("en-NG");
}
export default function Billing() {
    const [bills, setBills] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [paying, setPaying] = useState(null);
    useEffect(() => {
        portalApi.bills()
            .then(r => setBills(r.bills))
            .catch(e => setError(e.message))
            .finally(() => setLoading(false));
    }, []);
    async function handlePay(bill) {
        setPaying(String(bill.id));
        try {
            const res = await portalApi.payBill(String(bill.id), "paystack");
            if (res.checkout_url) {
                window.open(res.checkout_url, "_blank");
            }
            else {
                alert("Payment stub mode — no live checkout URL. Transaction reference: " + res.reference);
            }
        }
        catch (e) {
            alert(e instanceof Error ? e.message : "Payment initiation failed");
        }
        finally {
            setPaying(null);
        }
    }
    if (loading)
        return _jsx("div", { style: s.spinner, children: "Loading\u2026" });
    if (error)
        return _jsx("div", { style: s.error, children: error });
    const pendingTotal = bills
        .filter(b => b.status !== "paid" && b.status !== "waived")
        .reduce((sum, b) => sum + Number(b.total_amount ?? 0), 0);
    return (_jsxs("div", { style: s.section, children: [_jsx("h2", { style: s.h2, children: "My Bills" }), pendingTotal > 0 && (_jsx("div", { style: { background: "#fef3c7", border: "1px solid #fbbf24", borderRadius: 12, padding: "12px 16px", marginBottom: 16 }, children: _jsxs("p", { style: { fontWeight: 600, color: "#92400e" }, children: ["Outstanding Balance: ", fmtCurrency(pendingTotal)] }) })), bills.length === 0 ? (_jsx("p", { style: s.empty, children: "No bills found." })) : (_jsx("div", { style: { display: "flex", flexDirection: "column", gap: 12 }, children: bills.map((b, i) => {
                    const isPaid = b.status === "paid" || b.status === "waived";
                    return (_jsxs("div", { style: { ...s.row, flexDirection: "column", gap: 8, alignItems: "stretch" }, children: [_jsxs("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start" }, children: [_jsxs("div", { children: [_jsx("p", { style: s.bold, children: fmtCurrency(b.total_amount) }), Number(b.hmo_covered ?? 0) > 0 && (_jsxs("p", { style: s.muted, children: ["HMO covers: ", fmtCurrency(b.hmo_covered)] })), _jsxs("p", { style: s.muted, children: ["Patient pays: ", fmtCurrency(Number(b.total_amount ?? 0) - Number(b.hmo_covered ?? 0))] })] }), _jsx("span", { style: { ...s.badge, ...(isPaid ? s.badgeGreen : s.badgeOrange) }, children: String(b.status ?? "pending") })] }), !isPaid && (_jsx("button", { style: { ...s.btn, background: "#10b981", fontSize: 13, padding: "8px 16px", opacity: paying === String(b.id) ? 0.7 : 1 }, disabled: paying === String(b.id), onClick: () => handlePay(b), children: paying === String(b.id) ? "Redirecting…" : "Pay Now via Paystack" }))] }, String(b.id ?? i)));
                }) }))] }));
}
