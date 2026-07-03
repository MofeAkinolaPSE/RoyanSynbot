import { Link } from "react-router-dom";
import {
  ArrowRight,
  AlertCircle,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Stethoscope,
  Users2,
  FlaskConical,
  CalendarCheck,
  Pill,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";


const Dashboard = () => {
  const queryClient = useQueryClient();

  // â”€â”€ Realtime subscriptions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useRealtimeChannel("alerts_updates", () => {
    queryClient.invalidateQueries({ queryKey: ["dashboard-alerts"] });
  });
  useRealtimeChannel("encounter_updates", () => {
    queryClient.invalidateQueries({ queryKey: ["dashboard-hospital"] });
  });
  useRealtimeChannel("workflow_updates", (message: any) => {
    const evt = message?.event;
    if (["batch_locked", "batch_approved"].includes(evt)) {
      queryClient.invalidateQueries({ queryKey: ["dashboard-alerts"] });
    }
  });

  // â”€â”€ Queries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const { data: hospitalData, isLoading: hospitalLoading } = useQuery({
    queryKey: ["dashboard-hospital"],
    queryFn: api.dashboard.hospitalStatus,
    refetchInterval: 30_000,
  });

  const { data: alertsData, isLoading: alertsLoading, isError: alertsIsError } = useQuery({
    queryKey: ["dashboard-alerts"],
    queryFn: () => api.dashboard.alerts(),
  });

  // â”€â”€ Derived values â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const h = (hospitalData as any) ?? {};
  const patientsWaiting:      number = h.patients_waiting       ?? 0;
  const activeConsultations:  number = h.active_consultations   ?? 0;
  const patientsSeen:         number = h.patients_seen_today    ?? 0;
  const avgWaitMin:           number = h.avg_wait_minutes       ?? 0;
  const clinical                     = h.clinical_today         ?? {};
  const appointmentsToday:    number = clinical.appointments_today    ?? 0;
  const labOrdersPending:     number = clinical.lab_orders_pending    ?? 0;
  const prescriptionsPending: number = clinical.prescriptions_pending ?? 0;

  const queueByDept: { department: string; waiting: number; consulting: number }[] =
    Array.isArray(h.queue_by_department) ? h.queue_by_department : [];

  const flowByHour: { hour: string; patients: number }[] =
    Array.isArray(h.flow_by_hour) ? h.flow_by_hour : [];

  const alertsValid = Array.isArray(alertsData);
  const alerts = alertsValid ? (alertsData as any[]) : [];
  const criticalAlerts = alerts.filter((a: any) => a.severity === "critical");

  const waitColour =
    avgWaitMin > 60 ? "text-destructive" :
    avgWaitMin > 30 ? "text-warning" :
    avgWaitMin > 0  ? "text-success" :
    "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={motionTransitions.standard}
      className="flex flex-col gap-5"
    >
      {/* â”€â”€ Critical Alert Banner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {criticalAlerts.length > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-medium">
            {criticalAlerts[0].title}: {criticalAlerts[0].message}
          </span>
        </div>
      )}

      {/* â”€â”€ Page Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Hospital Command Center</h1>
          <p className="text-sm text-muted-foreground">Live patient flow &amp; clinical activity</p>
        </div>
        <div className="flex gap-2">
          <Link to="/executive">
            <Button variant="default" size="sm">
              <Activity className="mr-2 h-4 w-4" />
              Executive Briefing
            </Button>
          </Link>
          <Button variant="outline" size="sm" onClick={() => { void queryClient.invalidateQueries(); }}>
            Refresh
          </Button>
        </div>
      </div>

      {/* â”€â”€ Hospital KPI Cards â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* Patients Waiting */}
        <Card className="border-l-4 border-l-primary bg-gradient-to-br from-primary/5 to-card">
          <CardHeader className="pb-2 pt-4">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">Patients Waiting</CardDescription>
              <Users2 className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold tabular-nums">
              {hospitalLoading ? <Skeleton className="h-8 w-16" /> : patientsWaiting}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">In queue right now</div>
          </CardContent>
        </Card>

        {/* Average Wait Time */}
        <Card className="border-l-4 border-l-accent bg-gradient-to-br from-accent/5 to-card">
          <CardHeader className="pb-2 pt-4">
            <div className="flex items-center justify-between">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">Avg Wait Time</CardDescription>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent className="pb-4">
            <div className={cn("text-3xl font-bold tabular-nums", !hospitalLoading && waitColour)}>
              {hospitalLoading ? (
                <Skeleton className="h-8 w-20" />
              ) : avgWaitMin > 0 ? (
                `${avgWaitMin}m`
              ) : (
                <span className="text-base text-muted-foreground">â€”</span>
              )}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">Registration â†’ triage today</div>
          </CardContent>
        </Card>

        {/* Patients Seen Today */}
        <Card className="border-l-4 border-l-success bg-gradient-to-br from-success/5 to-card">
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

        {/* Active Consultations */}
        <Card className="border-l-4 border-l-secondary bg-gradient-to-br from-secondary/5 to-card">
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

      {/* â”€â”€ Main Charts Row â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Patient Flow by Hour â€” col-span-8 */}
        <Card className="lg:col-span-8">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base font-semibold">Patient Flow Today</CardTitle>
                <CardDescription className="text-xs">New encounters registered by hour</CardDescription>
              </div>
              <Link to="/hospital/queue">
                <Button variant="ghost" size="sm" className="text-xs">
                  Live Queue <ArrowRight className="ml-1 h-3 w-3" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <div className="h-[340px]">
              {hospitalLoading ? (
                <div className="flex h-full flex-col gap-3 p-4">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                  <Skeleton className="h-4 w-4/6" />
                  <Skeleton className="h-4 w-full" />
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
                  <span>No encounter data for today yet.</span>
                  <span className="text-xs opacity-70">Updates every 30 seconds.</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Queue by Department â€” col-span-4 */}
        <Card className="lg:col-span-4">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base font-semibold">Queue by Department</CardTitle>
                <CardDescription className="text-xs">Active (non-discharged) patients</CardDescription>
              </div>
              <Link to="/hospital/queue">
                <Button variant="ghost" size="sm" className="text-xs">
                  All <ArrowRight className="ml-1 h-3 w-3" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="pb-4">
            {hospitalLoading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}
              </div>
            ) : queueByDept.length > 0 ? (
              <div className="space-y-2">
                {queueByDept.slice(0, 7).map((d) => (
                  <div key={d.department} className="flex items-center justify-between rounded-lg border bg-card px-3 py-2">
                    <span className="text-sm font-medium truncate max-w-[130px]">{d.department}</span>
                    <div className="flex items-center gap-2 text-xs">
                      {d.waiting > 0 && (
                        <Badge variant="outline" className="border-warning/60 text-warning text-[10px] px-1.5">
                          {d.waiting} waiting
                        </Badge>
                      )}
                      {d.consulting > 0 && (
                        <Badge variant="outline" className="border-primary/60 text-primary text-[10px] px-1.5">
                          {d.consulting} active
                        </Badge>
                      )}
                      {d.waiting === 0 && d.consulting === 0 && (
                        <Badge variant="outline" className="border-success/60 text-success text-[10px] px-1.5">Clear</Badge>
                      )}
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

      {/* â”€â”€ Second Row: Alerts + Clinical Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* System Notifications â€” col-span-8 */}
        <Card className="lg:col-span-8 border-border/50 bg-muted/20">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base font-semibold">
              <Activity className="h-4 w-4 text-primary" />
              System Notifications
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[240px] space-y-2 overflow-y-auto pr-1">
              {alertsLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-14 w-full rounded-xl" />
                  <Skeleton className="h-14 w-full rounded-xl" />
                </div>
              ) : !alertsValid ? (
                <div className="py-4 text-sm text-muted-foreground">Alerts temporarily unavailable.</div>
              ) : alerts.length > 0 ? (
                alerts.map((alert: any, idx: number) => (
                  <div
                    key={idx}
                    className={cn(
                      "flex items-start gap-3 rounded-xl border p-3",
                      alert.severity === "critical"
                        ? "border-l-4 border-l-destructive bg-destructive/5 border-destructive/30"
                        : "border-l-4 border-l-warning bg-warning/5 border-border/50",
                    )}
                  >
                    <AlertCircle className={cn("mt-0.5 h-4 w-4 shrink-0", alert.severity === "critical" ? "text-destructive" : "text-warning")} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium leading-tight">{alert.title}</p>
                      <p className="text-xs text-muted-foreground">{alert.message}</p>
                      <p className="mt-0.5 text-[10px] text-muted-foreground/60">
                        {new Date(alert.created_at).toLocaleTimeString()}
                      </p>
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
            {alertsIsError && (
              <p className="mt-2 text-xs text-muted-foreground/70">
                Alerts service temporarily unavailable â€” refreshing automatically.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Clinical Summary â€” col-span-4 */}
        <Card className="lg:col-span-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">Clinical Summary</CardTitle>
            <CardDescription className="text-xs">Today's pending clinical activity</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pb-4">
            <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2.5">
              <div className="flex items-center gap-2">
                <CalendarCheck className="h-4 w-4 text-primary" />
                <span className="text-sm">Appointments</span>
              </div>
              <span className="text-sm font-bold tabular-nums">
                {hospitalLoading ? <Skeleton className="h-4 w-8 inline-block" /> : appointmentsToday}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2.5">
              <div className="flex items-center gap-2">
                <FlaskConical className="h-4 w-4 text-accent" />
                <span className="text-sm">Lab Orders Pending</span>
              </div>
              <span className={cn("text-sm font-bold tabular-nums", labOrdersPending > 10 ? "text-warning" : "")}>
                {hospitalLoading ? <Skeleton className="h-4 w-8 inline-block" /> : labOrdersPending}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2.5">
              <div className="flex items-center gap-2">
                <Pill className="h-4 w-4 text-secondary" />
                <span className="text-sm">Prescriptions Pending</span>
              </div>
              <span className={cn("text-sm font-bold tabular-nums", prescriptionsPending > 15 ? "text-warning" : "")}>
                {hospitalLoading ? <Skeleton className="h-4 w-8 inline-block" /> : prescriptionsPending}
              </span>
            </div>
            <div className="pt-1">
              <Link to="/hospital/lab">
                <Button variant="outline" size="sm" className="w-full text-xs">
                  View Lab Orders <ArrowRight className="ml-1 h-3 w-3" />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* â”€â”€ Quick Links â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/40 bg-muted/20 px-4 py-2.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Quick Links:</span>
        <Link to="/hospital/queue">
          <Badge variant="outline" className="cursor-pointer hover:bg-accent transition-colors">ðŸ¥ Hospital Queue</Badge>
        </Link>
        <Link to="/hospital/patients">
          <Badge variant="outline" className="cursor-pointer hover:bg-accent transition-colors">ðŸ‘¤ Patient Registry</Badge>
        </Link>
        <Link to="/hospital/lab">
          <Badge variant="outline" className="cursor-pointer hover:bg-accent transition-colors">ðŸ”¬ Lab Orders</Badge>
        </Link>
        <Link to="/compliance">
          <Badge variant="outline" className="cursor-pointer hover:bg-accent transition-colors">ðŸ›¡ Compliance</Badge>
        </Link>
        <Link to="/synbot">
          <Badge variant="outline" className="cursor-pointer hover:bg-accent transition-colors">ðŸ¤– Ask Synbot</Badge>
        </Link>
      </div>
    </motion.div>
  );
};

export default Dashboard;
