import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtCurrency(n: unknown) {
  return "₦" + Number(n ?? 0).toLocaleString("en-NG");
}

export default function Billing() {
  const [bills, setBills] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState<string | null>(null);

  useEffect(() => {
    portalApi.bills()
      .then(r => setBills(r.bills))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handlePay(bill: Record<string, unknown>) {
    setPaying(String(bill.id));
    try {
      const res = await portalApi.payBill(String(bill.id), "paystack");
      if (res.checkout_url) {
        window.open(res.checkout_url, "_blank");
      } else {
        alert("Payment stub mode — no live checkout URL. Transaction reference: " + res.reference);
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Payment initiation failed");
    } finally {
      setPaying(null);
    }
  }

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error) return <div style={s.error}>{error}</div>;

  const pendingTotal = (bills as Record<string, unknown>[])
    .filter(b => b.status !== "paid" && b.status !== "waived")
    .reduce((sum, b) => sum + Number(b.total_amount ?? 0), 0);

  return (
    <div style={s.section}>
      <h2 style={s.h2}>My Bills</h2>
      {pendingTotal > 0 && (
        <div style={{ background: "#fef3c7", border: "1px solid #fbbf24", borderRadius: 12, padding: "12px 16px", marginBottom: 16 }}>
          <p style={{ fontWeight: 600, color: "#92400e" }}>Outstanding Balance: {fmtCurrency(pendingTotal)}</p>
        </div>
      )}
      {bills.length === 0 ? (
        <p style={s.empty}>No bills found.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(bills as Record<string, unknown>[]).map((b, i) => {
            const isPaid = b.status === "paid" || b.status === "waived";
            return (
              <div key={String(b.id ?? i)} style={{ ...s.row, flexDirection: "column", gap: 8, alignItems: "stretch" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <p style={s.bold}>{fmtCurrency(b.total_amount)}</p>
                    {Number(b.hmo_covered ?? 0) > 0 && (
                      <p style={s.muted}>HMO covers: {fmtCurrency(b.hmo_covered)}</p>
                    )}
                    <p style={s.muted}>
                      Patient pays: {fmtCurrency(Number(b.total_amount ?? 0) - Number(b.hmo_covered ?? 0))}
                    </p>
                  </div>
                  <span style={{ ...s.badge, ...(isPaid ? s.badgeGreen : s.badgeOrange) }}>
                    {String(b.status ?? "pending")}
                  </span>
                </div>
                {/* Itemised line items (available for bills created via service catalog) */}
                {Array.isArray(b.items) && (b.items as Record<string, unknown>[]).length > 0 && (
                  <div style={{ borderTop: "1px solid #e5e7eb", paddingTop: 8, marginTop: 4 }}>
                    {(b.items as Record<string, unknown>[]).map((item, idx) => (
                      <div key={idx} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#6b7280", marginBottom: 2 }}>
                        <span>{String(item.description ?? item.category ?? "Service")}</span>
                        <span>{fmtCurrency(Number(item.patient_amount ?? item.unit_price ?? 0))}</span>
                      </div>
                    ))}
                  </div>
                )}
                {!isPaid && (
                  <button
                    style={{ ...s.btn, background: "#10b981", fontSize: 13, padding: "8px 16px", opacity: paying === String(b.id) ? 0.7 : 1 }}
                    disabled={paying === String(b.id)}
                    onClick={() => handlePay(b as Record<string, unknown>)}
                  >
                    {paying === String(b.id) ? "Redirecting…" : "Pay Now via Paystack"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
