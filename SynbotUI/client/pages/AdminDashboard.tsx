import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  LayoutDashboard, Users, Activity, DollarSign, AlertTriangle,
  RefreshCw, ShieldCheck, FlaskConical,
} from "lucide-react";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { api } from "@/lib/api-client";
import { AlertBanner } from "@/components/AlertBanner";
import { cn } from "@/lib/utils";

function fmtCurrency(n: number) {
  return `₦${Number(n || 0).toLocaleString("en-NG")}`;
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function AdminDashboard() {
  const today = new Date().toLocaleDateString("en-NG", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data: hospitalStatus, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ["admin-hospital-status"],
    queryFn: api.dashboard.hospitalStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const { data: alertsData, refetch: refetchAlerts } = useQuery({
    queryKey: ["admin-alerts"],
    queryFn: api.dashboard.alerts,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const { data: qualityStats } = useQuery({
    queryKey: ["admin-quality-stats"],
    queryFn: api.quality.stats,
    staleTime: 300_000,
  });

  const { data: shiftsData } = useQuery({
    queryKey: ["admin-shifts-today", new Date().toISOString().split("T")[0]],
    queryFn: () => api.hr.listShifts({ shift_date: new Date().toISOString().split("T")[0] }),
    staleTime: 120_000,
  });

  const { data: claimsData } = useQuery({
    queryKey: ["admin-claims-pending"],
    queryFn: () => api.hospital.billing.listClaims({ status: "submitted" }),
    staleTime: 120_000,
  });

  const { data: labTATData } = useQuery({
    queryKey: ["admin-lab-tat"],
    queryFn: api.hospital.lab.turnaround,
    staleTime: 300_000,
  });

  // ── Derived values ─────────────────────────────────────────────────────────
  const hs = hospitalStatus ?? {};
  const clinicalToday    = hs.clinical_today ?? {};
  const patientsWaiting  = hs.patients_waiting ?? hs.queue_count ?? 0;
  const avgWait          = hs.avg_wait_minutes ?? 0;
  const labPending       = clinicalToday.lab_orders_pending ?? hs.lab_orders_pending ?? 0;
  const rxPending        = clinicalToday.prescriptions_pending ?? hs.prescriptions_pending ?? 0;

  const queueChart = useMemo(() => {
    const raw = hs.queue_by_department ?? [];
    if (Array.isArray(raw)) {
      return raw.map((d: any) => ({
        dept: (d.department ?? "").replace(" & ", "&").slice(0, 14),
        count: Number(d.waiting ?? 0) + Number(d.consulting ?? 0),
      }));
    }
    return Object.entries(raw).map(([dept, count]) => ({ dept: dept.replace(" & ", "&").slice(0, 14), count: Number(count) }));
  }, [hs]);

  const incidentStats = qualityStats?.incidents ?? { total: 0, open: 0, by_severity: {} };
  const hefamaaScore  = qualityStats?.hefamaa?.avg_score ?? 0;

  const shiftsToday: any[] = Array.isArray(shiftsData?.shifts) ? shiftsData.shifts : [];
  const pendingClaims: any[] = Array.isArray(claimsData?.claims) ? claimsData.claims : Array.isArray(claimsData) ? claimsData : [];
  const tatRecords: any[] = Array.isArray(labTATData?.records) ? labTATData.records : [];

  const alerts: any[] = Array.isArray(alertsData) ? alertsData : [];
  const criticalAlerts = alerts.filter((a: any) => ["critical", "high"].includes(a.severity));

  function doRefresh() {
    void refetchStatus();
    void refetchAlerts();
  }

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <LayoutDashboard className="h-6 w-6 text-blue-600" /> Admin Dashboard
          </h1>
          <p className="text-sm text-muted-foreground">{today}</p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={doRefresh} disabled={statusLoading}>
          <RefreshCw className={cn("h-3.5 w-3.5", statusLoading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* Row 1 — Hospital Census */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { label: "Queue Waiting (Today)",  value: patientsWaiting, icon: Users,       color: "text-blue-700",   bg: "bg-blue-50" },
          { label: "Lab Pending",    value: labPending,      icon: FlaskConical, color: "text-orange-700", bg: "bg-orange-50" },
          { label: "Rx Pending",     value: rxPending,       icon: Activity,     color: "text-purple-700", bg: "bg-purple-50" },
          { label: "Avg Wait (min)", value: `${avgWait}m`,   icon: Activity,     color: avgWait > 60 ? "text-red-700" : "text-green-700", bg: avgWait > 60 ? "bg-red-50" : "bg-green-50" },
        ].map(k => (
          <Card key={k.label} className={cn("border-border/60", k.bg)}>
            <CardContent className="pt-4 pb-3">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{k.label}</p>
                  <p className={cn("text-2xl font-bold mt-0.5", k.color)}>{k.value}</p>
                </div>
                <k.icon className={cn("w-5 h-5 mt-1 shrink-0", k.color)} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Row 2 — Claims + Quality Strip */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <Card className="bg-yellow-50 border-yellow-200">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Pending HMO Claims</p>
            <p className="text-2xl font-bold text-yellow-700 mt-0.5">{pendingClaims.length}</p>
          </CardContent>
        </Card>
        <Card className={cn("border-border/60", incidentStats.open > 0 ? "bg-red-50" : "bg-green-50")}>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Open Incidents</p>
            <p className={cn("text-2xl font-bold mt-0.5", incidentStats.open > 0 ? "text-red-700" : "text-green-700")}>{incidentStats.open}</p>
          </CardContent>
        </Card>
        <Card className={cn("border-border/60", hefamaaScore >= 80 ? "bg-green-50" : "bg-orange-50")}>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">HEFAMAA Score</p>
            <p className={cn("text-2xl font-bold mt-0.5", hefamaaScore >= 80 ? "text-green-700" : "text-orange-700")}>{hefamaaScore}%</p>
          </CardContent>
        </Card>
      </div>

      {/* Row 3 — Queue Chart + Quality Detail */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Activity className="h-4 w-4 text-blue-500" /> Department Queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            {queueChart.length === 0 ? (
              <p className="text-sm text-center text-muted-foreground py-6">No queue data</p>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={queueChart} margin={{ top: 5, right: 10, left: -20, bottom: 20 }}>
                  <XAxis dataKey="dept" tick={{ fontSize: 10 }} angle={-35} textAnchor="end" />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {queueChart.map((_, i) => <Cell key={i} fill={i % 2 === 0 ? "#3b82f6" : "#0ea5e9"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-green-500" /> Quality & Safety
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm"><span className="text-muted-foreground">Total Incidents</span><strong>{incidentStats.total}</strong></div>
            <div className="flex justify-between text-sm"><span className="text-muted-foreground">Open Incidents</span><strong className={incidentStats.open > 0 ? "text-red-600" : "text-green-600"}>{incidentStats.open}</strong></div>
            {Object.entries(incidentStats.by_severity ?? {}).map(([sev, count]) => (
              <div key={sev} className="flex justify-between text-xs">
                <span className="capitalize text-muted-foreground">{sev.replace("_"," ")}</span>
                <span>{count as number}</span>
              </div>
            ))}
            <div className="flex justify-between text-sm border-t border-border/60 pt-2">
              <span className="text-muted-foreground">HEFAMAA Avg Score</span>
              <strong className={hefamaaScore >= 80 ? "text-green-600" : "text-orange-600"}>{hefamaaScore}%</strong>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Row 4 — Staff + Lab TAT + Critical Alerts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-500" /> Staff On Duty Today
            </CardTitle>
          </CardHeader>
          <CardContent>
            {shiftsToday.length === 0 ? (
              <p className="text-sm text-center text-muted-foreground py-4">No shifts today</p>
            ) : (
              <div className="space-y-1.5">
                {Object.entries(
                  shiftsToday.reduce((acc: Record<string, number>, s: any) => {
                    const dept = s.department ?? "General";
                    acc[dept] = (acc[dept] ?? 0) + 1;
                    return acc;
                  }, {})
                ).map(([dept, count]) => (
                  <div key={dept} className="flex justify-between text-xs">
                    <span className="text-muted-foreground">{dept}</span>
                    <strong>{count}</strong>
                  </div>
                ))}
                <div className="border-t border-border/60 pt-1.5 flex justify-between text-sm font-semibold">
                  <span>Total</span><span>{shiftsToday.length}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-purple-500" /> Lab TAT
            </CardTitle>
          </CardHeader>
          <CardContent>
            {tatRecords.length === 0 ? (
              <p className="text-sm text-center text-muted-foreground py-4">No TAT data</p>
            ) : (
              <div className="space-y-1.5">
                {tatRecords.slice(0, 6).map((r: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs">
                    <span className="text-muted-foreground truncate mr-2">{r.test_name ?? "—"}</span>
                    <span className="shrink-0 font-medium">
                      {r.turnaround_minutes != null ? (r.turnaround_minutes < 60 ? `${Math.round(r.turnaround_minutes)}m` : `${(r.turnaround_minutes/60).toFixed(1)}h`) : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className={cn("h-4 w-4", criticalAlerts.length > 0 ? "text-red-500" : "text-muted-foreground")} />
              System Alerts
              {criticalAlerts.length > 0 && (
                <span className="ml-auto rounded-full bg-red-100 text-red-700 text-[10px] font-semibold px-2 py-0.5">{criticalAlerts.length}</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {criticalAlerts.length === 0 ? (
              <p className="text-sm text-center text-muted-foreground py-4">No critical alerts</p>
            ) : (
              <div className="space-y-2">
                {criticalAlerts.slice(0, 5).map((a: any, i: number) => (
                  <div key={i} className="rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                    <p className="text-xs font-medium text-red-800">{a.title ?? a.type ?? "Alert"}</p>
                    <p className="text-[10px] text-red-600 mt-0.5">{a.message ?? a.detail ?? ""}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Row 5 — Pending HMO Claims */}
      {pendingClaims.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-yellow-500" /> Pending HMO Claims
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    {["Claim #","Patient","HMO","Amount","Submitted","Status"].map(h => (
                      <TableHead key={h} className="text-xs">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pendingClaims.slice(0, 10).map((c: any) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-mono text-xs">#{c.id}</TableCell>
                      <TableCell className="text-sm">{c.patient_id ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{c.hmo_provider ?? "—"}</TableCell>
                      <TableCell className="text-sm font-medium">{fmtCurrency(c.claim_amount)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {c.submitted_at ? new Date(c.submitted_at).toLocaleDateString("en-NG") : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] capitalize bg-yellow-50 text-yellow-700 border-yellow-300">{c.status}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Row 6 — Staff Registrations & Role Assignment callout */}
      <Card>
        <CardContent className="flex items-center justify-between gap-4 py-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <ShieldCheck className="h-4 w-4 text-blue-500" />
            Pending staff registrations and role assignment now live under Admin → Staff Registrations.
          </div>
          <Button asChild size="sm" variant="outline">
            <a href="#/admin/registrations">Open Staff Registrations</a>
          </Button>
        </CardContent>
      </Card>
    </motion.div>
  );
}
