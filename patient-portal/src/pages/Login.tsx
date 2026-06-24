import { useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

interface Props {
  onLogin: (token: string, patient: Record<string, unknown>) => void;
}

export default function Login({ onLogin }: Props) {
  const [mrn, setMrn] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await portalApi.login(mrn.trim(), phone.trim());
      sessionStorage.setItem("portal_token", res.token);
      onLogin(res.token, res.patient);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed. Check your MRN and phone number.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.center}>
      <div style={s.card}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div style={s.logo}>R</div>
          <h1 style={s.h1}>Royan Hospital</h1>
          <p style={s.sub}>Patient Portal</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label style={s.label}>Hospital Number (MRN)</label>
            <input
              style={s.input}
              value={mrn}
              onChange={e => setMrn(e.target.value)}
              placeholder="e.g. RYN-00123"
              required
              autoComplete="username"
            />
          </div>
          <div>
            <label style={s.label}>Phone Number</label>
            <input
              style={s.input}
              value={phone}
              onChange={e => setPhone(e.target.value)}
              placeholder="+234 800 000 0000"
              required
              autoComplete="tel"
            />
          </div>
          {error && <p style={s.error}>{error}</p>}
          <button type="submit" style={{ ...s.btn, opacity: loading ? 0.7 : 1 }} disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>

        <p style={{ textAlign: "center", fontSize: 12, color: "#64748b", marginTop: 20 }}>
          Use the MRN on your hospital card and the phone number registered at reception.
        </p>
      </div>
    </div>
  );
}
