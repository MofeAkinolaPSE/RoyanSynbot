import { useEffect, useState } from "react";
import { portalApi } from "../api";
import { s } from "../styles";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
}

const INTERP_COLORS: Record<string, string> = {
  normal: "#22c55e",
  abnormal: "#f97316",
  critical: "#ef4444",
  inconclusive: "#94a3b8",
};

export default function Results() {
  const [results, setResults] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    portalApi.labResults()
      .then(r => setResults(r.results))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={s.spinner}>Loading…</div>;
  if (error) return <div style={s.error}>{error}</div>;

  return (
    <div style={s.section}>
      <h2 style={s.h2}>Lab Results</h2>
      {results.length === 0 ? (
        <p style={s.empty}>No lab results available yet.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(results as Record<string, unknown>[]).map((r, i) => {
            const interp = String(r.interpretation ?? "");
            const color = INTERP_COLORS[interp] ?? "#64748b";
            return (
              <div key={String(r.id ?? i)} style={s.row}>
                <div style={{ flex: 1 }}>
                  <p style={s.bold}>{String(r.test_name ?? "Test")}</p>
                  {/* result_summary is always set for resulted records (ETL + live) */}
                  {!!r.result_summary && (
                    <p style={{ fontSize: 14, color: "#0f172a", marginTop: 2 }}>
                      <strong>{String(r.result_summary)}</strong>
                    </p>
                  )}
                  {/* Fallback: flat result_value on live orders that lack a summary */}
                  {!r.result_summary && !!r.result_value && (
                    <p style={{ fontSize: 14, color: "#0f172a", marginTop: 2 }}>
                      Result: <strong>{String(r.result_value)}</strong>{r.result_unit ? ` ${r.result_unit}` : ""}
                    </p>
                  )}
                  {/* Multi-analyte JSONB breakdown (e.g. FBC with 8+ sub-fields) */}
                  {r.result_data && typeof r.result_data === "object" &&
                    Object.keys(r.result_data as object).filter(k => !["value", "unit"].includes(k)).length > 0 && (
                    <div style={{ marginTop: 6, paddingLeft: 8, borderLeft: "2px solid #e2e8f0" }}>
                      {Object.entries(r.result_data as Record<string, unknown>)
                        .filter(([k]) => !["value", "unit"].includes(k))
                        .map(([k, v]) => (
                          <p key={k} style={{ fontSize: 12, color: "#475569", margin: "1px 0" }}>
                            {k}: <strong>{String(v)}</strong>
                          </p>
                        ))}
                    </div>
                  )}
                  {!!r.reference_range && (
                    <p style={s.muted}>Reference: {String(r.reference_range)}</p>
                  )}
                  <p style={s.muted}>{fmtDate(String(r.resulted_at ?? r.updated_at ?? ""))}</p>
                </div>
                {interp && (
                  <span style={{ ...s.badge, backgroundColor: color + "22", color, border: `1px solid ${color}55`, textTransform: "capitalize" }}>
                    {interp}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
