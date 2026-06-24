import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDateTime(date?: string, time?: string) {
  if (!date) return "—";
  const d = new Date(date).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
  return time ? `${d} at ${time.slice(0, 5)}` : d;
}

export default function Telemedicine() {
  const [sessions, setSessions] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    portalApi.telemedicine()
      .then(r => setSessions(r.sessions ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error) return <div style={s.error}>{error}</div>;

  return (
    <div style={s.section}>
      <h2 style={s.h2}>Video Consultations</h2>
      <p style={{ ...s.muted, marginBottom: 20 }}>Upcoming video consult sessions with your doctor. Click Join to enter the meeting.</p>
      {sessions.length === 0 ? (
        <div style={{ background: "#f0f9ff", borderRadius: 12, padding: 24, textAlign: "center" }}>
          <p style={{ fontSize: 32, marginBottom: 8 }}>📹</p>
          <p style={s.empty}>No scheduled video consultations.</p>
          <p style={{ fontSize: 13, color: "#64748b" }}>Contact Royan Hospital to schedule a telemedicine appointment.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(sessions as Record<string, unknown>[]).map((session, i) => {
            const isActive = session.status === "active";
            const meetingLink = String(session.meeting_link ?? session.patient_link ?? "");
            return (
              <div key={String(session.id ?? i)} style={{
                background: isActive ? "#f0fdf4" : "#fff",
                border: `1px solid ${isActive ? "#86efac" : "#e2e8f0"}`,
                borderRadius: 14, padding: "16px 20px",
                boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                  <div>
                    <p style={s.bold}>{String(session.visit_type ?? "Consultation").replace(/_/g, " ")}</p>
                    <p style={s.muted}>{fmtDateTime(String(session.scheduled_date ?? ""), String(session.scheduled_time ?? ""))}</p>
                    {session.doctor_id && <p style={s.muted}>Doctor: {String(session.doctor_id)}</p>}
                    {session.duration_minutes && <p style={s.muted}>Duration: {String(session.duration_minutes)} min</p>}
                    {session.chief_complaint && <p style={s.muted}>Reason: {String(session.chief_complaint)}</p>}
                  </div>
                  <span style={{
                    ...s.badge,
                    ...(isActive ? s.badgeGreen : s.badgeBlue),
                  }}>
                    {String(session.status ?? "scheduled")}
                  </span>
                </div>
                {meetingLink && (
                  <a
                    href={meetingLink}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: "inline-block", background: isActive ? "#16a34a" : "#0ea5e9",
                      color: "#fff", padding: "10px 20px", borderRadius: 8,
                      fontWeight: 700, fontSize: 14, textDecoration: "none",
                    }}
                  >
                    📹 {isActive ? "Join Now (Live)" : "Join Session"}
                  </a>
                )}
                {!meetingLink && (
                  <p style={{ fontSize: 13, color: "#94a3b8" }}>Meeting link will be available soon</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
