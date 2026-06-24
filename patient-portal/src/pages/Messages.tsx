import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function Messages() {
  const [notifications, setNotifications] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    portalApi.notifications()
      .then(r => setNotifications(r.notifications ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error) return <div style={s.error}>{error}</div>;

  return (
    <div style={s.section}>
      <h2 style={s.h2}>Messages from Royan Hospital</h2>
      {notifications.length === 0 ? (
        <p style={s.empty}>No messages found.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {(notifications as Record<string, unknown>[]).map((n, i) => {
            const channel = String(n.channel ?? "sms").toUpperCase();
            const channelStyle = channel === "WHATSAPP"
              ? { background: "#dcfce7", color: "#16a34a", border: "1px solid #86efac" }
              : { background: "#dbeafe", color: "#2563eb", border: "1px solid #93c5fd" };
            const isDelivered = ["delivered", "sent"].includes(String(n.status ?? ""));
            return (
              <div key={String(n.id ?? i)} style={{ background: "#fff", borderRadius: 12, padding: "14px 16px", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ ...s.badge, ...channelStyle }}>{channel}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ ...s.badge, background: isDelivered ? "#f0fdf4" : "#fef9c3", color: isDelivered ? "#15803d" : "#a16207", border: `1px solid ${isDelivered ? "#86efac" : "#fde047"}` }}>
                      {String(n.status ?? "sent")}
                    </span>
                    <span style={s.muted}>{fmtDate(String(n.sent_at ?? n.created_at ?? ""))}</span>
                  </div>
                </div>
                <p style={{ fontSize: 14, color: "#0f172a", lineHeight: 1.5 }}>{String(n.message ?? "")}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
