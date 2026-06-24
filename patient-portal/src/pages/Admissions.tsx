import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
}

const TYPE_COLOR: Record<string, string> = {
  inpatient:  "#3b82f6",
  outpatient: "#10b981",
  emergency:  "#ef4444",
  maternity:  "#a855f7",
  surgical:   "#f97316",
};

const STATUS_COLOR: Record<string, string> = {
  discharged:        "#22c55e",
  consulting:        "#3b82f6",
  patient_registered:"#94a3b8",
  triaged:           "#f59e0b",
  admitted:          "#6366f1",
};

export default function Admissions() {
  const [encounters, setEncounters] = useState<unknown[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);

  useEffect(() => {
    portalApi.encounters()
      .then(r => setEncounters(r.encounters))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error)   return <div style={s.error}>{error}</div>;

  return (
    <div style={s.section}>
      <h2 style={s.h2}>My Hospital History</h2>
      {encounters.length === 0 ? (
        <p style={s.empty}>No encounter history found.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(encounters as Record<string, unknown>[]).map((enc, i) => {
            const type        = String(enc.encounter_type ?? "outpatient");
            const status      = String(enc.status ?? "");
            const typeColor   = TYPE_COLOR[type]   ?? "#64748b";
            const statusColor = STATUS_COLOR[status] ?? "#94a3b8";
            return (
              <div key={String(enc.id ?? i)} style={s.row}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                    <span style={{ ...s.badge, backgroundColor: typeColor + "22", color: typeColor, border: `1px solid ${typeColor}55`, textTransform: "capitalize" }}>
                      {type}
                    </span>
                    <span style={{ ...s.badge, backgroundColor: statusColor + "22", color: statusColor, border: `1px solid ${statusColor}55`, textTransform: "capitalize" }}>
                      {status.replace(/_/g, " ")}
                    </span>
                  </div>
                  {enc.department && <p style={s.bold}>{String(enc.department)}</p>}
                  {enc.consulting_doctor && <p style={s.muted}>Dr. {String(enc.consulting_doctor)}</p>}
                  {enc.chief_complaint && (
                    <p style={{ fontSize: 13, color: "#374151", marginTop: 2 }}>{String(enc.chief_complaint)}</p>
                  )}
                  <p style={s.muted}>
                    {fmtDate(String(enc.created_at ?? ""))}
                    {enc.discharge_at ? ` → ${fmtDate(String(enc.discharge_at))}` : ""}
                  </p>
                  {enc.discharge_summary && (
                    <p style={{ fontSize: 12, color: "#6b7280", marginTop: 4, fontStyle: "italic" }}>
                      {String(enc.discharge_summary)}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
