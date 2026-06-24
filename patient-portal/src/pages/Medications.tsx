import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
}

export default function Medications() {
  const [prescriptions, setPrescriptions] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    portalApi.prescriptions()
      .then(r => setPrescriptions(r.prescriptions ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error) return <div style={s.error}>{error}</div>;

  const active = (prescriptions as Record<string, unknown>[]).filter(
    rx => ["pending", "partially_dispensed"].includes(String(rx.status ?? ""))
  );
  const past = (prescriptions as Record<string, unknown>[]).filter(
    rx => !["pending", "partially_dispensed"].includes(String(rx.status ?? ""))
  );

  return (
    <div style={s.section}>
      <h2 style={s.h2}>My Medications</h2>

      {prescriptions.length === 0 ? (
        <p style={s.empty}>No prescriptions found.</p>
      ) : (
        <>
          {active.length > 0 && (
            <>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Active</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
                {active.map((rx, i) => (
                  <div key={String((rx as Record<string, unknown>).id ?? i)} style={{ ...s.row, background: "#f0fdf4", border: "1px solid #86efac" }}>
                    <div>
                      <p style={s.bold}>{String((rx as Record<string, unknown>).drug_name ?? "Medication")}</p>
                      <p style={s.muted}>{String((rx as Record<string, unknown>).dosage ?? "—")} · {String((rx as Record<string, unknown>).frequency ?? "—")}</p>
                      {(rx as Record<string, unknown>).duration && <p style={s.muted}>Duration: {String((rx as Record<string, unknown>).duration)}</p>}
                      {(rx as Record<string, unknown>).route && <p style={s.muted}>Route: {String((rx as Record<string, unknown>).route)}</p>}
                      <p style={s.muted}>Prescribed: {fmtDate(String((rx as Record<string, unknown>).prescribed_at ?? ""))}</p>
                    </div>
                    <span style={{ ...s.badge, ...s.badgeGreen }}>Active</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {past.length > 0 && (
            <>
              <p style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Completed / Past</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {past.map((rx, i) => (
                  <div key={String((rx as Record<string, unknown>).id ?? i)} style={{ ...s.row, opacity: 0.75 }}>
                    <div>
                      <p style={s.bold}>{String((rx as Record<string, unknown>).drug_name ?? "Medication")}</p>
                      <p style={s.muted}>{String((rx as Record<string, unknown>).dosage ?? "—")} · {String((rx as Record<string, unknown>).frequency ?? "—")}</p>
                    </div>
                    <span style={{ ...s.badge, background: "#f1f5f9", color: "#64748b", border: "1px solid #e2e8f0" }}>
                      {String((rx as Record<string, unknown>).status ?? "past").replace(/_/g, " ")}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
