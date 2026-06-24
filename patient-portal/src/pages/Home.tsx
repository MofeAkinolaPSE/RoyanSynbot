import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
}

export default function Home({ patient }: { patient: Record<string, unknown> | null }) {
  const [appts, setAppts] = useState<unknown[]>([]);
  const [bills, setBills] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      portalApi.appointments(),
      portalApi.bills(),
    ]).then(([aptRes, billRes]) => {
      if (aptRes.status === "fulfilled") setAppts(aptRes.value.appointments ?? []);
      if (billRes.status === "fulfilled") setBills(billRes.value.bills ?? []);
    }).finally(() => setLoading(false));
  }, []);

  const name = patient
    ? (`${patient.first_name ?? ""} ${patient.last_name ?? ""}`.trim() || "Patient")
    : "Patient";
  const nextAppt = (appts as Record<string, unknown>[]).find(
    (a) => ["booked", "confirmed", "arrived"].includes(String(a.status ?? ""))
  );
  const unpaidBills = (bills as Record<string, unknown>[]).filter(
    (b) => !["paid", "waived"].includes(String(b.status ?? ""))
  );
  const totalOwing = unpaidBills.reduce((sum, b) => sum + Number(b.total_amount ?? 0), 0);

  return (
    <div style={s.section}>
      <h2 style={s.h2}>Welcome, {name}</h2>

      {/* Demographics strip */}
      {patient && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
            {[
              { label: "MRN", value: String(patient.mrn ?? "—") },
              { label: "Date of Birth", value: fmtDate(String(patient.date_of_birth ?? "")) },
              { label: "Blood Group", value: String(patient.blood_group ?? "—") },
              { label: "HMO", value: String(patient.hmo_provider ?? "None") },
              { label: "Phone", value: String(patient.phone ?? "—") },
              { label: "Gender", value: String(patient.gender ?? "—") },
            ].map(item => (
              <div key={item.label} style={{ background: "#fff", borderRadius: 10, padding: "10px 14px", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
                <p style={{ ...s.muted, marginTop: 0 }}>{item.label}</p>
                <p style={{ ...s.bold, marginTop: 2 }}>{item.value}</p>
              </div>
            ))}
          </div>

          {/* Allergies */}
          {Array.isArray(patient.allergies) && (patient.allergies as string[]).length > 0 && (
            <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 10, padding: "10px 14px", marginBottom: 16 }}>
              <p style={{ fontWeight: 700, fontSize: 13, color: "#dc2626", marginBottom: 4 }}>⚠️ Allergies</p>
              <p style={{ fontSize: 13, color: "#7f1d1d" }}>{(patient.allergies as string[]).join(" · ")}</p>
            </div>
          )}

          {/* Next of Kin */}
          {patient.next_of_kin_name && (
            <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 10, padding: "10px 14px", marginBottom: 16 }}>
              <p style={{ fontWeight: 700, fontSize: 13, color: "#15803d", marginBottom: 4 }}>👤 Next of Kin</p>
              <p style={{ fontSize: 13, color: "#166534" }}>{String(patient.next_of_kin_name)}</p>
              {patient.next_of_kin_phone && (
                <p style={{ fontSize: 13, color: "#166534" }}>{String(patient.next_of_kin_phone)}</p>
              )}
            </div>
          )}
        </>
      )}

      {loading ? (
        <div style={s.spinner}>Loading…</div>
      ) : (
        <>
          {/* Next appointment */}
          <div style={{ background: "#eff6ff", border: "1px solid #93c5fd", borderRadius: 12, padding: "14px 16px", marginBottom: 16 }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: "#1d4ed8", marginBottom: 6 }}>📅 NEXT APPOINTMENT</p>
            {nextAppt ? (
              <>
                <p style={s.bold}>{String(nextAppt.appointment_type ?? "Consultation")}</p>
                <p style={s.muted}>{fmtDate(String(nextAppt.appointment_date ?? ""))} · {String(nextAppt.department ?? "—")}</p>
                {nextAppt.doctor_name && <p style={s.muted}>Dr. {String(nextAppt.doctor_name)}</p>}
              </>
            ) : (
              <p style={{ ...s.muted, marginTop: 0 }}>No upcoming appointments</p>
            )}
          </div>

          {/* Outstanding balance */}
          {totalOwing > 0 && (
            <div style={{ background: "#fff7ed", border: "1px solid #fdba74", borderRadius: 12, padding: "14px 16px" }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: "#ea580c", marginBottom: 6 }}>💳 OUTSTANDING BALANCE</p>
              <p style={{ ...s.bold, fontSize: 22, color: "#9a3412" }}>₦{totalOwing.toLocaleString("en-NG")}</p>
              <p style={s.muted}>{unpaidBills.length} unpaid bill{unpaidBills.length !== 1 ? "s" : ""} — go to Billing tab to pay</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
