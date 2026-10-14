import { useMemo } from "react";
import { ALERT_ROLES } from "@/components/AlertBanner";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  ArrowRight, AlertCircle, AlertTriangle, Activity, CheckCircle2, Clock, Stethoscope, Users2,
  FlaskConical, CalendarCheck, Pill, ScanLine, Boxes, Receipt, ShieldCheck, Wifi, Building2,
  LayoutGrid, HeartPulse,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/AuthProvider";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { canViewByRoles, getNavEntryByHref } from "@/lib/nav-access";
import { WORKSTATION_FEATURED, resolvePrimaryRole, type RoleKey } from "@/lib/workstation-config";
import { QuickAccessCard } from "@/components/workstation/QuickAccessCard";
import { MetricTile } from "@/components/workstation/MetricTile";
import { cn } from "@/lib/utils";

const OPS_VIEW_ROLES: RoleKey[] = ["admin", "management", "ops", "receptionist"];

export default function Workstation() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { roles } = useAuth();
  const primaryRole = resolvePrimaryRole(roles);

  // ── Realtime (unchanged from the previous Hospital Command page) ──────
  useRealtimeChannel("alerts_updates", () => {
    queryClient.invalidateQueries({ queryKey: ["dashboard-alerts"] });
  });
  useRealtimeChannel("encounter_updates", () => {
    queryClient.invalidateQueries({ queryKey: ["dashboard-hospital"] });
  });
  useRealtimeChannel("workflow_updates", (message: any) => {
    if (["batch_locked", "batch_approved"].includes(message?.event)) {
      queryClient.invalidateQueries({ queryKey: ["dashboard-alerts"] });
    }
  });

  // ── Tier 1 — universal "Hospital Pulse" (every role) ───────────────────
  const { data: hospitalData, isLoading: hospitalLoading } = useQuery({
    queryKey: ["dashboard-hospital"],
    queryFn: api.dashboard.hospitalStatus,
    refetchInterval: 30_000,
  });
  const { data: alertsData, isLoading: alertsLoading, isError: alertsIsError } = useQuery({
    queryKey: ["dashboard-alerts"],
    queryFn: () => api.dashboard.alerts(),
    enabled: roles.some((r) => ALERT_ROLES.includes(r)),   // the alert feed is for admin / management / finance / ops
  });

  const h = (hospitalData as any) ?? {};
  const patientsWaiting: number = h.patients_waiting ?? 0;
  // the same patients Queue & Flow shows: every visit not yet discharged, whatever day it started
  const onQueue: number = h.on_queue ?? patientsWaiting;
  const inServices: number = h.in_services ?? 0;
  const carriedOver: number = h.carried_over ?? 0;
  const activeConsultations: number = h.active_consultations ?? 0;
  const patientsSeen: number = h.patients_seen_today ?? 0;
  const avgWaitMin: number = h.avg_wait_minutes ?? 0;
  const clinical = h.clinical_today ?? {};
  const appointmentsToday: number = clinical.appointments_today ?? 0;
  const labOrdersPending: number = clinical.lab_orders_pending ?? 0;
  const prescriptionsPending: number = clinical.prescriptions_pending ?? 0;
  const queueByDept: { department: string; waiting: number; consulting: number; in_services?: number }[] =
    Array.isArray(h.queue_by_department) ? h.queue_by_department : [];
  const flowByHour: { hour: string; patients: number }[] =
    Array.isArray(h.flow_by_hour) ? h.flow_by_hour : [];

  const alertsValid = Array.isArray(alertsData);
  const alerts = alertsValid ? (alertsData as any[]) : [];
  const criticalAlerts = alerts.filter((a: any) => a.severity === "critical");

  const waitColour =
    avgWaitMin > 60 ? "text-destructive" :
    avgWaitMin > 30 ? "text-warning" :
    avgWaitMin > 0  ? "text-success" : "";

  // ── Tier 2 — role-specific metrics, each gated to fire only for its role ──
  // Leaders see the same composed figures as the Executive overview (one source, server-cached),
  // not a separate "health score" verdict.
  const isLeader = roles.some((r) => r === "admin" || r === "management" || r === "finance");
  const execQ = useQuery({
    queryKey: ["executive-overview"],
    queryFn: () => api.dashboard.executive(),
    enabled: isLeader,
    staleTime: 120_000,
  });
  const labQ = useQuery({
    queryKey: ["workstation-lab"], queryFn: api.hospital.lab.stats, enabled: primaryRole === "lab",
  });
  const radiologyQ = useQuery({
    queryKey: ["workstation-radiology"], queryFn: api.hospital.radiology.stats, enabled: primaryRole === "radiology",
  });
  const pharmacyQ = useQuery({
    queryKey: ["workstation-pharmacy"], queryFn: api.hospital.pharmacy.stats, enabled: primaryRole === "pharmacist",
  });
  const pharmacyInvQ = useQuery({
    queryKey: ["workstation-pharmacy-inv"], queryFn: api.hospital.pharmacy.inventory.summary, enabled: primaryRole === "pharmacist",
  });
  const billingQ = useQuery({
    queryKey: ["workstation-billing"], queryFn: api.hospital.billing.getStats, enabled: primaryRole === "finance",
  });
  const hrQ = useQuery({
    queryKey: ["workstation-hr"], queryFn: api.hr.stats, enabled: primaryRole === "hr",
  });
  const presenceQ = useQuery({
    queryKey: ["workstation-presence"], queryFn: api.presence.summary,
    enabled: primaryRole === "hr" || primaryRole === "ops",
  });
  const qualityQ = useQuery({
    queryKey: ["workstation-quality"], queryFn: api.quality.stats, enabled: primaryRole === "quality_assurance",
  });
  const infectionQ = useQuery({
    queryKey: ["workstation-infection"], queryFn: api.quality.infectionStats, enabled: primaryRole === "quality_assurance",
  });
  const facilityQ = useQuery({
    queryKey: ["workstation-facility"], queryFn: api.facility.stats, enabled: primaryRole === "ops",
  });

  // ── Quick-access cards — union of every held role's featured pages,
  // fail-closed intersected with the real nav-items role check so a stale
  // curation entry can only hide a card, never grant one. ──────────────────
  const quickAccessHrefs = useMemo(() => {
    const set = new Set<string>();
    for (const role of roles) {
      const featured = WORKSTATION_FEATURED[role as RoleKey];
      if (featured) for (const href of featured) set.add(href);
    }
    return Array.from(set).filter((href) => {
      const entry = getNavEntryByHref(href);
      return !!entry && canViewByRoles(roles, entry.roles);
    });
  }, [roles]);

  const showOpsView = primaryRole ? OPS_VIEW_ROLES.includes(primaryRole) : false;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={motionTransitions.standard}
      className="flex flex-col gap-5"
    >
      {/* ── Critical Alert Banner ── */}
      {criticalAlerts.length > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-medium">
            {criticalAlerts[0].title}: {criticalAlerts[0].message}
          </span>
        </div>
      )}

      {/* ── Page Header ── */}
      <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">ROY Workstation</h1>
          <p className="text-sm text-muted-foreground">Your quick access, and what's happening across the hospital right now</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { void queryClient.invalidateQueries(); }}>
          Refresh
        </Button>
      </div>

      {/* ── Tier 1: Hospital Pulse (universal) ── */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card className="cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 border-l-4 border-l-primary bg-gradient-to-br from-primary/5 to-card"
          role="button"
          tabIndex={0}
          onClick={() => navigate("/hospital/queue?status=waiting")}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate("/hospital/queue?status=waiting"); } }}>
          <CardHeader className="pb-2 pt-4">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">On the queue</CardDescription>
              <Users2 className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold tabular-nums">
              {hospitalLoading ? <Skeleton className="h-8 w-16" /> : onQueue}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">{patientsWaiting} before the doctor · {inServices} at lab, Scancare, pharmacy or cashier</div>
          </CardContent>
        </Card>

        <Card className="cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 border-l-4 border-l-accent bg-gradient-to-br from-accent/5 to-card"
          role="button"
          tabIndex={0}
          onClick={() => navigate("/hospital/queue?status=waiting&view=waits")}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate("/hospital/queue?status=waiting&view=waits"); } }}>
          <CardHeader className="pb-2 pt-4">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">Avg Wait Time</CardDescription>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent className="pb-4">
            <div className={cn("text-3xl font-bold tabular-nums", !hospitalLoading && waitColour)}>
              {hospitalLoading ? <Skeleton className="h-8 w-20" /> : avgWaitMin > 0 ? `${avgWaitMin}m` : <span className="text-base text-muted-foreground">—</span>}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">Registration → triage today</div>
          </CardContent>
        </Card>

        <Card className="cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 border-l-4 border-l-success bg-gradient-to-br from-success/5 to-card"
          role="button"
          tabIndex={0}
          onClick={() => navigate("/hospital/queue?status=discharged")}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate("/hospital/queue?status=discharged"); } }}>
          <CardHeader className="pb-2 pt-4">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">Seen Today</CardDescription>
              <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold tabular-nums text-success">
              {hospitalLoading ? <Skeleton className="h-8 w-16" /> : patientsSeen}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">Discharged today</div>
          </CardContent>
        </Card>

        <Card className="cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 border-l-4 border-l-secondary bg-gradient-to-br from-secondary/5 to-card"
          role="button"
          tabIndex={0}
          onClick={() => navigate("/hospital/queue?status=consulting")}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate("/hospital/queue?status=consulting"); } }}>
          <CardHeader className="pb-2 pt-4">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">Consultations</CardDescription>
              <Stethoscope className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold tabular-nums">
              {hospitalLoading ? <Skeleton className="h-8 w-16" /> : activeConsultations}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">Doctors with patients now</div>
          </CardContent>
        </Card>
      </div>

      {/* ── Tier 2a: Quick Access ── */}
      {quickAccessHrefs.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-muted-foreground flex items-center gap-1.5">
            <LayoutGrid className="h-3.5 w-3.5" /> Quick Access
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {quickAccessHrefs.map((href) => <QuickAccessCard key={href} href={href} />)}
          </div>
        </div>
      )}

      {/* ── Tier 2b: role-specific metrics ── */}
      {(primaryRole === "doctor" || primaryRole === "nurse") && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/15 text-primary">
                {primaryRole === "doctor" ? <Stethoscope className="h-5 w-5" /> : <HeartPulse className="h-5 w-5" />}
              </div>
              <div>
                <p className="text-sm font-semibold">Your full {primaryRole === "doctor" ? "clinical" : "ward"} workspace lives on {primaryRole === "doctor" ? "My Dashboard" : "Nurse Dashboard"}</p>
                <p className="text-xs text-muted-foreground">Live queues, vitals, and consultation tools — this page stays a quick-access hub.</p>
              </div>
            </div>
            <Button size="sm" className="gap-1.5 shrink-0" onClick={() => navigate(primaryRole === "doctor" ? "/hospital/doctor" : "/hospital/nurse")}>
              Open <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardContent>
        </Card>
      )}

      {isLeader && execQ.data && (() => {
        const x: any = execQ.data;
        const naira = (v: any) => { const n = Number(v ?? 0); return Math.abs(n) >= 1e6 ? `₦${(n / 1e6).toFixed(1)}M` : `₦${Math.round(n).toLocaleString()}`; };
        const asOf = (v?: string) => (v ? new Date(v.slice(0, 10) + "T12:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");
        const top = (x.attention ?? []).slice(0, 4);
        return (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricTile label="Billed, 12 months" value={naira(x.billing?.billed_12m)} icon={Receipt} loading={execQ.isLoading}
                          sub={x.billing?.as_of ? `to ${asOf(x.billing.as_of)} · ${x.billing.hmo_share_pct ?? "—"}% HMO` : undefined} href="/executive" />
              <MetricTile label="HMOs & corporates owe" value={naira(x.debtors?.total)} icon={Building2} loading={execQ.isLoading}
                          sub={x.debtors?.over_90_pct != null ? `${x.debtors.over_90_pct}% over 90 days` : undefined} href="/finance/ar" />
              <MetricTile label="Cash & bank" value={naira(x.finance?.cash)} icon={Receipt} loading={execQ.isLoading}
                          sub={x.finance?.cash_on ? `at ${asOf(x.finance.cash_on)}` : undefined} href="/finance/books/banking" />
              <MetricTile label="Pharmacy stock (cost)" value={naira(x.finance?.stock?.in_books ? x.finance.stock.books_value : x.finance?.stock?.shelf_value)} icon={Boxes}
                          loading={execQ.isLoading} sub={x.finance?.stock?.expired_value ? `${naira(x.finance.stock.expired_value)} expired` : undefined} href="/finance/books/stock" />
            </div>
            {top.length > 0 && (
              <Card className="border-warning/40 bg-warning/5">
                <CardContent className="p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-warning">
                      <AlertCircle className="h-3.5 w-3.5" /> Needs attention
                    </p>
                    <Link to="/executive" className="text-xs text-primary hover:underline">All {(x.attention ?? []).length} on the Executive overview</Link>
                  </div>
                  <ul className="space-y-1">
                    {top.map((a: any, i: number) => (
                      <li key={i}>
                        <Link to={a.link} className="flex items-start gap-2 rounded px-1 py-0.5 text-sm hover:bg-warning/10">
                          <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", a.level === "critical" ? "bg-destructive" : a.level === "action" ? "bg-warning" : "bg-sky-500")} />
                          <span>{a.title}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </div>
        );
      })()}

      {primaryRole === "lab" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="Pending" value={labQ.data?.pending} icon={FlaskConical} loading={labQ.isLoading} color="text-yellow-500" href="/hospital/lab" />
          <MetricTile label="Processing" value={labQ.data?.processing} icon={Activity} loading={labQ.isLoading} color="text-purple-500" href="/hospital/lab" />
          <MetricTile label="STAT Overdue" value={labQ.data?.stat_overdue} icon={AlertTriangle} loading={labQ.isLoading} color="text-red-500" href="/hospital/lab" />
          <MetricTile label="Urgent Overdue" value={labQ.data?.urgent_overdue} icon={AlertTriangle} loading={labQ.isLoading} color="text-orange-500" href="/hospital/lab" />
        </div>
      )}

      {primaryRole === "radiology" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="Pending" value={radiologyQ.data?.pending} icon={ScanLine} loading={radiologyQ.isLoading} color="text-yellow-500" href="/hospital/radiology" />
          <MetricTile label="In Progress" value={radiologyQ.data?.in_progress} icon={Activity} loading={radiologyQ.isLoading} color="text-purple-500" href="/hospital/radiology" />
          <MetricTile label="STAT Pending" value={radiologyQ.data?.stat_pending} icon={AlertTriangle} loading={radiologyQ.isLoading} color="text-red-500" href="/hospital/radiology" />
          <MetricTile label="Reported" value={radiologyQ.data?.reported} icon={CheckCircle2} loading={radiologyQ.isLoading} color="text-green-500" href="/hospital/radiology" />
        </div>
      )}

      {primaryRole === "pharmacist" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="Active Prescriptions" value={pharmacyQ.data?.active} icon={Pill} loading={pharmacyQ.isLoading} href="/hospital/pharmacy" />
          <MetricTile label="Total Rx" value={pharmacyQ.data?.total} icon={Pill} loading={pharmacyQ.isLoading} href="/hospital/pharmacy" />
          <MetricTile label="Critical Stock" value={pharmacyInvQ.data?.critical_count ?? pharmacyInvQ.data?.tier_counts?.CRITICAL} icon={Boxes} loading={pharmacyInvQ.isLoading} color="text-red-500" href="/hospital/pharmacy/inventory" />
          <MetricTile label="Expiring Soon" value={pharmacyInvQ.data?.expiring_soon_count} icon={AlertTriangle} loading={pharmacyInvQ.isLoading} color="text-orange-500" href="/hospital/pharmacy/inventory" />
        </div>
      )}

      {primaryRole === "finance" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="Pending Bills" value={billingQ.data?.pending_count} icon={Receipt} loading={billingQ.isLoading} color="text-yellow-500" href="/hospital/billing" />
          <MetricTile label="Disputed" value={billingQ.data?.disputed_count} icon={AlertTriangle} loading={billingQ.isLoading} color="text-red-500" href="/hospital/billing" />
          <MetricTile label="HMO Pending" value={billingQ.data?.hmo_pending_count} icon={Building2} loading={billingQ.isLoading} href="/hospital/hmo" />
          <MetricTile label="Total Outstanding" value={billingQ.data?.total_outstanding != null ? `₦${Number(billingQ.data.total_outstanding).toLocaleString()}` : undefined} icon={Receipt} loading={billingQ.isLoading} color="text-red-500" href="/hospital/billing" />
        </div>
      )}

      {primaryRole === "hr" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="On Duty Today" value={hrQ.data?.shifts_today?.on_duty} icon={Users2} loading={hrQ.isLoading} href="/hr" />
          <MetricTile label="Online Now" value={presenceQ.data?.count} icon={Wifi} loading={presenceQ.isLoading} color="text-green-500" href="/workspace?tab=team" />
          <MetricTile label="Pending Leave" value={hrQ.data?.leave?.pending} icon={CalendarCheck} loading={hrQ.isLoading} color="text-yellow-500" href="/hr" />
          <MetricTile label="Pending Payroll" value={hrQ.data?.payroll?.pending_amount != null ? `₦${Number(hrQ.data.payroll.pending_amount).toLocaleString()}` : undefined} icon={Receipt} loading={hrQ.isLoading} href="/hr" />
        </div>
      )}

      {primaryRole === "quality_assurance" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="Open Incidents" value={qualityQ.data?.incidents?.open} icon={ShieldCheck} loading={qualityQ.isLoading} color="text-orange-500" href="/hospital/quality" />
          <MetricTile label="Total Incidents" value={qualityQ.data?.incidents?.total} icon={AlertCircle} loading={qualityQ.isLoading} href="/hospital/quality" />
          <MetricTile label="HEFAMAA Avg Score" value={qualityQ.data?.hefamaa?.avg_score} icon={CheckCircle2} loading={qualityQ.isLoading} color="text-green-500" href="/hospital/quality" />
          <MetricTile label="HAI Cases" value={infectionQ.data?.hai_count} icon={AlertTriangle} loading={infectionQ.isLoading} color="text-red-500" href="/hospital/quality" />
        </div>
      )}

      {primaryRole === "ops" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="Online Now" value={presenceQ.data?.count} icon={Wifi} loading={presenceQ.isLoading} color="text-green-500" href="/workspace?tab=team" />
          <MetricTile label="Audits Overdue" value={facilityQ.data?.audits?.overdue} icon={AlertTriangle} loading={facilityQ.isLoading} color="text-orange-500" href="/hospital/audits-maintenance" />
          <MetricTile label="Maintenance Overdue" value={facilityQ.data?.maintenance?.overdue} icon={AlertTriangle} loading={facilityQ.isLoading} color="text-orange-500" href="/hospital/audits-maintenance" />
          <MetricTile label="Total Maintenance" value={facilityQ.data?.maintenance?.total} icon={Activity} loading={facilityQ.isLoading} href="/hospital/audits-maintenance" />
        </div>
      )}

      {/* ── Tier 2c: hospital-wide flow — admin/management/ops/receptionist only ── */}
      {showOpsView && (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <Card className="lg:col-span-8">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold">Patient Flow Today</CardTitle>
                    <CardDescription className="text-xs">New encounters registered by hour</CardDescription>
                  </div>
                  <Link to="/hospital/queue">
                    <Button variant="ghost" size="sm" className="text-xs">Live Queue <ArrowRight className="ml-1 h-3 w-3" /></Button>
                  </Link>
                </div>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="h-[300px]">
                  {hospitalLoading ? (
                    <div className="flex h-full flex-col gap-3 p-4">
                      <Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-4/6" /><Skeleton className="h-4 w-full" />
                    </div>
                  ) : flowByHour.some((r) => r.patients > 0) ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={flowByHour} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
                        <XAxis dataKey="hour" stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} />
                        <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={28} />
                        <Tooltip formatter={(v: number) => [v, "Patients"]} contentStyle={{ fontSize: "12px", borderRadius: "8px" }} />
                        <Bar dataKey="patients" name="Patients" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} barSize={18} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
                      <Activity className="h-6 w-6 opacity-40" />
                      <span>No new patients registered today yet.</span>
                      {onQueue > 0 && <span className="text-xs">{onQueue} still on the queue{carriedOver ? ` (${carriedOver} from earlier days)` : ""} - see the live queue.</span>}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card className="lg:col-span-4">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold">Queue by Department</CardTitle>
                    <CardDescription className="text-xs">Active (non-discharged) patients</CardDescription>
                  </div>
                  <Link to="/hospital/queue">
                    <Button variant="ghost" size="sm" className="text-xs">All <ArrowRight className="ml-1 h-3 w-3" /></Button>
                  </Link>
                </div>
              </CardHeader>
              <CardContent className="pb-4">
                {hospitalLoading ? (
                  <div className="space-y-3">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}</div>
                ) : queueByDept.length > 0 ? (
                  <div className="space-y-2">
                    {queueByDept.slice(0, 7).map((d) => (
                      <div key={d.department} className="flex items-center justify-between rounded-lg border bg-card px-3 py-2">
                        <span className="text-sm font-medium truncate max-w-[130px]">{d.department}</span>
                        <div className="flex items-center gap-2 text-xs">
                          {d.waiting > 0 && <Badge variant="outline" className="border-warning/60 text-warning text-xs px-1.5">{d.waiting} waiting</Badge>}
                          {d.consulting > 0 && <Badge variant="outline" className="border-primary/60 text-primary text-xs px-1.5">{d.consulting} active</Badge>}
                          {(d.in_services ?? 0) > 0 && <Badge variant="outline" className="text-xs px-1.5">{d.in_services} at services</Badge>}
                          {d.waiting === 0 && d.consulting === 0 && !d.in_services && <Badge variant="outline" className="border-success/60 text-success text-xs px-1.5">Clear</Badge>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                    <CheckCircle2 className="mb-2 h-7 w-7 text-success/70" />
                    <p className="text-sm">All queues clear</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <Card className="lg:col-span-8 border-border/50 bg-muted/20">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base font-semibold">
                  <Activity className="h-4 w-4 text-primary" /> System Notifications
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="max-h-[240px] space-y-2 overflow-y-auto pr-1">
                  {alertsLoading ? (
                    <div className="space-y-2"><Skeleton className="h-14 w-full rounded-xl" /><Skeleton className="h-14 w-full rounded-xl" /></div>
                  ) : !alertsValid ? (
                    <div className="py-4 text-sm text-muted-foreground">Alerts temporarily unavailable.</div>
                  ) : alerts.length > 0 ? (
                    alerts.map((alert: any, idx: number) => (
                      <div key={idx} className={cn("flex items-start gap-3 rounded-xl border p-3",
                        alert.severity === "critical" ? "border-l-4 border-l-destructive bg-destructive/5 border-destructive/30" : "border-l-4 border-l-warning bg-warning/5 border-border/50")}>
                        <AlertCircle className={cn("mt-0.5 h-4 w-4 shrink-0", alert.severity === "critical" ? "text-destructive" : "text-warning")} />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium leading-tight">{alert.title}</p>
                          <p className="text-xs text-muted-foreground">{alert.message}</p>
                          <p className="mt-0.5 text-xs text-muted-foreground/60">{new Date(alert.created_at).toLocaleTimeString()}</p>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <CheckCircle2 className="mb-2 h-8 w-8 text-success/70" />
                      <p className="text-sm">No new system alerts</p>
                    </div>
                  )}
                </div>
                {alertsIsError && <p className="mt-2 text-xs text-muted-foreground/70">Alerts service temporarily unavailable — refreshing automatically.</p>}
              </CardContent>
            </Card>

            <Card className="lg:col-span-4">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold">Clinical Summary</CardTitle>
                <CardDescription className="text-xs">Today's pending clinical activity</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 pb-4">
                <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2.5">
                  <div className="flex items-center gap-2"><CalendarCheck className="h-4 w-4 text-primary" /><span className="text-sm">Appointments</span></div>
                  <span className="text-sm font-bold tabular-nums">{hospitalLoading ? <Skeleton className="h-4 w-8 inline-block" /> : appointmentsToday}</span>
                </div>
                <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2.5">
                  <div className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-accent" /><span className="text-sm">Lab Orders Pending</span></div>
                  <span className={cn("text-sm font-bold tabular-nums", labOrdersPending > 10 ? "text-warning" : "")}>{hospitalLoading ? <Skeleton className="h-4 w-8 inline-block" /> : labOrdersPending}</span>
                </div>
                <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2.5">
                  <div className="flex items-center gap-2"><Pill className="h-4 w-4 text-secondary" /><span className="text-sm">Prescriptions Pending</span></div>
                  <span className={cn("text-sm font-bold tabular-nums", prescriptionsPending > 15 ? "text-warning" : "")}>{hospitalLoading ? <Skeleton className="h-4 w-8 inline-block" /> : prescriptionsPending}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </motion.div>
  );
}
