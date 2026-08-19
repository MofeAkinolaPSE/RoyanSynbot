import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Scissors, RefreshCw, Loader2, CalendarDays, CheckCircle2, AlertTriangle, HeartPulse,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { TheatreWorkspacePanel } from "@/components/theatre/TheatreWorkspacePanel";
import { StatusBadge, UrgencyBadge } from "@/components/theatre/theatre-shared";

interface TheatreCase {
  id: number;
  encounter_id: number;
  patient_id: number;
  patient_mrn?: string;
  patient_name?: string;
  theatre_name?: string;
  procedure_name: string;
  case_type?: string;
  urgency: string;
  status: string;
  scheduled_date?: string;
  start_time?: string;
  surgeon_id?: string;
  anaesthetist_id?: string;
  scrub_nurse?: string;
  circulating_nurse?: string;
  actual_start_time?: string;
  actual_end_time?: string;
  pre_op_checklist?: Record<string, boolean | string | null>;
  anaesthetic_record?: Record<string, unknown>;
  operative_notes?: Record<string, unknown>;
  post_op_notes?: Record<string, unknown>;
  notes?: string;
  booked_by?: string;
}

export default function SurgicalTheatre() {
  const today = new Date().toISOString().split("T")[0];

  const [scheduleDate, setScheduleDate] = useState(today);
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterUrgency, setFilterUrgency] = useState("all");

  const [panelCase, setPanelCase] = useState<TheatreCase | null>(null);
  const [panelInitialTab, setPanelInitialTab] = useState<string | undefined>(undefined);

  // All cases (for list tab)
  const { data: casesData, isLoading: casesLoading, refetch: refetchCases } = useQuery({
    queryKey: ["theatre-cases", filterStatus, filterUrgency],
    queryFn: () => api.hospital.theatre.listCases({
      status: filterStatus !== "all" ? filterStatus : undefined,
      urgency: filterUrgency !== "all" ? filterUrgency : undefined,
    }),
  });

  // Daily schedule
  const { data: scheduleData, isLoading: scheduleLoading, refetch: refetchSchedule } = useQuery({
    queryKey: ["theatre-schedule", scheduleDate],
    queryFn: () => api.hospital.theatre.dailySchedule(scheduleDate),
  });

  const { data: statsData, refetch: refetchStats } = useQuery({
    queryKey: ["theatre-stats"],
    queryFn: () => api.hospital.theatre.stats(),
    refetchInterval: 30_000,
  });
  const stats = statsData ?? {};

  const cases: TheatreCase[] = casesData?.cases || [];
  const schedule: TheatreCase[] = scheduleData?.schedule || [];

  // KPIs — sourced from /theatre/stats, not client-side filters over a
  // possibly status/urgency-filtered worklist.
  const kpi = {
    scheduled:  stats.scheduled  ?? 0,
    in_theatre: stats.in_theatre ?? 0,
    recovery:   stats.recovery   ?? 0,
    completed:  stats.completed  ?? 0,
    emergency:  stats.emergency  ?? 0,
  };

  function openPanel(c: TheatreCase, initialTab?: string) {
    setPanelCase(c);
    setPanelInitialTab(initialTab);
  }
  function closePanel() {
    setPanelCase(null);
    setPanelInitialTab(undefined);
  }

  function CaseRow({ c }: { c: TheatreCase }) {
    return (
      <TableRow className="border-border/50 hover:bg-muted cursor-pointer" onClick={() => openPanel(c)}>
        <TableCell className="font-mono text-xs text-muted-foreground">{c.id}</TableCell>
        <TableCell>
          <div className="font-medium text-sm">{c.procedure_name}</div>
          {c.theatre_name && <div className="text-xs text-muted-foreground">{c.theatre_name}</div>}
        </TableCell>
        <TableCell className="text-xs text-muted-foreground">{c.patient_name ?? `Patient ID ${c.patient_id}`}</TableCell>
        <TableCell>
          <UrgencyBadge urgency={c.urgency} />
        </TableCell>
        <TableCell>
          <StatusBadge status={c.status} />
        </TableCell>
        <TableCell className="text-xs text-muted-foreground">{c.surgeon_id || "—"}</TableCell>
        <TableCell className="text-xs text-muted-foreground">
          {c.scheduled_date && `${c.scheduled_date}${c.start_time ? " " + c.start_time : ""}`}
        </TableCell>
      </TableRow>
    );
  }

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 rounded-lg">
            <Scissors className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Surgical Theatre</h1>
            <p className="text-sm text-muted-foreground">Case scheduling, intraoperative records, and recovery</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="border-border"
            onClick={() => { refetchCases(); refetchSchedule(); refetchStats(); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Scheduled",  value: kpi.scheduled,  icon: CalendarDays, color: "text-slate-600",  bg: "bg-slate-50" },
          { label: "In Theatre", value: kpi.in_theatre, icon: Scissors,     color: "text-sky-700",   bg: "bg-sky-50" },
          { label: "Recovery",   value: kpi.recovery,   icon: HeartPulse,   color: "text-blue-700",  bg: "bg-blue-50" },
          { label: "Completed",  value: kpi.completed,  icon: CheckCircle2, color: "text-green-700", bg: "bg-green-50" },
          { label: "Emergency",  value: kpi.emergency,  icon: AlertTriangle,color: kpi.emergency > 0 ? "text-red-600" : "text-muted-foreground", bg: kpi.emergency > 0 ? "bg-red-50" : "bg-muted/30" },
        ].map(k => (
          <Card key={k.label} className={cn("border-border", k.bg)}>
            <CardContent className="pt-4 pb-3">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{k.label}</p>
                  <p className={cn("text-2xl font-bold", k.color)}>{k.value}</p>
                </div>
                <k.icon className={cn("w-5 h-5 mt-1", k.color)} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="cases">
        <TabsList className="bg-muted border border-border">
          <TabsTrigger value="cases">All Cases</TabsTrigger>
          <TabsTrigger value="schedule">Daily Schedule</TabsTrigger>
        </TabsList>

        {/* All Cases Tab */}
        <TabsContent value="cases" className="mt-4 space-y-4">
          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            {["all", "scheduled", "pre_op", "in_theatre", "recovery", "completed", "cancelled"].map(s => (
              <button key={s}
                onClick={() => setFilterStatus(s)}
                className={cn(
                  "px-3 py-1 rounded-full text-xs border transition-colors",
                  filterStatus === s
                    ? "bg-blue-700 border-blue-600 text-white"
                    : "border-border text-muted-foreground hover:border-primary/50"
                )}>
                {s === "all" ? "All Statuses" : s.replace("_", " ")}
              </button>
            ))}
            <div className="ml-2 flex gap-2">
              {["all", "elective", "urgent", "emergency"].map(u => (
                <button key={u}
                  onClick={() => setFilterUrgency(u)}
                  className={cn(
                    "px-3 py-1 rounded-full text-xs border transition-colors",
                    filterUrgency === u
                      ? "bg-blue-600 border-blue-500 text-white"
                      : "border-border text-muted-foreground hover:border-primary/50"
                  )}>
                  {u === "all" ? "All Urgencies" : u}
                </button>
              ))}
            </div>
          </div>

          <Card className="border-border bg-muted/20">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground text-xs">ID</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Procedure</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Patient</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Urgency</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Status</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Surgeon</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Date / Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {casesLoading
                  ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…</TableCell></TableRow>
                  : cases.length === 0
                    ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No cases found</TableCell></TableRow>
                    : cases.map(c => <CaseRow key={c.id} c={c} />)
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Daily Schedule Tab */}
        <TabsContent value="schedule" className="mt-4 space-y-4">
          <div className="flex items-center gap-3">
            <Label className="text-muted-foreground text-sm">Date</Label>
            <Input
              type="date"
              value={scheduleDate}
              onChange={e => setScheduleDate(e.target.value)}
              className="w-44 bg-background border-border text-white text-sm"
            />
          </div>

          {scheduleLoading
            ? <div className="text-center py-12 text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
            : schedule.length === 0
              ? <div className="text-center py-12 text-muted-foreground">No cases scheduled for {scheduleDate}</div>
              : (
                <div className="space-y-3">
                  {schedule.map(c => (
                    <Card key={c.id} className="border-border bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors"
                      onClick={() => openPanel(c)}>
                      <CardContent className="py-3 px-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4">
                            <div className="text-lg font-bold text-foreground font-mono w-14">
                              {c.start_time || "--:--"}
                            </div>
                            <div>
                              <div className="font-medium text-foreground">{c.procedure_name}</div>
                              <div className="text-xs text-muted-foreground flex gap-3 mt-0.5">
                                <span>{c.patient_name ?? `Patient ID ${c.patient_id}`}</span>
                                {c.theatre_name && <span>{c.theatre_name}</span>}
                                {c.surgeon_id && <span>Surgeon: {c.surgeon_id}</span>}
                                {c.anaesthetist_id && <span>Anaes: {c.anaesthetist_id}</span>}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <UrgencyBadge urgency={c.urgency} />
                            <StatusBadge status={c.status} />
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )
          }
        </TabsContent>
      </Tabs>

      {panelCase && (
        <TheatreWorkspacePanel case={panelCase} initialTab={panelInitialTab} onClose={closePanel} />
      )}
    </motion.div>
  );
}
