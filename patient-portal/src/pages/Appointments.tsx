import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function Appointments() {
  const [appts, setAppts] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    portalApi.appointments()
      .then(r => setAppts(r.appointments))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error) return <div style={s.error}>{error}</div>;

  return (
    <div style={s.section}>
      <h2 style={s.h2}>My Appointments</h2>
      {appts.length === 0 ? (
        <p style={s.empty}>No upcoming appointments found.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(appts as Record<string, unknown>[]).map((a, i) => (
            <div key={String(a.id ?? i)} style={s.row}>
              <div>
                <p style={s.bold}>{String(a.appointment_type ?? a.service ?? "Appointment")}</p>
                <p style={s.muted}>{fmtDate(String(a.appointment_date ?? a.scheduled_at ?? ""))}</p>
                {!!a.doctor_name && <p style={s.muted}>Dr. {String(a.doctor_name)}</p>}
                {!!a.department && <p style={s.muted}>{String(a.department)}</p>}
              </div>
              <span style={{ ...s.badge, ...(a.status === "confirmed" ? s.badgeGreen : s.badgeBlue) }}>
                {String(a.status ?? "booked")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
