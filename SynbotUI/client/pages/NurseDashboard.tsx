import { useState, useMemo } from "react";
import { WorkspaceView } from "@/pages/StaffWorkspace";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  HeartPulse, BedDouble, AlertTriangle, Activity, Droplets,
  ChevronDown, Loader2, RefreshCw, ArrowRight, Syringe, Clock, Pill, Scissors,
} from "lucide-react";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { cn } from "@/lib/utils";
import { LabWorkspacePanel } from "@/components/lab/LabWorkspacePanel";
import { TheatreWorkspacePanel } from "@/components/theatre/TheatreWorkspacePanel";
import { NursingWorkspacePanel } from "@/components/nursing/NursingWorkspacePanel";
import { AdmissionRequestsCard } from "@/components/nursing/AdmissionRequestsCard";
import { RecentNursingNotes } from "@/components/nursing/RecentNursingNotes";
import { NursingWorklist } from "@/components/nursing/NursingWorklist";
import { ShowMeHow } from "@/components/tour/ShowMeHow";
import { BedWorkspacePanel } from "@/components/wards/BedWorkspacePanel";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function waitMins(ts?: string): string {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ── Ward Row (lazy-loads beds on expand) ──────────────────────────────────────
function WardRow({
  ward,
  onOpenBed,
}: {
  ward: any;
  /** Opens the bed workspace in place, so the nurse never leaves the station. */
  onOpenBed?: (bed: any) => void;
}) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  const { data: bedsData, isLoading: bedsLoading } = useQuery({
    queryKey: ["ward-beds-nurse", ward.id],
    queryFn: () => api.hospital.wards.beds(String(ward.id)),
    enabled: expanded,
    staleTime: 60_000,
  });

  const beds: any[] = Array.isArray(bedsData?.beds) ? bedsData.beds : [];
  const total    = ward.total_beds ?? ward.bed_count ?? 0;
  const occupied = ward.occupied_beds ?? beds.filter((b: any) => b.status === "occupied" || b.patient_id).length ?? 0;
  const pct = total > 0 ? Math.round((occupied / total) * 100) : 0;

  return (
    <div className="border-b border-border/50 last:border-0">
      <button
        className="flex w-full items-center justify-between px-4 py-3 hover:bg-muted/40 transition-colors text-left"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="font-medium text-sm">{ward.name ?? ward.ward_name}</span>
        <div className="flex items-center gap-4">
          <div className="w-28 hidden sm:block">
            <Progress value={pct} className="h-1.5" />
          </div>
          <span className="text-xs text-muted-foreground w-24 text-right">
            {occupied}/{total} beds ({pct}%)
          </span>
          <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-3">
          {bedsLoading ? (
            <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading beds…
            </div>
          ) : beds.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No beds configured</p>
          ) : (
            <div className="space-y-1">
              <div className="flex items-center gap-3 border-b pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <span className="w-[92px] shrink-0">Room</span>
                <span className="w-8 shrink-0">Bed</span>
                <span className="w-[76px] shrink-0">Rate</span>
                <span className="w-[68px] shrink-0">Status</span>
                <span className="min-w-0 flex-1">Patient</span>
              </div>
              {/* Same column sequence as the Wards & Beds page — Room, Bed,
                  Rate, Status, Patient — so a nurse reading one and then the
                  other is not re-learning the row. Room and rate only became
                  available once migration 209 gave beds a real room. */}
              {beds.map((bed: any) => (
                // Clicking a bed opens the same workspace the IPD queue uses —
                // room detail, running charges, add a service, nursing record.
                // A nurse standing at the station should not have to navigate to
                // another page to chart the patient in front of them.
                <button
                  key={bed.id}
                  onClick={() => onOpenBed?.({ ...bed, ward_id: ward.id, ward_name: ward.name ?? ward.ward_name })}
                  disabled={!onOpenBed}
                  className="flex w-full items-center gap-3 rounded px-1 -mx-1 py-1 text-left text-xs transition-colors hover:bg-muted/60 disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <span className="w-[92px] shrink-0 truncate font-medium">
                    {bed.room_name ?? <span className="italic text-muted-foreground/60">Unassigned</span>}
                  </span>
                  <span className="w-8 shrink-0 font-mono text-muted-foreground">{bed.bed_number}</span>
                  <span className="w-[76px] shrink-0 tabular-nums text-muted-foreground">
                    {bed.room_daily_rate
                      ? `₦${Number(bed.room_daily_rate).toLocaleString()}`
                      : <span className="text-amber-600">no rate</span>}
                  </span>
                  <Badge
                    variant="outline"
                    className={cn("shrink-0 text-xs",
                      bed.status === "occupied" ? "bg-blue-50 text-blue-700 border-blue-300" : "bg-green-50 text-green-700 border-green-300"
                    )}
                  >
                    {bed.status ?? "available"}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate">
                    {bed.patient_name ?? <span className="italic text-muted-foreground/50">Empty</span>}
                  </span>
                  {bed.patient_mrn && (
                    <span
                      role="link"
                      tabIndex={0}
                      className="h-5 shrink-0 rounded px-1.5 text-xs text-primary hover:underline"
                      onClick={(e) => { e.stopPropagation(); navigate(`/hospital/patients/${bed.patient_mrn}`); }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") { e.stopPropagation(); navigate(`/hospital/patients/${bed.patient_mrn}`); }
                      }}
                    >
                      PCE
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
/** The Nursing Station: the ward first, then the nurse's whole workspace (day, tasks, inbox, messages). */
export default function NurseDashboard() {
  return <WorkspaceView title="Nursing Station" lead={[{ key: "ward", label: "Nursing station", icon: HeartPulse, render: () => <NursingStation /> }]} />;
}

function NursingStation() {

  // Each KPI has its own section on this same page, so the tile scrolls rather
  // than navigating the nurse away from the board they are working from.
  const scrollTo = (id: string) =>
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();
  const today = new Date().toLocaleDateString("en-NG", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  // Vitals dialog state
  const [vitalsOpen, setVitalsOpen] = useState(false);
  const [vitalsEnc, setVitalsEnc] = useState<any>(null);
  const [labPanelOrder, setLabPanelOrder] = useState<any | null>(null);
  const [theatrePanelCase, setTheatrePanelCase] = useState<any | null>(null);
  const [nursingPanelEncounter, setNursingPanelEncounter] = useState<any | null>(null);
  // NursingWorkspacePanel has always accepted initialTab; neither page ever
  // passed one, so Notes and Flowsheet sat three clicks deep with no signpost.
  const [nursingPanelTab, setNursingPanelTab] = useState<string | undefined>(undefined);
  // Held so the notes feed can resolve a note back to a live encounter without
  // issuing its own duplicate query.
  const [worklistEncounters, setWorklistEncounters] = useState<any[]>([]);
  // Bed workspace opened from the ward card, so the station is self-sufficient.
  const [stationBed, setStationBed] = useState<any | null>(null);

  /**
   * queue_clinical.py names the field `mrn`; every other department's
   * enrichment calls it `patient_mrn`. Normalised here so the shared panel gets
   * the prop shape it expects.
   */
  const openNursingPanel = (enc: any, tab?: string) => {
    setNursingPanelTab(tab);
    setNursingPanelEncounter({ ...enc, patient_mrn: enc.patient_mrn ?? enc.mrn });
  };
  const [vitalsForm, setVitalsForm] = useState({
    bp_systolic: "", bp_diastolic: "", temperature: "", pulse: "",
    spo2: "", respiratory_rate: "", weight: "",
  });

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data: wardsData, isLoading: wardsLoading, refetch: refetchWards } = useQuery({
    queryKey: ["nurse-wards"],
    queryFn: () => api.hospital.wards.list(),
    refetchInterval: 30_000,
    staleTime: 60_000,
  });
  const wards: any[] = Array.isArray(wardsData?.wards) ? wardsData.wards : Array.isArray(wardsData) ? wardsData : [];

  const { data: waitingData, refetch: refetchWaiting } = useQuery({
    queryKey: ["nurse-waiting"],
    queryFn: () => api.hospital.queue.list({ status: "patient_registered" } as any),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
  const waitingPatients: any[] = Array.isArray(waitingData?.encounters) ? waitingData.encounters : [];

  const { data: triagedData, refetch: refetchTriaged } = useQuery({
    queryKey: ["nurse-triaged"],
    queryFn: () => api.hospital.queue.list({ status: "triaged" } as any),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
  const triagedPatients: any[] = Array.isArray(triagedData?.encounters) ? triagedData.encounters : [];

  const pendingAssessment = useMemo(
    () => [...waitingPatients, ...triagedPatients].sort((a, b) =>
      new Date(a.created_at ?? 0).getTime() - new Date(b.created_at ?? 0).getTime()
    ),
    [waitingPatients, triagedPatients]
  );


  const { data: inpatientsData, refetch: refetchInpatients } = useQuery({
    queryKey: ["nurse-inpatients"],
    queryFn: () => api.hospital.queue.list({ active_only: true } as any),
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
  const inpatients: any[] = Array.isArray(inpatientsData?.encounters) ? inpatientsData.encounters : [];

  const { data: critLabData, isLoading: critLoading, refetch: refetchCrit } = useQuery({
    queryKey: ["nurse-critical-labs"],
    queryFn: () => api.hospital.lab.critical(),
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
  const critFlags: any[] = Array.isArray(critLabData?.critical_results) ? critLabData.critical_results : [];

  const { data: medQueueData, isLoading: medQueueLoading } = useQuery({
    queryKey: ["nurse-med-queue"],
    queryFn: () => api.hospital.pharmacy.administrationQueue(),
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
  const medQueue: any[] = Array.isArray(medQueueData?.queue) ? medQueueData.queue : [];

  const { data: theatreInTheatreData, isLoading: theatreInTheatreLoading } = useQuery({
    queryKey: ["nurse-theatre-in-theatre"],
    queryFn: () => api.hospital.theatre.listCases({ status: "in_theatre" }),
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
  const { data: theatreRecoveryData, isLoading: theatreRecoveryLoading } = useQuery({
    queryKey: ["nurse-theatre-recovery"],
    queryFn: () => api.hospital.theatre.listCases({ status: "recovery" }),
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
  const theatreInProgress: any[] = [
    ...(Array.isArray(theatreInTheatreData?.cases) ? theatreInTheatreData.cases : []),
    ...(Array.isArray(theatreRecoveryData?.cases) ? theatreRecoveryData.cases : []),
  ];
  const theatreInProgressLoading = theatreInTheatreLoading || theatreRecoveryLoading;

  // Real-time: invalidate waiting/triaged instantly on encounter events
  useRealtimeChannel("encounter_updates", (msg: any) => {
    const ev = msg?.event ?? "";
    if (["encounter_opened", "nurse_done", "patient_called"].includes(ev)) {
      void qc.invalidateQueries({ queryKey: ["nurse-waiting"] });
      void qc.invalidateQueries({ queryKey: ["nurse-triaged"] });
      void qc.invalidateQueries({ queryKey: ["nurse-inpatients"] });
    }
  });

  const totalBeds    = useMemo(() => wards.reduce((s, w) => s + (w.total_beds ?? w.bed_count ?? 0), 0), [wards]);
  const occupiedBeds = useMemo(() => wards.reduce((s, w) => s + (w.occupied_beds ?? 0), 0), [wards]);
  const availableBeds = totalBeds - occupiedBeds;

  function doRefresh() {
    void refetchWards(); void refetchWaiting(); void refetchTriaged();
    void refetchInpatients(); void refetchCrit();
  }

  // ── Vitals mutation ────────────────────────────────────────────────────────
  const vitalsMut = useMutation({
    mutationFn: async () => {
      if (!vitalsEnc) throw new Error("No encounter selected");
      await api.hospital.nursing.recordVitals({
        patient_id: Number(vitalsEnc.patient_id),
        encounter_id: Number(vitalsEnc.id),
        bp_systolic:      vitalsForm.bp_systolic      ? Number(vitalsForm.bp_systolic)      : undefined,
        bp_diastolic:     vitalsForm.bp_diastolic     ? Number(vitalsForm.bp_diastolic)     : undefined,
        temperature:      vitalsForm.temperature      ? Number(vitalsForm.temperature)      : undefined,
        pulse:            vitalsForm.pulse            ? Number(vitalsForm.pulse)            : undefined,
        spo2:             vitalsForm.spo2             ? Number(vitalsForm.spo2)             : undefined,
        respiratory_rate: vitalsForm.respiratory_rate ? Number(vitalsForm.respiratory_rate) : undefined,
        weight:           vitalsForm.weight           ? Number(vitalsForm.weight)           : undefined,
      });
      return api.hospital.queue.nursingDone(vitalsEnc.id);
    },
    onSuccess: () => {
      toast({ title: "Vitals confirmed — patient ready for doctor" });
      setVitalsOpen(false);
      setVitalsEnc(null);
      setVitalsForm({ bp_systolic: "", bp_diastolic: "", temperature: "", pulse: "", spo2: "", respiratory_rate: "", weight: "" });
      void qc.invalidateQueries({ queryKey: ["nurse-waiting"] });
      void qc.invalidateQueries({ queryKey: ["nurse-triaged"] });
    },
    onError: (e: any) => toast({ title: "Error recording vitals", description: e.message, variant: "destructive" }),
  });

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
            <HeartPulse className="h-5 w-5 text-blue-600" /> Ward today
          </h2>
          <p className="text-sm text-muted-foreground">{today}</p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={doRefresh}>
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* Doctors asking for a bed. Above the KPIs because it is the one
          thing on this page another clinician is actively waiting on. */}
      <AdmissionRequestsCard onOpenPatient={(r) => openNursingPanel(r, "detail")} />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { label: "Waiting for Nurse",  value: pendingAssessment.length, icon: Syringe,      color: "text-teal-700",   bg: pendingAssessment.length > 0 ? "bg-teal-50 border-teal-200" : "", anchor: "sec-waiting" },
          { label: "Inpatients",         value: inpatients.length,        icon: Activity,     color: "text-blue-700",   bg: "bg-blue-50", anchor: "sec-inpatients" },
          { label: "Beds Available",     value: availableBeds,            icon: BedDouble,    color: "text-green-700",  bg: "bg-green-50", anchor: "sec-beds" },
          { label: "Critical Flags",     value: critFlags.length,         icon: AlertTriangle,color: critFlags.length > 0 ? "text-red-700" : "text-muted-foreground", bg: critFlags.length > 0 ? "bg-red-50" : "bg-muted/30", anchor: "sec-critical" },
        ].map(k => (
          <Card
            key={k.label}
            role="button"
            tabIndex={0}
            onClick={() => scrollTo(k.anchor)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); scrollTo(k.anchor); } }}
            className={cn("border-border/60 cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5", k.bg)}
          >
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

      {/* ── Waiting for Assessment ─────────────────────────────────────────── */}
      <Card id="sec-waiting" className={cn(pendingAssessment.length > 0 && "border-teal-500/30")}>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Syringe className={cn("h-4 w-4", pendingAssessment.length > 0 ? "text-teal-400" : "text-muted-foreground")} />
            Waiting for Assessment
            {pendingAssessment.length > 0 && (
              <span className="rounded-full bg-teal-500/20 text-teal-700 dark:text-teal-400 text-xs font-semibold px-2 py-0.5">
                {pendingAssessment.length}
              </span>
            )}
          </CardTitle>
          <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
            <Link to="/hospital/queue"><ArrowRight className="h-3 w-3" /> Full Queue</Link>
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {pendingAssessment.length === 0 ? (
            <p className="px-4 py-6 text-sm text-center text-muted-foreground">No patients waiting for assessment</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">Queue #</TableHead>
                  <TableHead>Patient</TableHead>
                  <TableHead className="hidden sm:table-cell">Chief Complaint</TableHead>
                  <TableHead className="w-16">Wait</TableHead>
                  <TableHead className="w-28">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pendingAssessment.map((enc: any) => (
                  <TableRow key={enc.id} className="hover:bg-muted/30">
                    <TableCell className="font-mono text-xs font-bold text-primary">
                      {enc.queue_number ?? String(enc.id).slice(0, 6)}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-0.5">
                        <button
                          className="text-sm font-medium text-left hover:text-primary transition-colors"
                          onClick={() => enc.mrn && navigate(`/hospital/patients/${enc.mrn}`)}
                        >
                          {enc.patient_name ?? <span className="text-muted-foreground italic text-xs">Unknown</span>}
                        </button>
                        {enc.mrn && <span className="font-mono text-xs text-muted-foreground">{enc.mrn}</span>}
                      </div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-muted-foreground max-w-[180px] truncate">
                      {enc.chief_complaint ?? "—"}
                    </TableCell>
                    <TableCell>
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />{waitMins(enc.created_at)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline"
                        className="h-7 px-2 text-xs gap-1 border-teal-500/40 text-teal-700 dark:text-teal-400 hover:bg-teal-500/10"
                        onClick={() => { setVitalsEnc(enc); setVitalsOpen(true); }}>
                        <Syringe className="h-3 w-3" /> Vitals
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Ward Bed Status */}
      <Card id="sec-beds">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <BedDouble className="h-4 w-4 text-blue-500" />
            Ward Bed Status
            <span className="ml-auto text-xs text-muted-foreground font-normal">Click a ward to see beds</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {wardsLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : wards.length === 0 ? (
            <p className="text-center py-8 text-sm text-muted-foreground">No wards configured</p>
          ) : wards.map((w: any) => <WardRow key={w.id} ward={w} onOpenBed={setStationBed} />)
          }
        </CardContent>
      </Card>

      {/* Critical Labs + Medications to Administer + Theatre In Progress + Active Inpatients */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <Card id="sec-critical">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className={cn("h-4 w-4", critFlags.length > 0 ? "text-red-500" : "text-muted-foreground")} />
              Critical Lab Flags
              {critFlags.length > 0 && (
                <span className="rounded-full bg-red-100 text-red-700 text-xs font-semibold px-2 py-0.5">{critFlags.length}</span>
              )}
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/lab"><ArrowRight className="h-3 w-3" /> Lab</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {critLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : critFlags.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No critical flags</p>
            ) : (
              <ul className="divide-y divide-border">
                {critFlags.slice(0, 8).map((f: any) => (
                  <li key={f.id} className="flex items-center justify-between gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/40 transition-colors"
                    onClick={() => setLabPanelOrder({
                      id: f.lab_order_id ?? f.id,
                      test_name: f.test_name,
                      patient_id: f.patient_id,
                      patient_name: f.patient_name,
                      patient_mrn: f.patient_mrn,
                      urgency: f.urgency,
                      status: f.order_status,
                      is_critical: true,
                    })}>
                    <div>
                      <p className="text-xs font-medium text-red-700">{f.test_name ?? `Result #${f.lab_order_id}`}</p>
                      <p className="text-xs text-muted-foreground">
                        Patient #{f.patient_id} · {fmtDate(f.resulted_at)}
                      </p>
                    </div>
                    <Badge variant="outline" className="text-xs bg-red-50 text-red-700 border-red-300 shrink-0">CRITICAL</Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Pill className="h-4 w-4 text-purple-500" />
              Medications to Administer
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/pharmacy"><ArrowRight className="h-3 w-3" /> Pharmacy</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {medQueueLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : medQueue.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No medications pending administration</p>
            ) : (
              <>
                <ul className="divide-y divide-border">
                  {medQueue.slice(0, 8).map((m: any) => (
                    <li key={m.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                      <div>
                        <p className="text-xs font-medium">{m.drug_name} {m.dosage ? `· ${m.dosage}` : ""}</p>
                        <p className="text-xs text-muted-foreground">
                          {m.patient_name ?? `Patient #${m.patient_id}`} · {m.route ?? "—"}
                        </p>
                      </div>
                      {m.patient_mrn && (
                        <Button variant="outline" size="sm" asChild className="h-6 px-2 text-xs border-primary/40 text-primary shrink-0">
                          <Link to={`/hospital/patients/${m.patient_mrn}`}>PCE</Link>
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="px-4 py-2 text-xs text-muted-foreground border-t">
                  Shows first dose not yet given only — doesn't track later scheduled doses.
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Scissors className="h-4 w-4 text-sky-500" />
              Theatre Cases In Progress
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/theatre"><ArrowRight className="h-3 w-3" /> Theatre</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {theatreInProgressLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : theatreInProgress.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No cases in theatre or recovery</p>
            ) : (
              <ul className="divide-y divide-border">
                {theatreInProgress.slice(0, 8).map((c: any) => (
                  <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/40 transition-colors"
                    onClick={() => setTheatrePanelCase(c)}>
                    <div>
                      <p className="text-xs font-medium">{c.procedure_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {c.patient_name ?? `Patient #${c.patient_id}`} · {c.theatre_name ?? "—"}
                      </p>
                    </div>
                    <Badge variant="outline" className={cn("text-xs shrink-0 capitalize",
                      c.status === "in_theatre" ? "bg-sky-50 text-sky-700 border-sky-300" : "bg-blue-50 text-blue-700 border-blue-300")}>
                      {c.status?.replace("_", " ")}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card id="sec-inpatients">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Droplets className="h-4 w-4 text-blue-500" />
              Active Inpatients
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/nursing"><ArrowRight className="h-3 w-3" /> Nursing Station</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {inpatients.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No active inpatients</p>
            ) : (
              <ul className="divide-y divide-border">
                {inpatients.slice(0, 8).map((enc: any) => (
                  <li key={enc.id} className="flex items-center justify-between gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/40 transition-colors"
                    onClick={() => setNursingPanelEncounter({ ...enc, patient_mrn: enc.mrn })}>
                    <div>
                      <p className="text-xs font-medium">{enc.patient_name ?? enc.mrn ?? `Patient #${enc.patient_id}`}</p>
                      <p className="text-xs text-muted-foreground">{enc.department ?? "—"}</p>
                    </div>
                    {enc.mrn && (
                      <Button variant="outline" size="sm" asChild className="h-6 px-2 text-xs border-primary/40 text-primary shrink-0"
                        onClick={(e) => e.stopPropagation()}>
                        <Link to={`/hospital/patients/${enc.mrn}`}>PCE</Link>
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Folded in from the retired Nursing Station page. The cards above
          each answer one question; this is the single view of everybody,
          which is what a nurse taking over a shift actually opens. */}
      <NursingWorklist onOpen={openNursingPanel} onEncountersLoaded={setWorklistEncounters} />

      <RecentNursingNotes encounters={worklistEncounters} onOpenNote={openNursingPanel} />

      {/* Quick Links */}
      <div className="flex flex-wrap gap-3">
        {[
          { label: "Nursing Station", href: "/hospital/nursing", color: "border-primary/40 text-primary" },
          { label: "Wards & Beds",    href: "/hospital/wards",   color: "" },
          { label: "Clinical Queue",  href: "/hospital/queue",   color: "" },
          { label: "Laboratory",      href: "/hospital/lab",     color: "" },
        ].map(l => (
          <Button key={l.href} variant="outline" size="sm" asChild className={cn("gap-1.5", l.color)}>
            <Link to={l.href}>{l.label} <ArrowRight className="h-3 w-3" /></Link>
          </Button>
        ))}
      </div>

      {/* ── Vitals Dialog ──────────────────────────────────────────────────── */}
      <Dialog open={vitalsOpen} onOpenChange={o => { if (!o) { setVitalsOpen(false); setVitalsEnc(null); } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HeartPulse className="h-4 w-4 text-teal-400" /> Record Vitals
            </DialogTitle>
            <DialogDescription>
              {vitalsEnc?.queue_number ?? String(vitalsEnc?.id ?? "").slice(0, 8)} — {vitalsEnc?.patient_name ?? "Patient"}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div className="space-y-1">
              <Label>BP Systolic (mmHg)</Label>
              <Input type="number" placeholder="e.g. 120" value={vitalsForm.bp_systolic}
                onChange={e => setVitalsForm(f => ({ ...f, bp_systolic: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>BP Diastolic (mmHg)</Label>
              <Input type="number" placeholder="e.g. 80" value={vitalsForm.bp_diastolic}
                onChange={e => setVitalsForm(f => ({ ...f, bp_diastolic: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Temperature (°C)</Label>
              <Input type="number" step="0.1" placeholder="e.g. 36.6" value={vitalsForm.temperature}
                onChange={e => setVitalsForm(f => ({ ...f, temperature: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Pulse (bpm)</Label>
              <Input type="number" placeholder="e.g. 72" value={vitalsForm.pulse}
                onChange={e => setVitalsForm(f => ({ ...f, pulse: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>SpO₂ (%)</Label>
              <Input type="number" placeholder="e.g. 98" value={vitalsForm.spo2}
                onChange={e => setVitalsForm(f => ({ ...f, spo2: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Respiratory Rate</Label>
              <Input type="number" placeholder="e.g. 18" value={vitalsForm.respiratory_rate}
                onChange={e => setVitalsForm(f => ({ ...f, respiratory_rate: e.target.value }))} />
            </div>
            <div className="col-span-2 space-y-1">
              <Label>Weight (kg)</Label>
              <Input type="number" step="0.1" placeholder="e.g. 70.5" value={vitalsForm.weight}
                onChange={e => setVitalsForm(f => ({ ...f, weight: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setVitalsOpen(false); setVitalsEnc(null); }}>Cancel</Button>
            <Button
              className="bg-teal-600 hover:bg-teal-700"
              disabled={vitalsMut.isPending}
              onClick={() => vitalsMut.mutate()}
            >
              {vitalsMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save & Confirm Vitals
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Lab Workspace panel (inline critical-result review) ──────────── */}
      {labPanelOrder && (
        <LabWorkspacePanel order={labPanelOrder} initialTab="result" onClose={() => setLabPanelOrder(null)} />
      )}

      {/* ── Theatre Workspace panel (inline in-progress case review) ─────── */}
      {theatrePanelCase && (
        <TheatreWorkspacePanel case={theatrePanelCase} onClose={() => setTheatrePanelCase(null)} />
      )}

      {/* Bed workspace, opened from the ward card. Same panel the IPD queue and
          the wards page use: room detail, running charges, add a service,
          nursing record — so a nurse configures the bed and charts the patient
          without leaving the station. */}
      {stationBed && (
        <BedWorkspacePanel bed={stationBed} onClose={() => setStationBed(null)} />
      )}

      {/* ── Nursing Workspace panel (inline active-inpatient charting) ───── */}
      {nursingPanelEncounter && (
        <NursingWorkspacePanel
          encounter={nursingPanelEncounter}
          initialTab={nursingPanelTab}
          onClose={() => { setNursingPanelEncounter(null); setNursingPanelTab(undefined); }}
        />
      )}
    </motion.div>
  );
}
