import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Activity, Users, Clock, AlertTriangle, RefreshCw, Loader2,
  ClipboardCheck, Stethoscope, LogOut, ChevronRight, Plus, LayoutGrid, List,
  FileText, Copy, Syringe, PhoneCall, HeartPulse,
} from "lucide-react";
import { PatientCprsPanel } from "@/components/PatientCprsPanel";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { AlertBanner } from "@/components/AlertBanner";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Encounter {
  id: string;
  patient_id?: string | number;
  status: string;
  department?: string;
  encounter_type?: string;
  triage_level?: string;
  triage_priority?: string;
  patient_name?: string;
  mrn?: string;
  created_at?: string;
  triage_at?: string;
  consultation_at?: string;
  chief_complaint?: string;
  queue_number?: string;
  consulting_room?: string;
  called_at?: string;
  nurse_done_at?: string;
}

const STATUS_COLORS: Record<string, string> = {
  patient_registered:  "bg-slate-500/20 text-slate-300 border-slate-500/30",
  triaged:             "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  nurse_assessment:    "bg-teal-500/20 text-teal-400 border-teal-500/30",
  called:              "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  consulting:          "bg-blue-500/20 text-blue-400 border-blue-500/30",
  lab_ordered:         "bg-purple-500/20 text-purple-400 border-purple-500/30",
  pharmacy_dispensing: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  billing_pending:     "bg-pink-500/20 text-pink-400 border-pink-500/30",
  discharged:          "bg-green-500/20 text-green-400 border-green-500/30",
};

const TRIAGE_COLORS: Record<string, string> = {
  immediate: "bg-red-500/20 text-red-400 border-red-500/30",
  urgent:    "bg-orange-500/20 text-orange-400 border-orange-500/30",
  non_urgent:  "bg-green-500/20 text-green-400 border-green-500/30",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? "bg-slate-500/20 text-slate-300 border-slate-500/30";
  return (
    <Badge variant="outline" className={cn("text-xs capitalize whitespace-nowrap", cls)}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

function waitMins(ts?: string): string {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ─── Component ────────────────────────────────────────────────────────────────
// ─── Kanban column config ─────────────────────────────────────────────────────
const KANBAN_COLUMNS = [
  {
    key: "waiting",
    label: "Waiting",
    color: "border-yellow-500/30 bg-yellow-500/5",
    headerColor: "text-yellow-400",
    statuses: ["patient_registered"],
  },
  {
    key: "triaged",
    label: "Triaged",
    color: "border-orange-500/30 bg-orange-500/5",
    headerColor: "text-orange-400",
    statuses: ["triaged"],
  },
  {
    key: "nurse",
    label: "Nurse / Called",
    color: "border-teal-500/30 bg-teal-500/5",
    headerColor: "text-teal-400",
    statuses: ["nurse_assessment", "called"],
  },
  {
    key: "consulting",
    label: "Consulting",
    color: "border-blue-500/30 bg-blue-500/5",
    headerColor: "text-blue-400",
    statuses: ["consulting", "lab_ordered", "pharmacy_dispensing"],
  },
  {
    key: "billing",
    label: "Billing / Done",
    color: "border-green-500/30 bg-green-500/5",
    headerColor: "text-green-400",
    statuses: ["billing_pending", "discharged"],
  },
] as const;

const ROOMS = ["Room 1", "Room 2", "Room 3", "Room 4", "Room 5"];

export default function ClinicalQueue() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();
  const nextStatus = (status: string) => ({
    consulting: "lab_ordered",
    lab_ordered: "pharmacy_dispensing",
    pharmacy_dispensing: "billing_pending",
  } as Record<string, string>)[status] ?? "billing_pending";

  const [viewMode, setViewMode] = useState<"table" | "board">("table");
  const [filter, setFilter] = useState<string>("all");
  const [triageOpen, setTriageOpen] = useState(false);
  const [consultOpen, setConsultOpen] = useState(false);
  const [dischargeOpen, setDischargeOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [openEncOpen, setOpenEncOpen] = useState(false);
  const [activeEnc, setActiveEnc] = useState<Encounter | null>(null);
  const [cprsMrn, setCprsMrn] = useState<string | null>(null);
  const [callRoomEnc, setCallRoomEnc] = useState<Encounter | null>(null);
  const [selectedRoom, setSelectedRoom] = useState("Room 1");
  const [consultForm, setConsultForm] = useState({ consulting_doctor: "", diagnosis_notes: "", icd10_search: "" });
  const [noteForm, setNoteForm] = useState({ note_type: "soap", content: "" });
  const [icd10Search, setIcd10Search] = useState("");

  const [triageForm, setTriageForm] = useState({ triage_level: "non_urgent", chief_complaint: "" });
  const [dischargeForm, setDischargeForm] = useState({ discharge_summary: "", disposition: "home" });
  const [openEncForm, setOpenEncForm] = useState({
    patient_id: "", encounter_type: "outpatient", department: "OPD",
  });
  const [vitalsOpen, setVitalsOpen] = useState(false);
  const [vitalsEnc, setVitalsEnc] = useState<Encounter | null>(null);
  const [vitalsForm, setVitalsForm] = useState({
    bp_systolic: "", bp_diastolic: "", temperature: "", pulse: "",
    spo2: "", respiratory_rate: "", weight: "",
  });

  // Queue data
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["clinical-queue", filter],
    queryFn: () => api.hospital.queue.list(filter !== "all" ? { status: filter } : undefined),
    refetchInterval: 30_000,
  });

  // Real-time: invalidate queue instantly on any encounter event
  useRealtimeChannel("encounter_updates", () => {
    void qc.invalidateQueries({ queryKey: ["clinical-queue"] });
  });

  const encounters: Encounter[] = Array.isArray(data?.encounters)
    ? data.encounters
    : Array.isArray(data)
    ? data
    : [];

  // Count by status
  const counts = encounters.reduce<Record<string, number>>((acc, e) => {
    acc[e.status] = (acc[e.status] ?? 0) + 1;
    return acc;
  }, {});

  const triageMut = useMutation({
    mutationFn: () => activeEnc ? api.hospital.queue.triage(activeEnc.id, triageForm) : Promise.reject(),
    onSuccess: () => { toast({ title: "Patient triaged" }); setTriageOpen(false); void qc.invalidateQueries({ queryKey: ["clinical-queue"] }); },
    onError: (e: any) => toast({ title: "Triage failed", description: e.message, variant: "destructive" }),
  });

  const consultMut = useMutation({
    mutationFn: () => activeEnc ? api.hospital.queue.consult(activeEnc.id, {
      consulting_doctor: consultForm.consulting_doctor || undefined,
      diagnosis_notes: consultForm.diagnosis_notes || undefined,
    }) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Moved to consulting" });
      setConsultOpen(false);
      setConsultForm({ consulting_doctor: "", diagnosis_notes: "", icd10_search: "" });
      void qc.invalidateQueries({ queryKey: ["clinical-queue"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const addNoteMut = useMutation({
    mutationFn: () => activeEnc ? api.hospital.queue.addNote(activeEnc.id, noteForm) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Note saved" });
      setNoteOpen(false);
      setNoteForm({ note_type: "soap", content: "" });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  // ICD-10 live search
  const { data: icd10Data } = useQuery({
    queryKey: ["icd10-queue", icd10Search],
    queryFn: () => api.hospital.clinical.searchIcd10(icd10Search),
    enabled: icd10Search.length >= 2,
    staleTime: 300_000,
  });
  const icd10Results: any[] = Array.isArray(icd10Data?.codes) ? icd10Data.codes : [];

  // Copy-forward: fetch last note for the active encounter's patient
  const { data: lastNoteData, refetch: fetchLastNote } = useQuery({
    queryKey: ["last-note", activeEnc?.id],
    queryFn: () => api.hospital.queue.listNotes(String(activeEnc!.id)),
    enabled: false,
    staleTime: 0,
  });

  const advanceMut = useMutation({
    mutationFn: (enc: Encounter) => api.hospital.queue.advance(enc.id, { new_status: nextStatus(enc.status) }),
    onSuccess: () => { toast({ title: "Stage advanced" }); void qc.invalidateQueries({ queryKey: ["clinical-queue"] }); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const dischargeMut = useMutation({
    mutationFn: () => activeEnc ? api.hospital.queue.discharge(activeEnc.id, dischargeForm) : Promise.reject(),
    onSuccess: () => { toast({ title: "Patient discharged" }); setDischargeOpen(false); void qc.invalidateQueries({ queryKey: ["clinical-queue"] }); },
    onError: (e: any) => toast({ title: "Discharge failed", description: e.message, variant: "destructive" }),
  });

  const openEncMut = useMutation({
    mutationFn: () => api.hospital.queue.open(openEncForm),
    onSuccess: () => { toast({ title: "Encounter opened" }); setOpenEncOpen(false); setOpenEncForm({ patient_id: "", encounter_type: "outpatient", department: "OPD" }); void qc.invalidateQueries({ queryKey: ["clinical-queue"] }); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

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
      void qc.invalidateQueries({ queryKey: ["clinical-queue"] });
    },
    onError: (e: any) => toast({ title: "Error recording vitals", description: e.message, variant: "destructive" }),
  });

  const callPatientMut = useMutation({
    mutationFn: ({ enc, room }: { enc: Encounter; room: string }) =>
      api.hospital.queue.callPatient(enc.id, room),
    onSuccess: () => {
      toast({ title: `Patient called into ${selectedRoom}` });
      setCallRoomEnc(null);
      void qc.invalidateQueries({ queryKey: ["clinical-queue"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const statuses = ["all", "patient_registered", "triaged", "nurse_assessment", "called", "consulting", "lab_ordered", "pharmacy_dispensing", "billing_pending"];

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Clinical Queue</h1>
          <p className="text-sm text-muted-foreground">Active patient encounters and workflow progression</p>
        </div>
        <div className="flex gap-2">
          <div className="flex rounded-lg border border-border overflow-hidden">
            <button
              onClick={() => setViewMode("table")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors",
                viewMode === "table" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <List className="h-3.5 w-3.5" /> List
            </button>
            <button
              onClick={() => setViewMode("board")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors",
                viewMode === "board" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" /> Board
            </button>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching} className="gap-2">
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
          </Button>
          <Button size="sm" onClick={() => setOpenEncOpen(true)} className="gap-2">
            <Plus className="h-3.5 w-3.5" /> Open Encounter
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Total Active", value: encounters.length, icon: <Users className="h-4 w-4" />, color: "text-blue-400" },
          { label: "Awaiting Triage", value: counts.patient_registered ?? 0, icon: <Clock className="h-4 w-4" />, color: "text-yellow-400" },
          { label: "In Consultation", value: counts.consulting ?? 0, icon: <Stethoscope className="h-4 w-4" />, color: "text-green-400" },
          { label: "Billing Pending", value: counts.billing_pending ?? 0, icon: <AlertTriangle className="h-4 w-4" />, color: "text-orange-400" },
        ].map(k => (
          <Card key={k.label}>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{k.label}</p>
                  <p className="text-2xl font-bold">{k.value}</p>
                </div>
                <span className={k.color}>{k.icon}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filter tabs */}
      <div className="flex flex-wrap gap-2">
        {statuses.map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs capitalize transition-colors",
              filter === s
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border hover:bg-muted",
            )}
          >
            {s === "all" ? "All" : s.replace(/_/g, " ")}{" "}
            {s !== "all" && counts[s] !== undefined && (
              <span className="ml-1 rounded-full bg-muted-foreground/20 px-1.5 py-0.5">{counts[s]}</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Kanban Board View ─────────────────────────────────────────────── */}
      {viewMode === "board" && (
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
          {KANBAN_COLUMNS.map(col => {
            const colEncounters = encounters.filter(e => col.statuses.includes(e.status as any));
            return (
              <div key={col.key} className={cn("rounded-xl border p-3", col.color)}>
                {/* Column header */}
                <div className={cn("mb-3 flex items-center justify-between text-xs font-semibold uppercase tracking-wide", col.headerColor)}>
                  <span>{col.label}</span>
                  <span className="rounded-full bg-current/10 px-2 py-0.5 text-current">{colEncounters.length}</span>
                </div>
                {/* Cards */}
                <div className="space-y-2">
                  {colEncounters.length === 0 ? (
                    <div className="py-8 text-center text-xs text-muted-foreground opacity-50">Empty</div>
                  ) : colEncounters.map(enc => (
                    <div
                      key={enc.id}
                      className="rounded-lg border border-border/60 bg-card p-3 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => enc.mrn && setCprsMrn(enc.mrn)}
                    >
                      <div className="mb-1 flex items-start justify-between gap-1">
                        {enc.queue_number ? (
                          <span className="font-mono text-sm font-bold text-primary">{enc.queue_number}</span>
                        ) : (
                          <span className="font-mono text-xs text-muted-foreground">{String(enc.id).slice(0, 8)}</span>
                        )}
                        {(enc.triage_level || enc.triage_priority) && (
                          <Badge variant="outline" className={cn("shrink-0 text-[10px] capitalize", TRIAGE_COLORS[enc.triage_level || enc.triage_priority || ""] ?? "")}>
                            {(enc.triage_level || enc.triage_priority || "").replace(/_/g, " ")}
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm font-medium leading-tight truncate mb-1">
                        {enc.patient_name || enc.mrn || `…${String(enc.patient_id ?? "").slice(-6)}`}
                      </p>
                      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />{waitMins(enc.created_at)}
                        </span>
                        {enc.department && <span>· {enc.department}</span>}
                        {enc.consulting_room && <span>· {enc.consulting_room}</span>}
                      </div>
                      {/* Quick actions */}
                      <div className="mt-2 flex flex-wrap gap-1" onClick={e => e.stopPropagation()}>
                        {enc.status === "patient_registered" && (
                          <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1" onClick={() => { setActiveEnc(enc); setTriageOpen(true); }}>
                            <ClipboardCheck className="h-3 w-3" /> Triage
                          </Button>
                        )}
                        {enc.status === "triaged" && (
                          <>
                            <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1 border-teal-500/40 text-teal-400 hover:bg-teal-500/10"
                              onClick={() => { setVitalsEnc(enc); setVitalsOpen(true); }}>
                              <Syringe className="h-3 w-3" /> Vitals
                            </Button>
                            <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1" onClick={() => { setActiveEnc(enc); setConsultOpen(true); }}>
                              <Stethoscope className="h-3 w-3" /> Consult
                            </Button>
                          </>
                        )}
                        {enc.status === "nurse_assessment" && (
                          <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10"
                            onClick={() => { setCallRoomEnc(enc); setSelectedRoom("Room 1"); }}>
                            <PhoneCall className="h-3 w-3" /> Call
                          </Button>
                        )}
                        {enc.status === "called" && (
                          <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1" onClick={() => { setActiveEnc(enc); setConsultOpen(true); }}>
                            <Stethoscope className="h-3 w-3" /> Start
                          </Button>
                        )}
                        {["consulting", "lab_ordered", "pharmacy_dispensing"].includes(enc.status) && (
                          <>
                            <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1" onClick={() => { setActiveEnc(enc); setNoteOpen(true); }}>
                              <FileText className="h-3 w-3" /> Note
                            </Button>
                            <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1" onClick={() => advanceMut.mutate(enc)} disabled={advanceMut.isPending}>
                              <ChevronRight className="h-3 w-3" /> Advance
                            </Button>
                          </>
                        )}
                        {enc.status === "billing_pending" && (
                          <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] gap-1 border-green-500/40 text-green-400 hover:bg-green-500/10"
                            onClick={() => { setActiveEnc(enc); setDischargeOpen(true); }}>
                            <LogOut className="h-3 w-3" /> Discharge
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Encounters table ─────────────────────────────────────────────── */}
      {viewMode === "table" && <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : encounters.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              <Activity className="mx-auto mb-3 h-8 w-8 opacity-30" />
              No active encounters{filter !== "all" ? ` with status "${filter.replace(/_/g, " ")}"` : ""}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Queue #</TableHead>
                  <TableHead>Patient</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Triage</TableHead>
                  <TableHead>Wait</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {encounters.map(enc => (
                  <TableRow
                    key={enc.id}
                    className="cursor-pointer hover:bg-muted/30"
                    onClick={() => enc.mrn && setCprsMrn(enc.mrn)}
                  >
                    <TableCell className="font-mono text-xs font-bold text-primary">
                      {enc.queue_number ?? String(enc.id).slice(0, 8)}
                    </TableCell>
                    <TableCell className="text-sm">{enc.patient_name || enc.mrn || (enc.patient_id ? String(enc.patient_id).slice(0, 8) : "—")}</TableCell>
                    <TableCell className="capitalize text-xs">{enc.encounter_type ?? "—"}</TableCell>
                    <TableCell className="text-xs">{enc.department ?? "—"}</TableCell>
                    <TableCell><StatusBadge status={enc.status} /></TableCell>
                    <TableCell>
                      {(enc.triage_level || enc.triage_priority) ? (
                        <Badge variant="outline" className={cn("text-xs capitalize", TRIAGE_COLORS[enc.triage_level || enc.triage_priority || ""] ?? "")}>
                          {(enc.triage_level || enc.triage_priority || "").replace(/_/g, " ")}
                        </Badge>
                      ) : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{waitMins(enc.created_at)}</TableCell>
                    <TableCell onClick={e => e.stopPropagation()}>
                      <div className="flex gap-1">
                        {enc.status === "patient_registered" && (
                          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => { setActiveEnc(enc); setTriageOpen(true); }}>
                            <ClipboardCheck className="h-3 w-3" /> Triage
                          </Button>
                        )}
                        {enc.status === "triaged" && (
                          <>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 border-teal-500/40 text-teal-400 hover:bg-teal-500/10"
                              onClick={() => { setVitalsEnc(enc); setVitalsOpen(true); }}>
                              <Syringe className="h-3 w-3" /> Vitals
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => { setActiveEnc(enc); setConsultOpen(true); }}>
                              <Stethoscope className="h-3 w-3" /> Consult
                            </Button>
                          </>
                        )}
                        {enc.status === "nurse_assessment" && (
                          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10"
                            onClick={() => { setCallRoomEnc(enc); setSelectedRoom("Room 1"); }}>
                            <PhoneCall className="h-3 w-3" /> Call
                          </Button>
                        )}
                        {enc.status === "called" && (
                          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => { setActiveEnc(enc); setConsultOpen(true); }}>
                            <Stethoscope className="h-3 w-3" /> Start
                          </Button>
                        )}
                        {["consulting", "lab_ordered", "pharmacy_dispensing"].includes(enc.status) && (
                          <>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => { setActiveEnc(enc); setNoteOpen(true); }}>
                              <FileText className="h-3 w-3" /> Note
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => advanceMut.mutate(enc)} disabled={advanceMut.isPending}>
                              <ChevronRight className="h-3 w-3" /> Advance
                            </Button>
                          </>
                        )}
                        {enc.status === "billing_pending" && (
                          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 border-green-500/40 text-green-400 hover:bg-green-500/10"
                            onClick={() => { setActiveEnc(enc); setDischargeOpen(true); }}>
                            <LogOut className="h-3 w-3" /> Discharge
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>}

      {/* ── Open Encounter Dialog ──────────────────────────────────────── */}
      <Dialog open={openEncOpen} onOpenChange={setOpenEncOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Open New Encounter</DialogTitle>
            <DialogDescription>Register a patient into the clinical queue</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Patient MRN *</Label>
              <Input value={openEncForm.patient_id} onChange={e => setOpenEncForm(f => ({ ...f, patient_id: e.target.value }))} placeholder="e.g. RHN-000001" />
            </div>
            <div className="space-y-1">
              <Label>Encounter Type</Label>
              <Select value={openEncForm.encounter_type} onValueChange={v => setOpenEncForm(f => ({ ...f, encounter_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="outpatient">Outpatient</SelectItem>
                  <SelectItem value="inpatient">Inpatient</SelectItem>
                  <SelectItem value="emergency">Emergency</SelectItem>
                  <SelectItem value="day_case">Day Case</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Department</Label>
              <Input value={openEncForm.department} onChange={e => setOpenEncForm(f => ({ ...f, department: e.target.value }))} placeholder="e.g. Cardiology" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenEncOpen(false)}>Cancel</Button>
            <Button disabled={!openEncForm.patient_id.trim() || openEncMut.isPending} onClick={() => openEncMut.mutate()}>
              {openEncMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Open Encounter
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Consult Dialog (ICD-10 + Notes) ───────────────────────────── */}
      <Dialog open={consultOpen} onOpenChange={setConsultOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Start Consultation</DialogTitle>
            <DialogDescription>Enc #{activeEnc?.id?.toString().slice(0, 8)} — {activeEnc?.patient_name ?? "Patient"}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Doctor</Label>
              <Input
                value={consultForm.consulting_doctor}
                onChange={e => setConsultForm(f => ({ ...f, consulting_doctor: e.target.value }))}
                placeholder="Consulting doctor name"
              />
            </div>
            <div className="space-y-1">
              <Label>ICD-10 Diagnosis (optional)</Label>
              <Input
                value={icd10Search}
                onChange={e => setIcd10Search(e.target.value)}
                placeholder="Search code or keyword..."
              />
              {icd10Results.length > 0 && (
                <div className="rounded-md border max-h-32 overflow-y-auto mt-1">
                  {icd10Results.map((code: any) => (
                    <button
                      key={code.code}
                      className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors"
                      onClick={() => {
                        setConsultForm(f => ({ ...f, diagnosis_notes: (f.diagnosis_notes ? f.diagnosis_notes + "\n" : "") + code.code + " — " + code.description }));
                        setIcd10Search("");
                      }}
                    >
                      <span className="font-mono text-muted-foreground mr-2">{code.code}</span>
                      {code.description}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="space-y-1">
              <Label>Diagnosis Notes</Label>
              <Textarea
                value={consultForm.diagnosis_notes}
                onChange={e => setConsultForm(f => ({ ...f, diagnosis_notes: e.target.value }))}
                placeholder="Clinical findings, differential, ICD codes selected above..."
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConsultOpen(false)}>Cancel</Button>
            <Button disabled={consultMut.isPending} onClick={() => consultMut.mutate()}>
              {consultMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Start Consultation
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Clinical Note Dialog ────────────────────────────────────────── */}
      <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Clinical Note</DialogTitle>
            <DialogDescription>Enc #{activeEnc?.id?.toString().slice(0, 8)} — {activeEnc?.patient_name ?? "Patient"}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="flex items-center justify-between">
              <div className="space-y-1 flex-1 mr-3">
                <Label>Note Type</Label>
                <Select value={noteForm.note_type} onValueChange={v => setNoteForm(f => ({ ...f, note_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="soap">SOAP</SelectItem>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="assessment">Assessment</SelectItem>
                    <SelectItem value="plan">Plan</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="mt-5 gap-1.5 text-xs"
                onClick={async () => {
                  const result = await fetchLastNote();
                  const notes = result.data?.notes ?? [];
                  if (notes.length > 0) {
                    setNoteForm(f => ({ ...f, content: notes[notes.length - 1].content }));
                  } else {
                    void 0;
                  }
                }}
              >
                <Copy className="h-3 w-3" /> Copy Last Note
              </Button>
            </div>
            <div className="space-y-1">
              <Label>Content *</Label>
              <Textarea
                value={noteForm.content}
                onChange={e => setNoteForm(f => ({ ...f, content: e.target.value }))}
                placeholder={noteForm.note_type === "soap"
                  ? "S: Subjective...\nO: Objective...\nA: Assessment...\nP: Plan..."
                  : "Clinical note content..."}
                rows={8}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNoteOpen(false)}>Cancel</Button>
            <Button disabled={!noteForm.content.trim() || addNoteMut.isPending} onClick={() => addNoteMut.mutate()}>
              {addNoteMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save Note
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Triage Dialog ──────────────────────────────────────────────── */}
      <Dialog open={triageOpen} onOpenChange={setTriageOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Triage Patient</DialogTitle>
            <DialogDescription>Encounter {String(activeEnc?.id ?? "").slice(0, 8)}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Triage Priority</Label>
              <Select value={triageForm.triage_level} onValueChange={v => setTriageForm(f => ({ ...f, triage_level: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="immediate">Immediate (Red)</SelectItem>
                  <SelectItem value="urgent">Urgent (Orange)</SelectItem>
                  <SelectItem value="less_urgent">Less Urgent</SelectItem>
                  <SelectItem value="non_urgent">Non Urgent</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Chief Complaint</Label>
              <Textarea value={triageForm.chief_complaint} onChange={e => setTriageForm(f => ({ ...f, chief_complaint: e.target.value }))} placeholder="Brief presenting complaint..." rows={3} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTriageOpen(false)}>Cancel</Button>
            <Button disabled={triageMut.isPending} onClick={() => triageMut.mutate()}>
              {triageMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Confirm Triage
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Discharge Dialog ───────────────────────────────────────────── */}
      <Dialog open={dischargeOpen} onOpenChange={setDischargeOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Discharge Patient</DialogTitle>
            <DialogDescription>Encounter {String(activeEnc?.id ?? "").slice(0, 8)}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Disposition</Label>
              <Select value={dischargeForm.disposition} onValueChange={v => setDischargeForm(f => ({ ...f, disposition: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="home">Home</SelectItem>
                  <SelectItem value="admit">Admit to Ward</SelectItem>
                  <SelectItem value="refer">Referred</SelectItem>
                  <SelectItem value="deceased">Deceased</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Discharge Summary</Label>
              <Textarea value={dischargeForm.discharge_summary} onChange={e => setDischargeForm(f => ({ ...f, discharge_summary: e.target.value }))} placeholder="Clinical summary, follow-up instructions..." rows={4} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDischargeOpen(false)}>Cancel</Button>
            <Button className="bg-green-600 hover:bg-green-700" disabled={dischargeMut.isPending} onClick={() => dischargeMut.mutate()}>
              {dischargeMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Confirm Discharge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Call Patient Dialog ────────────────────────────────────────── */}
      <Dialog open={!!callRoomEnc} onOpenChange={open => { if (!open) setCallRoomEnc(null); }}>
        <DialogContent className="sm:max-w-xs">
          <DialogHeader>
            <DialogTitle>Call Patient into Room</DialogTitle>
            <DialogDescription>
              {callRoomEnc?.queue_number ?? String(callRoomEnc?.id ?? "").slice(0, 8)} — {callRoomEnc?.patient_name ?? "Patient"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Label>Select Room</Label>
            <Select value={selectedRoom} onValueChange={setSelectedRoom}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {ROOMS.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCallRoomEnc(null)}>Cancel</Button>
            <Button
              disabled={callPatientMut.isPending}
              onClick={() => callRoomEnc && callPatientMut.mutate({ enc: callRoomEnc, room: selectedRoom })}
            >
              {callPatientMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Call into {selectedRoom}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Vitals Dialog ──────────────────────────────────────────────── */}
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

      {/* ── Patient CPRS slide panel ───────────────────────────────────── */}
      {cprsMrn && (
        <PatientCprsPanel patientMrn={cprsMrn} onClose={() => setCprsMrn(null)} />
      )}
    </motion.div>
  );
}
