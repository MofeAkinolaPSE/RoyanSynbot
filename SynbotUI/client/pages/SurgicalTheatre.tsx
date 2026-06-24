import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  Scissors, RefreshCw, Loader2, CalendarDays, CheckCircle2, AlertTriangle,
  Plus, ClipboardList, Stethoscope, FileText, HeartPulse, ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const URGENCY_COLORS: Record<string, string> = {
  elective:  "bg-blue-100 text-blue-700 border-blue-300",
  urgent:    "bg-orange-100 text-orange-700 border-orange-300",
  emergency: "bg-red-100 text-red-700 border-red-300",
};

const STATUS_COLORS: Record<string, string> = {
  scheduled:  "bg-slate-100 text-slate-600 border-slate-300",
  pre_op:     "bg-yellow-100 text-yellow-700 border-yellow-300",
  in_theatre: "bg-sky-100 text-sky-700 border-sky-300",
  recovery:   "bg-blue-100 text-blue-700 border-blue-300",
  completed:  "bg-green-100 text-green-700 border-green-300",
  cancelled:  "bg-slate-100 text-slate-500 border-slate-300",
};

const STATUS_NEXT: Record<string, string> = {
  scheduled:  "Start Pre-Op",
  pre_op:     "Move to Theatre",
  in_theatre: "Send to Recovery",
  recovery:   "Mark Completed",
};

const STATUS_TRANSITIONS: Record<string, string> = {
  scheduled:  "pre_op",
  pre_op:     "in_theatre",
  in_theatre: "recovery",
  recovery:   "completed",
};

interface TheatreCase {
  id: number;
  encounter_id: number;
  patient_id: number;
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

const emptyBooking = {
  encounter_id: "",
  patient_id: "",
  procedure_name: "",
  theatre_name: "",
  case_type: "",
  urgency: "elective",
  scheduled_date: "",
  start_time: "",
  surgeon_id: "",
  anaesthetist_id: "",
  scrub_nurse: "",
  circulating_nurse: "",
  notes: "",
};

const emptyPreOp = {
  consent_signed: false,
  site_marked: false,
  allergies_confirmed: false,
  blood_group_confirmed: false,
  fasting_confirmed: false,
  iv_access: false,
  premedication_given: false,
  imaging_available: false,
  blood_available: false,
  equipment_checked: false,
  notes: "",
};

const emptyAnaesthetic = {
  anaesthetic_type: "general",
  asa_grade: "",
  induction_agent: "",
  maintenance_agent: "",
  airway_management: "",
  positioning: "",
  total_duration_minutes: "",
  blood_loss_ml: "",
  fluids_given_ml: "",
  complications: "",
  notes: "",
};

const emptyOperative = {
  incision: "",
  findings: "",
  procedure_performed: "",
  specimens_sent: "",
  drains_inserted: false,
  closure_method: "",
  complications: "",
  blood_loss_ml: "",
  surgeon_notes: "",
};

const emptyPostOp = {
  recovery_location: "",
  vital_signs_stable: true,
  pain_score: "",
  nausea_vomiting: false,
  oxygen_therapy: false,
  wound_status: "",
  discharge_criteria_met: false,
  follow_up_date: "",
  post_op_medications: "",
  complications: "",
  notes: "",
};

function CheckItem({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer group">
      <div
        onClick={() => onChange(!checked)}
        className={cn(
          "w-5 h-5 rounded border flex items-center justify-center transition-colors cursor-pointer",
          checked ? "bg-green-100 border-green-500" : "border-border group-hover:border-ring"
        )}
      >
        {checked && <CheckCircle2 className="w-3 h-3 text-green-600" />}
      </div>
      <span className="text-sm text-foreground">{label}</span>
    </label>
  );
}

export default function SurgicalTheatre() {
  const { toast } = useToast();
  const qc = useQueryClient();
  const today = new Date().toISOString().split("T")[0];

  const [scheduleDate, setScheduleDate] = useState(today);
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterUrgency, setFilterUrgency] = useState("all");

  const [bookingOpen, setBookingOpen] = useState(false);
  const [bookingForm, setBookingForm] = useState({ ...emptyBooking });

  const [preOpOpen, setPreOpOpen] = useState(false);
  const [preOpCase, setPreOpCase] = useState<TheatreCase | null>(null);
  const [preOpForm, setPreOpForm] = useState({ ...emptyPreOp });

  const [anaesOpen, setAnaesOpen] = useState(false);
  const [anaesCase, setAnaesCase] = useState<TheatreCase | null>(null);
  const [anaesForm, setAnaesForm] = useState({ ...emptyAnaesthetic });

  const [opNotesOpen, setOpNotesOpen] = useState(false);
  const [opNotesCase, setOpNotesCase] = useState<TheatreCase | null>(null);
  const [opForm, setOpForm] = useState({ ...emptyOperative });

  const [postOpOpen, setPostOpOpen] = useState(false);
  const [postOpCase, setPostOpCase] = useState<TheatreCase | null>(null);
  const [postOpForm, setPostOpForm] = useState({ ...emptyPostOp });

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

  const cases: TheatreCase[] = casesData?.cases || [];
  const schedule: TheatreCase[] = scheduleData?.schedule || [];

  // KPIs from all cases
  const kpi = {
    scheduled:  cases.filter(c => c.status === "scheduled").length,
    in_theatre: cases.filter(c => c.status === "in_theatre").length,
    recovery:   cases.filter(c => c.status === "recovery").length,
    completed:  cases.filter(c => c.status === "completed").length,
    emergency:  cases.filter(c => c.urgency === "emergency").length,
  };

  const bookMut = useMutation({
    mutationFn: (d: typeof bookingForm) =>
      api.hospital.theatre.scheduleCase({
        ...d,
        encounter_id: Number(d.encounter_id),
        patient_id:   Number(d.patient_id),
      }),
    onSuccess: () => {
      toast({ title: "Theatre case scheduled" });
      setBookingOpen(false);
      setBookingForm({ ...emptyBooking });
      qc.invalidateQueries({ queryKey: ["theatre-cases"] });
      qc.invalidateQueries({ queryKey: ["theatre-schedule"] });
    },
    onError: () => toast({ title: "Failed to schedule case", variant: "destructive" }),
  });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.hospital.theatre.advanceStatus(id, { status }),
    onSuccess: (_, v) => {
      toast({ title: `Status advanced to ${v.status.replace("_", " ")}` });
      qc.invalidateQueries({ queryKey: ["theatre-cases"] });
      qc.invalidateQueries({ queryKey: ["theatre-schedule"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Transition failed", variant: "destructive" }),
  });

  const preOpMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: typeof preOpForm }) =>
      api.hospital.theatre.submitPreOp(id, {
        ...data,
        notes: data.notes || undefined,
      }),
    onSuccess: () => {
      toast({ title: "Pre-op checklist saved" });
      setPreOpOpen(false);
      qc.invalidateQueries({ queryKey: ["theatre-cases"] });
    },
    onError: () => toast({ title: "Failed to save pre-op checklist", variant: "destructive" }),
  });

  const anaesMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: typeof anaesForm }) =>
      api.hospital.theatre.submitAnaesthetic(id, {
        ...data,
        total_duration_minutes: data.total_duration_minutes ? Number(data.total_duration_minutes) : undefined,
        blood_loss_ml:          data.blood_loss_ml ? Number(data.blood_loss_ml) : undefined,
        fluids_given_ml:        data.fluids_given_ml ? Number(data.fluids_given_ml) : undefined,
      }),
    onSuccess: () => {
      toast({ title: "Anaesthetic record saved" });
      setAnaesOpen(false);
      qc.invalidateQueries({ queryKey: ["theatre-cases"] });
    },
    onError: () => toast({ title: "Failed to save anaesthetic record", variant: "destructive" }),
  });

  const opNotesMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: typeof opForm }) =>
      api.hospital.theatre.submitOperativeNotes(id, {
        ...data,
        blood_loss_ml: data.blood_loss_ml ? Number(data.blood_loss_ml) : undefined,
      }),
    onSuccess: () => {
      toast({ title: "Operative notes saved" });
      setOpNotesOpen(false);
      qc.invalidateQueries({ queryKey: ["theatre-cases"] });
    },
    onError: () => toast({ title: "Failed to save operative notes", variant: "destructive" }),
  });

  const postOpMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: typeof postOpForm }) =>
      api.hospital.theatre.submitPostOp(id, {
        ...data,
        pain_score: data.pain_score !== "" ? Number(data.pain_score) : undefined,
      }),
    onSuccess: () => {
      toast({ title: "Post-op record saved" });
      setPostOpOpen(false);
      qc.invalidateQueries({ queryKey: ["theatre-cases"] });
    },
    onError: () => toast({ title: "Failed to save post-op record", variant: "destructive" }),
  });

  function openPreOp(c: TheatreCase) {
    setPreOpCase(c);
    setPreOpForm({ ...emptyPreOp, ...(c.pre_op_checklist as any || {}) });
    setPreOpOpen(true);
  }

  function openAnaes(c: TheatreCase) {
    setAnaesCase(c);
    setAnaesForm({ ...emptyAnaesthetic, ...(c.anaesthetic_record as any || {}) });
    setAnaesOpen(true);
  }

  function openOpNotes(c: TheatreCase) {
    setOpNotesCase(c);
    setOpForm({ ...emptyOperative, ...(c.operative_notes as any || {}) });
    setOpNotesOpen(true);
  }

  function openPostOp(c: TheatreCase) {
    setPostOpCase(c);
    setPostOpForm({ ...emptyPostOp, ...(c.post_op_notes as any || {}) });
    setPostOpOpen(true);
  }

  function CaseRow({ c }: { c: TheatreCase }) {
    const nextStatus = STATUS_TRANSITIONS[c.status];
    const nextLabel  = STATUS_NEXT[c.status];
    return (
      <TableRow className="border-border/50 hover:bg-muted">
        <TableCell className="font-mono text-xs text-muted-foreground">{c.id}</TableCell>
        <TableCell>
          <div className="font-medium text-sm">{c.procedure_name}</div>
          {c.theatre_name && <div className="text-xs text-muted-foreground">{c.theatre_name}</div>}
        </TableCell>
        <TableCell>
          <Badge variant="outline" className={cn("text-xs capitalize", URGENCY_COLORS[c.urgency] || "")}>
            {c.urgency}
          </Badge>
        </TableCell>
        <TableCell>
          <Badge variant="outline" className={cn("text-xs", STATUS_COLORS[c.status] || "")}>
            {c.status.replace("_", " ")}
          </Badge>
        </TableCell>
        <TableCell className="text-xs text-muted-foreground">{c.surgeon_id || "—"}</TableCell>
        <TableCell className="text-xs text-muted-foreground">
          {c.scheduled_date && `${c.scheduled_date}${c.start_time ? " " + c.start_time : ""}`}
        </TableCell>
        <TableCell>
          <div className="flex gap-1 flex-wrap">
            {/* Pre-op checklist — available from scheduled onwards */}
            {["scheduled", "pre_op"].includes(c.status) && (
              <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                onClick={() => openPreOp(c)}>
                <ClipboardList className="w-3 h-3 mr-1" /> Pre-Op
              </Button>
            )}
            {/* Anaesthetic — available from pre_op */}
            {["pre_op", "in_theatre"].includes(c.status) && (
              <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                onClick={() => openAnaes(c)}>
                <Stethoscope className="w-3 h-3 mr-1" /> Anaes
              </Button>
            )}
            {/* Operative notes — in_theatre */}
            {c.status === "in_theatre" && (
              <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                onClick={() => openOpNotes(c)}>
                <FileText className="w-3 h-3 mr-1" /> Op Notes
              </Button>
            )}
            {/* Post-op — recovery */}
            {c.status === "recovery" && (
              <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                onClick={() => openPostOp(c)}>
                <HeartPulse className="w-3 h-3 mr-1" /> Post-Op
              </Button>
            )}
            {/* Advance status */}
            {nextStatus && nextLabel && (
              <Button size="sm" className="h-6 text-xs px-2 bg-blue-700 hover:bg-blue-800"
                disabled={statusMut.isPending}
                onClick={() => statusMut.mutate({ id: c.id, status: nextStatus })}>
                {statusMut.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : (
                  <>{nextLabel} <ChevronRight className="w-3 h-3 ml-1" /></>
                )}
              </Button>
            )}
          </div>
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
            onClick={() => { refetchCases(); refetchSchedule(); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" className="bg-blue-700 hover:bg-blue-800"
            onClick={() => setBookingOpen(true)}>
            <Plus className="w-4 h-4 mr-1" /> Book Case
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
                  <TableHead className="text-muted-foreground text-xs">Urgency</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Status</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Surgeon</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Date / Time</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Actions</TableHead>
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
                    <Card key={c.id} className="border-border bg-muted/30">
                      <CardContent className="py-3 px-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4">
                            <div className="text-lg font-bold text-foreground font-mono w-14">
                              {c.start_time || "--:--"}
                            </div>
                            <div>
                              <div className="font-medium text-foreground">{c.procedure_name}</div>
                              <div className="text-xs text-muted-foreground flex gap-3 mt-0.5">
                                {c.theatre_name && <span>{c.theatre_name}</span>}
                                {c.surgeon_id && <span>Surgeon: {c.surgeon_id}</span>}
                                {c.anaesthetist_id && <span>Anaes: {c.anaesthetist_id}</span>}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className={cn("text-xs capitalize", URGENCY_COLORS[c.urgency] || "")}>
                              {c.urgency}
                            </Badge>
                            <Badge variant="outline" className={cn("text-xs", STATUS_COLORS[c.status] || "")}>
                              {c.status.replace("_", " ")}
                            </Badge>
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

      {/* --- Book Case Dialog --- */}
      <Dialog open={bookingOpen} onOpenChange={setBookingOpen}>
        <DialogContent className="bg-card border-border text-white max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Book Theatre Case</DialogTitle>
            <DialogDescription className="text-muted-foreground">Schedule a new surgical procedure</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "encounter_id",   label: "Encounter ID",     type: "number" },
              { key: "patient_id",     label: "Patient ID",       type: "number" },
              { key: "procedure_name", label: "Procedure Name",   type: "text",   colSpan: 2 },
              { key: "theatre_name",   label: "Theatre",          type: "text" },
              { key: "surgeon_id",     label: "Surgeon ID",       type: "text" },
              { key: "anaesthetist_id",label: "Anaesthetist ID",  type: "text" },
              { key: "scrub_nurse",    label: "Scrub Nurse",      type: "text" },
              { key: "circulating_nurse", label: "Circulating Nurse", type: "text" },
              { key: "scheduled_date", label: "Scheduled Date",   type: "date" },
              { key: "start_time",     label: "Start Time (HH:MM)",type: "time" },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input
                  type={f.type}
                  value={(bookingForm as any)[f.key] || ""}
                  onChange={e => setBookingForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8"
                />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Urgency</Label>
              <Select value={bookingForm.urgency}
                onValueChange={v => setBookingForm(p => ({ ...p, urgency: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["elective", "urgent", "emergency"].map(u => (
                    <SelectItem key={u} value={u} className="capitalize">{u}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Case Type</Label>
              <Select value={bookingForm.case_type || ""}
                onValueChange={v => setBookingForm(p => ({ ...p, case_type: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm">
                  <SelectValue placeholder="Select…" />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["general", "regional", "local", "sedation"].map(t => (
                    <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Notes</Label>
              <Textarea
                value={bookingForm.notes}
                onChange={e => setBookingForm(p => ({ ...p, notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-16 resize-none"
              />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setBookingOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={bookMut.isPending || !bookingForm.encounter_id || !bookingForm.patient_id || !bookingForm.procedure_name}
              onClick={() => bookMut.mutate(bookingForm)}>
              {bookMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Schedule Case
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* --- Pre-Op Checklist Dialog --- */}
      <Dialog open={preOpOpen} onOpenChange={setPreOpOpen}>
        <DialogContent className="bg-card border-border text-white max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ClipboardList className="w-5 h-5 text-yellow-400" />
              Pre-Op Safety Checklist
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">WHO Surgical Safety Checklist — {preOpCase?.procedure_name}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-3 mt-2">
            {[
              ["consent_signed",       "Consent signed by patient"],
              ["site_marked",          "Surgical site marked"],
              ["allergies_confirmed",  "Allergies confirmed"],
              ["blood_group_confirmed","Blood group confirmed"],
              ["fasting_confirmed",    "Patient fasting confirmed"],
              ["iv_access",            "IV access established"],
              ["premedication_given",  "Premedication given"],
              ["imaging_available",    "Imaging available in theatre"],
              ["blood_available",      "Blood / blood products available"],
              ["equipment_checked",    "Equipment checked by scrub nurse"],
            ].map(([key, label]) => (
              <CheckItem
                key={key}
                label={label}
                checked={!!(preOpForm as any)[key]}
                onChange={v => setPreOpForm(p => ({ ...p, [key]: v }))}
              />
            ))}
            <div className="space-y-1 mt-1">
              <Label className="text-xs text-muted-foreground">Notes</Label>
              <Textarea
                value={preOpForm.notes}
                onChange={e => setPreOpForm(p => ({ ...p, notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-16 resize-none"
              />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setPreOpOpen(false)}>Cancel</Button>
            <Button className="bg-yellow-600 hover:bg-yellow-700"
              disabled={preOpMut.isPending}
              onClick={() => preOpMut.mutate({ id: preOpCase!.id, data: preOpForm })}>
              {preOpMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Checklist
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* --- Anaesthetic Record Dialog --- */}
      <Dialog open={anaesOpen} onOpenChange={setAnaesOpen}>
        <DialogContent className="bg-card border-border text-white max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Stethoscope className="w-5 h-5 text-blue-400" />
              Anaesthetic Record
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">{anaesCase?.procedure_name}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Anaesthetic Type</Label>
              <Select value={anaesForm.anaesthetic_type}
                onValueChange={v => setAnaesForm(p => ({ ...p, anaesthetic_type: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["general", "regional", "spinal", "local", "sedation"].map(t => (
                    <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {[
              { key: "asa_grade",              label: "ASA Grade (I–VI)" },
              { key: "induction_agent",        label: "Induction Agent" },
              { key: "maintenance_agent",      label: "Maintenance Agent" },
              { key: "airway_management",      label: "Airway Management" },
              { key: "positioning",            label: "Patient Positioning" },
              { key: "total_duration_minutes", label: "Duration (min)",    type: "number" },
              { key: "blood_loss_ml",          label: "Blood Loss (mL)",   type: "number" },
              { key: "fluids_given_ml",        label: "Fluids Given (mL)", type: "number" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input
                  type={f.type || "text"}
                  value={(anaesForm as any)[f.key] || ""}
                  onChange={e => setAnaesForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8"
                />
              </div>
            ))}
            {["complications", "notes"].map(k => (
              <div key={k} className="col-span-2 space-y-1">
                <Label className="text-xs text-muted-foreground capitalize">{k}</Label>
                <Textarea
                  value={(anaesForm as any)[k] || ""}
                  onChange={e => setAnaesForm(p => ({ ...p, [k]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-16 resize-none"
                />
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setAnaesOpen(false)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700"
              disabled={anaesMut.isPending}
              onClick={() => anaesMut.mutate({ id: anaesCase!.id, data: anaesForm })}>
              {anaesMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Record
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* --- Operative Notes Dialog --- */}
      <Dialog open={opNotesOpen} onOpenChange={setOpNotesOpen}>
        <DialogContent className="bg-card border-border text-white max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-400" />
              Operative Notes
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">{opNotesCase?.procedure_name}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "incision",            label: "Incision",           colSpan: 2 },
              { key: "findings",            label: "Findings *",         colSpan: 2, textarea: true },
              { key: "procedure_performed", label: "Procedure Performed *", colSpan: 2, textarea: true },
              { key: "specimens_sent",      label: "Specimens Sent",     colSpan: 2 },
              { key: "closure_method",      label: "Closure Method" },
              { key: "blood_loss_ml",       label: "Blood Loss (mL)",    type: "number" },
              { key: "complications",       label: "Complications",      colSpan: 2, textarea: true },
              { key: "surgeon_notes",       label: "Surgeon Notes",      colSpan: 2, textarea: true },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", f.colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                {f.textarea
                  ? <Textarea
                      value={(opForm as any)[f.key] || ""}
                      onChange={e => setOpForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-20 resize-none"
                    />
                  : <Input
                      type={f.type || "text"}
                      value={(opForm as any)[f.key] || ""}
                      onChange={e => setOpForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-8"
                    />
                }
              </div>
            ))}
            <div className="col-span-2">
              <CheckItem
                label="Drains inserted"
                checked={opForm.drains_inserted}
                onChange={v => setOpForm(p => ({ ...p, drains_inserted: v }))}
              />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setOpNotesOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={opNotesMut.isPending || !opForm.findings || !opForm.procedure_performed}
              onClick={() => opNotesMut.mutate({ id: opNotesCase!.id, data: opForm })}>
              {opNotesMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Notes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* --- Post-Op Recovery Dialog --- */}
      <Dialog open={postOpOpen} onOpenChange={setPostOpOpen}>
        <DialogContent className="bg-card border-border text-white max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HeartPulse className="w-5 h-5 text-green-400" />
              Post-Op Recovery Record
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">{postOpCase?.procedure_name}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Recovery Location</Label>
              <Select value={postOpForm.recovery_location || ""}
                onValueChange={v => setPostOpForm(p => ({ ...p, recovery_location: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm">
                  <SelectValue placeholder="Select…" />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["PACU", "ICU", "Ward", "HDU", "Day Surgery"].map(l => (
                    <SelectItem key={l} value={l} className="">{l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Pain Score (0–10)</Label>
              <Input
                type="number" min={0} max={10}
                value={postOpForm.pain_score}
                onChange={e => setPostOpForm(p => ({ ...p, pain_score: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Follow-up Date</Label>
              <Input type="date"
                value={postOpForm.follow_up_date}
                onChange={e => setPostOpForm(p => ({ ...p, follow_up_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Wound Status</Label>
              <Input
                value={postOpForm.wound_status}
                onChange={e => setPostOpForm(p => ({ ...p, wound_status: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Post-Op Medications</Label>
              <Textarea
                value={postOpForm.post_op_medications}
                onChange={e => setPostOpForm(p => ({ ...p, post_op_medications: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-16 resize-none"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Complications</Label>
              <Textarea
                value={postOpForm.complications}
                onChange={e => setPostOpForm(p => ({ ...p, complications: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-16 resize-none"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Notes</Label>
              <Textarea
                value={postOpForm.notes}
                onChange={e => setPostOpForm(p => ({ ...p, notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-16 resize-none"
              />
            </div>
            <div className="col-span-2 space-y-2">
              {[
                ["vital_signs_stable",    "Vital signs stable"],
                ["nausea_vomiting",       "Nausea / vomiting present"],
                ["oxygen_therapy",        "Oxygen therapy required"],
                ["discharge_criteria_met","Discharge criteria met"],
              ].map(([key, label]) => (
                <CheckItem
                  key={key}
                  label={label}
                  checked={!!(postOpForm as any)[key]}
                  onChange={v => setPostOpForm(p => ({ ...p, [key]: v }))}
                />
              ))}
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setPostOpOpen(false)}>Cancel</Button>
            <Button className="bg-green-600 hover:bg-green-700"
              disabled={postOpMut.isPending}
              onClick={() => postOpMut.mutate({ id: postOpCase!.id, data: postOpForm })}>
              {postOpMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Record
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
