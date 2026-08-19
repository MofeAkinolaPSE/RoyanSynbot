import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  User, Scissors, ClipboardList, Stethoscope, FileText, HeartPulse, History,
  ShieldCheck, ExternalLink, Loader2, CheckCircle2, XCircle, ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import {
  StatusBadge, UrgencyBadge, WorkflowProgress, DetailRow, CheckItem, elapsed,
} from "@/components/theatre/theatre-shared";

interface TheatreWorkspacePanelProps {
  case: {
    id: string | number;
    patient_id?: string | number;
    patient_mrn?: string;
    patient_name?: string;
    patient_gender?: string;
    patient_dob?: string;
    procedure_name?: string;
    theatre_name?: string;
    urgency?: string;
    status?: string;
    scheduled_date?: string;
    start_time?: string;
    surgeon_id?: string;
    created_at?: string;
  } & Record<string, any>;
  onClose: () => void;
  initialTab?: string;
}

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

export function TheatreWorkspacePanel({ case: initialCase, onClose, initialTab }: TheatreWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? "detail");

  const [preOpForm, setPreOpForm] = useState({ ...emptyPreOp, ...(initialCase.pre_op_checklist || {}) });
  const [anaesForm, setAnaesForm] = useState({ ...emptyAnaesthetic, ...(initialCase.anaesthetic_record || {}) });
  const [postOpForm, setPostOpForm] = useState({ ...emptyPostOp, ...(initialCase.post_op_notes || {}) });

  const [opForm, setOpForm] = useState({ ...emptyOperative });
  const [opMode, setOpMode] = useState<"view" | "edit" | "amend">("view");
  const [amendReason, setAmendReason] = useState("");

  const caseId = String(initialCase.id);

  const { data, isLoading } = useQuery({
    queryKey: ["theatre-panel-case", caseId],
    queryFn: () => api.hospital.theatre.getCase(caseId),
    refetchInterval: 15_000,
  });
  const c: typeof initialCase = { ...initialCase, ...(data?.case ?? {}) };
  const opHistory: any[] = c.operative_notes_history ?? [];

  const { data: historyData } = useQuery({
    queryKey: ["theatre-panel-patient-history", c.patient_id],
    queryFn: () => api.hospital.theatre.listCases({ patient_id: Number(c.patient_id) }),
    enabled: tab === "history" && !!c.patient_id,
  });
  const patientHistory: any[] = (historyData?.cases ?? []).filter((h: any) => String(h.id) !== caseId);

  useEffect(() => {
    if (opMode === "edit") {
      setOpForm({ ...emptyOperative, ...(c.operative_notes || {}) });
    } else if (opMode === "amend") {
      setOpForm({ ...emptyOperative });
      setAmendReason("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opMode]);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["theatre-panel-case", caseId] });
    void qc.invalidateQueries({ queryKey: ["theatre-cases"] });
    void qc.invalidateQueries({ queryKey: ["theatre-schedule"] });
    void qc.invalidateQueries({ queryKey: ["theatre-stats"] });
  };

  const advanceMut = useMutation({
    mutationFn: (status: string) => api.hospital.theatre.advanceStatus(caseId, { status }),
    onSuccess: (_res, status) => {
      toast({ title: `Status advanced to ${status.replace(/_/g, " ")}` });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: e?.message || "Transition failed", variant: "destructive" }),
  });

  const preOpMut = useMutation({
    mutationFn: () => api.hospital.theatre.submitPreOp(caseId, { ...preOpForm, notes: preOpForm.notes || undefined }),
    onSuccess: () => { toast({ title: "Pre-op checklist saved" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to save pre-op checklist", description: e.message, variant: "destructive" }),
  });

  const anaesMut = useMutation({
    mutationFn: () => api.hospital.theatre.submitAnaesthetic(caseId, {
      ...anaesForm,
      total_duration_minutes: anaesForm.total_duration_minutes ? Number(anaesForm.total_duration_minutes) : undefined,
      blood_loss_ml:          anaesForm.blood_loss_ml ? Number(anaesForm.blood_loss_ml) : undefined,
      fluids_given_ml:        anaesForm.fluids_given_ml ? Number(anaesForm.fluids_given_ml) : undefined,
    }),
    onSuccess: () => { toast({ title: "Anaesthetic record saved" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to save anaesthetic record", description: e.message, variant: "destructive" }),
  });

  const opNotesMut = useMutation({
    mutationFn: () => api.hospital.theatre.submitOperativeNotes(caseId, {
      ...opForm,
      blood_loss_ml: opForm.blood_loss_ml ? Number(opForm.blood_loss_ml) : undefined,
    }),
    onSuccess: () => { toast({ title: "Operative notes saved" }); setOpMode("view"); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to save operative notes", description: e.message, variant: "destructive" }),
  });

  const verifyMut = useMutation({
    mutationFn: () => api.hospital.theatre.verifyOperativeNotes(caseId, {}),
    onSuccess: () => { toast({ title: "Operative notes verified" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to verify", description: e.message, variant: "destructive" }),
  });

  const amendMut = useMutation({
    mutationFn: () => api.hospital.theatre.amendOperativeNotes(caseId, {
      ...opForm,
      blood_loss_ml: opForm.blood_loss_ml ? Number(opForm.blood_loss_ml) : undefined,
      amendment_reason: amendReason,
    }),
    onSuccess: () => { toast({ title: "Operative notes amended" }); setOpMode("view"); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to amend operative notes", description: e.message, variant: "destructive" }),
  });

  const postOpMut = useMutation({
    mutationFn: () => api.hospital.theatre.submitPostOp(caseId, {
      ...postOpForm,
      pain_score: postOpForm.pain_score !== "" ? Number(postOpForm.pain_score) : undefined,
    }),
    onSuccess: () => { toast({ title: "Post-op record saved" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to save post-op record", description: e.message, variant: "destructive" }),
  });

  const cancelMut = useMutation({
    mutationFn: () => api.hospital.theatre.advanceStatus(caseId, { status: "cancelled" }),
    onSuccess: () => { toast({ title: "Case cancelled" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to cancel case", description: e.message, variant: "destructive" }),
  });

  const status = c.status;
  const hasOpNotes   = !!c.operative_notes;
  const hasPostOp    = !!c.post_op_notes;
  const opVerified   = !!c.operative_notes_verified_at;

  const canStartPreOp      = status === "scheduled";
  const canMoveToTheatre   = status === "pre_op";
  const canRecordOpNotes   = status === "in_theatre" && !hasOpNotes;
  const canSendToRecovery  = status === "in_theatre" && hasOpNotes;
  const canRecordPostOp    = status === "recovery" && !hasPostOp;
  const canMarkCompleted   = status === "recovery" && hasPostOp;
  const canCancel          = ["scheduled", "pre_op"].includes(status ?? "");
  const canVerifyOpNotes   = hasOpNotes && !opVerified;
  const canAmendOpNotes    = opVerified;
  const showOpForm         = !hasOpNotes || opMode !== "view";
  const opFormValid        = !!opForm.findings.trim() && !!opForm.procedure_performed.trim();

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        {isLoading && !data ? (
          <LoadingSkeleton />
        ) : (
          <>
            {/* Header */}
            <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <Scissors className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">{c.procedure_name ?? "Theatre Case"}</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <span className="text-xs text-muted-foreground">{c.patient_name ?? `Patient ID ${c.patient_id}`}</span>
                    {c.patient_mrn && <Badge variant="outline" className="text-xs font-mono">{c.patient_mrn}</Badge>}
                    <UrgencyBadge urgency={c.urgency} />
                    <StatusBadge status={status} />
                  </div>
                  <p className="text-[13px] text-muted-foreground mt-1">Case #{c.id} · Booked {elapsed(c.created_at)} ago</p>
                </div>
              </div>
            </SheetHeader>

            {/* Tabs */}
            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="preop">Pre-Op</TabsTrigger>
                <TabsTrigger value="anaesthetic">Anaesthetic</TabsTrigger>
                <TabsTrigger value="opnotes">Op Notes</TabsTrigger>
                <TabsTrigger value="postop">Post-Op</TabsTrigger>
                <TabsTrigger value="history">History</TabsTrigger>
              </TabsList>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                {/* ── Detail ── */}
                <TabsContent value="detail" className="mt-0 space-y-4">
                  <section>
                    <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Patient" />
                    <DetailRow label="Name"   value={c.patient_name} />
                    <DetailRow label="MRN"    value={c.patient_mrn} mono />
                    <DetailRow label="Gender" value={c.patient_gender} />
                    <DetailRow label="DOB"    value={c.patient_dob} />
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<Scissors className="h-3.5 w-3.5" />} label="Case Details" />
                    <DetailRow label="Theatre"    value={c.theatre_name} />
                    <DetailRow label="Case Type"  value={c.case_type} />
                    <DetailRow label="Surgeon"    value={c.surgeon_id} />
                    <DetailRow label="Anaesthetist" value={c.anaesthetist_id} />
                    <DetailRow label="Scrub Nurse" value={c.scrub_nurse} />
                    <DetailRow label="Circulating Nurse" value={c.circulating_nurse} />
                    <DetailRow label="Scheduled" value={c.scheduled_date ? `${c.scheduled_date}${c.start_time ? " " + c.start_time : ""}` : undefined} />
                    <DetailRow label="Actual Start" value={c.actual_start_time ? new Date(c.actual_start_time).toLocaleString() : undefined} />
                    <DetailRow label="Actual End"   value={c.actual_end_time ? new Date(c.actual_end_time).toLocaleString() : undefined} />
                    <DetailRow label="Booked by"  value={c.booked_by} mono />
                    <DetailRow label="Notes"      value={c.notes} />
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<ClipboardList className="h-3.5 w-3.5" />} label="Workflow" />
                    <WorkflowProgress status={status} />
                  </section>
                </TabsContent>

                {/* ── Pre-Op ── */}
                <TabsContent value="preop" className="mt-0 space-y-3">
                  {c.pre_op_completed_at && (
                    <p className="text-[13px] text-muted-foreground">
                      Last saved by {c.pre_op_completed_by} · {elapsed(c.pre_op_completed_at)} ago
                    </p>
                  )}
                  <div className="grid grid-cols-1 gap-2.5">
                    {[
                      ["consent_signed",        "Consent signed by patient"],
                      ["site_marked",           "Surgical site marked"],
                      ["allergies_confirmed",   "Allergies confirmed"],
                      ["blood_group_confirmed", "Blood group confirmed"],
                      ["fasting_confirmed",     "Patient fasting confirmed"],
                      ["iv_access",             "IV access established"],
                      ["premedication_given",   "Premedication given"],
                      ["imaging_available",     "Imaging available in theatre"],
                      ["blood_available",       "Blood / blood products available"],
                      ["equipment_checked",     "Equipment checked by scrub nurse"],
                    ].map(([key, label]) => (
                      <CheckItem key={key} label={label}
                        checked={!!(preOpForm as any)[key]}
                        onChange={v => setPreOpForm(p => ({ ...p, [key]: v }))} />
                    ))}
                  </div>
                  <div className="space-y-1">
                    <Label>Notes</Label>
                    <Textarea rows={2} value={preOpForm.notes} onChange={e => setPreOpForm(p => ({ ...p, notes: e.target.value }))} />
                  </div>
                  <Button size="sm" className="w-full gap-1.5" disabled={preOpMut.isPending} onClick={() => preOpMut.mutate()}>
                    {preOpMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ClipboardList className="h-3.5 w-3.5" />}
                    Save Checklist
                  </Button>
                </TabsContent>

                {/* ── Anaesthetic ── */}
                <TabsContent value="anaesthetic" className="mt-0 space-y-3">
                  <div className="space-y-1">
                    <Label>Anaesthetic Type</Label>
                    <Select value={anaesForm.anaesthetic_type} onValueChange={v => setAnaesForm(p => ({ ...p, anaesthetic_type: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {["general", "regional", "spinal", "local", "sedation"].map(t => (
                          <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
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
                        <Label>{f.label}</Label>
                        <Input type={f.type || "text"} value={(anaesForm as any)[f.key] || ""}
                          onChange={e => setAnaesForm(p => ({ ...p, [f.key]: e.target.value }))} />
                      </div>
                    ))}
                  </div>
                  <div className="space-y-1">
                    <Label>Complications</Label>
                    <Textarea rows={2} value={anaesForm.complications} onChange={e => setAnaesForm(p => ({ ...p, complications: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label>Notes</Label>
                    <Textarea rows={2} value={anaesForm.notes} onChange={e => setAnaesForm(p => ({ ...p, notes: e.target.value }))} />
                  </div>
                  <Button size="sm" className="w-full gap-1.5" disabled={anaesMut.isPending} onClick={() => anaesMut.mutate()}>
                    {anaesMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Stethoscope className="h-3.5 w-3.5" />}
                    Save Anaesthetic Record
                  </Button>
                </TabsContent>

                {/* ── Op Notes ── */}
                <TabsContent value="opnotes" className="mt-0 space-y-3">
                  {!showOpForm ? (
                    <section className="space-y-3">
                      {opVerified ? (
                        <div className="rounded-md border border-green-500/30 bg-green-500/5 p-3 space-y-1">
                          <div className="flex items-center gap-1.5 text-green-700 dark:text-green-400 text-sm font-medium">
                            <CheckCircle2 className="h-4 w-4" /> Verified
                          </div>
                          <p className="text-xs text-muted-foreground">
                            By {c.operative_notes_verified_by} · {new Date(c.operative_notes_verified_at).toLocaleString()}
                          </p>
                        </div>
                      ) : (
                        <div className="rounded-md border border-yellow-500/30 bg-yellow-500/5 p-2 text-xs text-yellow-700 dark:text-yellow-400">
                          Awaiting verification
                        </div>
                      )}
                      {c.operative_notes_amendment_reason && (
                        <div className="rounded-md border border-orange-500/30 bg-orange-500/5 p-2 text-xs text-orange-500">
                          Amended: {c.operative_notes_amendment_reason}
                        </div>
                      )}
                      <div className="rounded-md border p-3 space-y-2 text-sm">
                        {c.operative_notes?.incision && <div><p className="text-xs text-muted-foreground mb-0.5">Incision</p><p>{c.operative_notes.incision}</p></div>}
                        <div><p className="text-xs text-muted-foreground mb-0.5">Findings</p><p className="whitespace-pre-wrap">{c.operative_notes?.findings}</p></div>
                        <div><p className="text-xs text-muted-foreground mb-0.5">Procedure Performed</p><p className="whitespace-pre-wrap">{c.operative_notes?.procedure_performed}</p></div>
                        {c.operative_notes?.specimens_sent && <div><p className="text-xs text-muted-foreground mb-0.5">Specimens Sent</p><p>{c.operative_notes.specimens_sent}</p></div>}
                        {c.operative_notes?.closure_method && <div><p className="text-xs text-muted-foreground mb-0.5">Closure Method</p><p>{c.operative_notes.closure_method}</p></div>}
                        {c.operative_notes?.blood_loss_ml != null && <div><p className="text-xs text-muted-foreground mb-0.5">Blood Loss</p><p>{c.operative_notes.blood_loss_ml} mL</p></div>}
                        <p className="text-xs">Drains inserted: {c.operative_notes?.drains_inserted ? "Yes" : "No"}</p>
                        {c.operative_notes?.complications && <div><p className="text-xs text-muted-foreground mb-0.5">Complications</p><p className="whitespace-pre-wrap">{c.operative_notes.complications}</p></div>}
                        {c.operative_notes?.surgeon_notes && <div><p className="text-xs text-muted-foreground mb-0.5">Surgeon Notes</p><p className="whitespace-pre-wrap">{c.operative_notes.surgeon_notes}</p></div>}
                        <p className="text-[13px] text-muted-foreground">Recorded by {c.operative_notes_by}</p>
                      </div>
                      {!opVerified && (
                        <Button size="sm" variant="outline" className="w-full" onClick={() => setOpMode("edit")}>Edit Notes</Button>
                      )}
                      {opVerified && (
                        <Button size="sm" variant="ghost" className="w-full text-orange-500" onClick={() => setOpMode("amend")}>Amend Notes…</Button>
                      )}
                    </section>
                  ) : (
                    <section className="space-y-3">
                      {opMode === "amend" && (
                        <div className="rounded-md border border-orange-500/30 bg-orange-500/5 p-2 text-xs text-orange-500">
                          Amending verified operative notes — the prior version stays on record and this creates a new, unverified version.
                        </div>
                      )}
                      {[
                        { key: "incision",            label: "Incision" },
                        { key: "findings",             label: "Findings *", textarea: true },
                        { key: "procedure_performed",  label: "Procedure Performed *", textarea: true },
                        { key: "specimens_sent",       label: "Specimens Sent" },
                        { key: "closure_method",       label: "Closure Method" },
                        { key: "blood_loss_ml",        label: "Blood Loss (mL)", type: "number" },
                        { key: "complications",        label: "Complications", textarea: true },
                        { key: "surgeon_notes",        label: "Surgeon Notes", textarea: true },
                      ].map(f => (
                        <div key={f.key} className="space-y-1">
                          <Label>{f.label}</Label>
                          {f.textarea
                            ? <Textarea rows={3} value={(opForm as any)[f.key] || ""} onChange={e => setOpForm(p => ({ ...p, [f.key]: e.target.value }))} />
                            : <Input type={f.type || "text"} value={(opForm as any)[f.key] || ""} onChange={e => setOpForm(p => ({ ...p, [f.key]: e.target.value }))} />
                          }
                        </div>
                      ))}
                      <CheckItem label="Drains inserted" checked={opForm.drains_inserted}
                        onChange={v => setOpForm(p => ({ ...p, drains_inserted: v }))} />
                      {opMode === "amend" && (
                        <div className="space-y-1">
                          <Label>Amendment Reason *</Label>
                          <Textarea rows={2} value={amendReason} onChange={e => setAmendReason(e.target.value)}
                            placeholder="Why are these notes being corrected?" />
                        </div>
                      )}
                      <div className="flex gap-2">
                        {hasOpNotes && (
                          <Button size="sm" variant="outline" className="flex-1" onClick={() => setOpMode("view")}>Cancel</Button>
                        )}
                        <Button size="sm" className="flex-1 gap-1.5"
                          disabled={!opFormValid || (opMode === "amend" ? !amendReason.trim() || amendMut.isPending : opNotesMut.isPending)}
                          onClick={() => opMode === "amend" ? amendMut.mutate() : opNotesMut.mutate()}>
                          {(opMode === "amend" ? amendMut.isPending : opNotesMut.isPending) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                          {opMode === "amend" ? "Save Amendment" : "Save Notes"}
                        </Button>
                      </div>
                    </section>
                  )}
                </TabsContent>

                {/* ── Post-Op ── */}
                <TabsContent value="postop" className="mt-0 space-y-3">
                  {c.post_op_at && (
                    <p className="text-[13px] text-muted-foreground">
                      Last saved by {c.post_op_by} · {elapsed(c.post_op_at)} ago
                    </p>
                  )}
                  <div className="space-y-1">
                    <Label>Recovery Location</Label>
                    <Select value={postOpForm.recovery_location || ""} onValueChange={v => setPostOpForm(p => ({ ...p, recovery_location: v }))}>
                      <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
                      <SelectContent>
                        {["PACU", "ICU", "Ward", "HDU", "Day Surgery"].map(l => <SelectItem key={l} value={l}>{l}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label>Pain Score (0–10)</Label>
                      <Input type="number" min={0} max={10} value={postOpForm.pain_score}
                        onChange={e => setPostOpForm(p => ({ ...p, pain_score: e.target.value }))} />
                    </div>
                    <div className="space-y-1">
                      <Label>Follow-up Date</Label>
                      <Input type="date" value={postOpForm.follow_up_date}
                        onChange={e => setPostOpForm(p => ({ ...p, follow_up_date: e.target.value }))} />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label>Wound Status</Label>
                    <Input value={postOpForm.wound_status} onChange={e => setPostOpForm(p => ({ ...p, wound_status: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label>Post-Op Medications</Label>
                    <Textarea rows={2} value={postOpForm.post_op_medications} onChange={e => setPostOpForm(p => ({ ...p, post_op_medications: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label>Complications</Label>
                    <Textarea rows={2} value={postOpForm.complications} onChange={e => setPostOpForm(p => ({ ...p, complications: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label>Notes</Label>
                    <Textarea rows={2} value={postOpForm.notes} onChange={e => setPostOpForm(p => ({ ...p, notes: e.target.value }))} />
                  </div>
                  <div className="space-y-2">
                    {[
                      ["vital_signs_stable",     "Vital signs stable"],
                      ["nausea_vomiting",        "Nausea / vomiting present"],
                      ["oxygen_therapy",         "Oxygen therapy required"],
                      ["discharge_criteria_met", "Discharge criteria met"],
                    ].map(([key, label]) => (
                      <CheckItem key={key} label={label} checked={!!(postOpForm as any)[key]}
                        onChange={v => setPostOpForm(p => ({ ...p, [key]: v }))} />
                    ))}
                  </div>
                  <Button size="sm" className="w-full gap-1.5" disabled={postOpMut.isPending} onClick={() => postOpMut.mutate()}>
                    {postOpMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <HeartPulse className="h-3.5 w-3.5" />}
                    Save Post-Op Record
                  </Button>
                </TabsContent>

                {/* ── History ── */}
                <TabsContent value="history" className="mt-0 space-y-4">
                  <section className="space-y-2">
                    <SectionLabel icon={<History className="h-3.5 w-3.5" />} label="Operative Notes Amendment Trail" />
                    {opHistory.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No amendments — current operative notes are the original.</p>
                    ) : (
                      <div className="space-y-2">
                        {opHistory.map((v: any, i: number) => (
                          <div key={i} className="rounded-md border p-2 text-xs space-y-0.5">
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{v.operative_notes?.procedure_performed ?? "—"}</span>
                              {v.verified_at
                                ? <Badge variant="outline" className="text-[12px] text-green-700 dark:text-green-400 border-green-500/30">was verified</Badge>
                                : <Badge variant="outline" className="text-[12px] text-yellow-700 dark:text-yellow-400 border-yellow-500/30">unverified</Badge>}
                            </div>
                            <p className="text-muted-foreground">{elapsed(v.superseded_at)} ago, by {v.operative_notes_by}</p>
                            {v.amendment_reason && <p className="text-orange-500">Amended: {v.amendment_reason}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                  <Separator />
                  <section className="space-y-2">
                    <SectionLabel icon={<Scissors className="h-3.5 w-3.5" />} label="Patient's Other Surgical Cases" />
                    {patientHistory.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No other theatre cases for this patient.</p>
                    ) : (
                      <ul className="text-xs text-muted-foreground space-y-1">
                        {patientHistory.slice(0, 8).map((h: any) => (
                          <li key={h.id} className="flex justify-between">
                            <span>{h.procedure_name}</span>
                            <span>{h.status?.replace(/_/g, " ")}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                </TabsContent>
              </div>
            </Tabs>

            {/* Footer action bar */}
            <Separator className="shrink-0" />
            <div className="px-5 py-3 flex flex-wrap gap-2 shrink-0">
              {canStartPreOp && (
                <Button size="sm" className="gap-1.5" disabled={advanceMut.isPending} onClick={() => advanceMut.mutate("pre_op")}>
                  {advanceMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ChevronRight className="h-3.5 w-3.5" />} Start Pre-Op
                </Button>
              )}
              {canMoveToTheatre && (
                <Button size="sm" className="gap-1.5" disabled={advanceMut.isPending} onClick={() => advanceMut.mutate("in_theatre")}>
                  {advanceMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ChevronRight className="h-3.5 w-3.5" />} Move to Theatre
                </Button>
              )}
              {canRecordOpNotes && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => { setTab("opnotes"); setOpMode("edit"); }}>
                  <FileText className="h-3.5 w-3.5" /> Record Operative Notes
                </Button>
              )}
              {canSendToRecovery && (
                <Button size="sm" className="gap-1.5" disabled={advanceMut.isPending} onClick={() => advanceMut.mutate("recovery")}>
                  {advanceMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ChevronRight className="h-3.5 w-3.5" />} Send to Recovery
                </Button>
              )}
              {canRecordPostOp && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setTab("postop")}>
                  <HeartPulse className="h-3.5 w-3.5" /> Record Post-Op Notes
                </Button>
              )}
              {canMarkCompleted && (
                <Button size="sm" className="gap-1.5 bg-green-600 hover:bg-green-700" disabled={advanceMut.isPending} onClick={() => advanceMut.mutate("completed")}>
                  {advanceMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />} Mark Completed
                </Button>
              )}
              {canVerifyOpNotes && (
                <Button size="sm" className="gap-1.5 bg-green-600 hover:bg-green-700" disabled={verifyMut.isPending}
                  onClick={() => { if (window.confirm("Verify these operative notes? Once verified they can only be corrected via an amendment.")) verifyMut.mutate(); }}>
                  {verifyMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />} Verify Operative Notes
                </Button>
              )}
              {canAmendOpNotes && opMode === "view" && (
                <Button size="sm" variant="outline" className="gap-1.5 text-orange-500 border-orange-500/30"
                  onClick={() => { setTab("opnotes"); setOpMode("amend"); }}>
                  Amend Operative Notes
                </Button>
              )}
              {canCancel && (
                <Button size="sm" variant="outline" className="gap-1.5 text-red-500 border-red-500/30 hover:bg-red-500/10"
                  disabled={cancelMut.isPending}
                  onClick={() => { if (window.confirm("Cancel this theatre case?")) cancelMut.mutate(); }}>
                  <XCircle className="h-3.5 w-3.5" /> Cancel
                </Button>
              )}
              <Button size="sm" variant="ghost" className="gap-1.5 ml-auto"
                disabled={!c.patient_mrn}
                onClick={() => { if (c.patient_mrn) { navigate(`/hospital/patients/${c.patient_mrn}`); onClose(); } }}>
                <ExternalLink className="h-3.5 w-3.5" /> Open Patient Record
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function SectionLabel({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 rounded-full" />
        <div className="space-y-2 flex-1"><Skeleton className="h-4 w-40" /><Skeleton className="h-3 w-28" /></div>
      </div>
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
