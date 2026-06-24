import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDateTime(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function VitalsHistory() {
  const [vitals, setVitals] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    portalApi.vitals()
      .then(r => setVitals(r.vitals ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error) return <div style={s.error}>{error}</div>;

  return (
    <div style={s.section}>
      <h2 style={s.h2}>My Vitals (Last 30 Days)</h2>
      {vitals.length === 0 ? (
        <p style={s.empty}>No vitals recorded in the last 30 days.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(vitals as Record<string, unknown>[]).map((v, i) => (
            <div key={String(v.id ?? i)} style={{ background: "#fff", borderRadius: 12, padding: "14px 16px", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
              <p style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>{fmtDateTime(String(v.recorded_at ?? ""))}</p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                {v.bp_systolic != null && (
                  <div>
                    <p style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase" }}>BP</p>
                    <p style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>{String(v.bp_systolic)}/{String(v.bp_diastolic)} <span style={{ fontSize: 10, fontWeight: 400, color: "#64748b" }}>mmHg</span></p>
                  </div>
                )}
                {v.pulse != null && (
                  <div>
                    <p style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase" }}>Pulse</p>
                    <p style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>{String(v.pulse)} <span style={{ fontSize: 10, fontWeight: 400, color: "#64748b" }}>bpm</span></p>
                  </div>
                )}
                {v.temperature != null && (
                  <div>
                    <p style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase" }}>Temp</p>
                    <p style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>{String(v.temperature)}<span style={{ fontSize: 10, fontWeight: 400, color: "#64748b" }}>°C</span></p>
                  </div>
                )}
                {v.spo2 != null && (
                  <div>
                    <p style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase" }}>SpO2</p>
                    <p style={{ fontWeight: 700, fontSize: 15, color: Number(v.spo2) < 95 ? "#dc2626" : "#0f172a" }}>{String(v.spo2)}<span style={{ fontSize: 10, fontWeight: 400, color: "#64748b" }}>%</span></p>
                  </div>
                )}
                {v.weight_kg != null && (
                  <div>
                    <p style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase" }}>Weight</p>
                    <p style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>{String(v.weight_kg)} <span style={{ fontSize: 10, fontWeight: 400, color: "#64748b" }}>kg</span></p>
                  </div>
                )}
                {v.pain_score != null && (
                  <div>
                    <p style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase" }}>Pain</p>
                    <p style={{ fontWeight: 700, fontSize: 15, color: Number(v.pain_score) >= 7 ? "#dc2626" : "#0f172a" }}>{String(v.pain_score)}<span style={{ fontSize: 10, fontWeight: 400, color: "#64748b" }}>/10</span></p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
