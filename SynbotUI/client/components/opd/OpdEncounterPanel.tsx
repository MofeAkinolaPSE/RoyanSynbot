import { useState } from "react";
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
  User, HeartPulse, FileText, FlaskConical, ScanLine, Share2, Scissors,
  PhoneCall, Pause, Play, LogOut, ExternalLink, Loader2, Copy, BedDouble, ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { FREQUENCY_OPTIONS, ROUTE_OPTIONS } from "@/lib/clinical-options";
import { ENCOUNTER_STATUS_COLORS } from "@/lib/encounter-status";

interface OpdEncounterPanelProps {
  encounter: {
    id: string | number;
    mrn: string;
    patient_id?: string | number;
    patient_name?: string;
    queue_number?: string;
    status: string;
  };
  onClose: () => void;
  initialTab?: string;
}

const STATUS_COLORS = ENCOUNTER_STATUS_COLORS;

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const d = new Date(dob);
  const age = Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000));
  return isNaN(age) ? "—" : `${age}y`;
}

const FREE_TEXT_TITLE = "__free_text__";

const emptyVitals = { bp_systolic: "", bp_diastolic: "", temperature: "", pulse: "", spo2: "", respiratory_rate: "", weight: "" };
const emptyNote = { note_title_id: "", note_type: "general", content: "" };
const emptyLab = { test_name: "", urgency: "routine", specimen_type: "", notes: "" };
const emptyRad = { modality: "xray", body_part: "", clinical_indication: "", urgency: "routine", notes: "" };
const emptyTheatre = { procedure_name: "", urgency: "elective", case_type: "", theatre_name: "", scheduled_date: "", start_time: "", surgeon_id: "", notes: "" };
const emptyRx = { drug_name: "", dosage: "", frequency: "twice daily", duration: "5 days", route: "oral", quantity: "1", unit: "tablet" };
const emptyReferral = { referring_to: "", reason: "", urgency: "routine", additional_notes: "", referring_doctor: "" };

export function OpdEncounterPanel({ encounter: initialEncounter, onClose, initialTab }: OpdEncounterPanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? "summary");

  const [vitalsForm, setVitalsForm] = useState({ ...emptyVitals });
  const [noteForm, setNoteForm] = useState({ ...emptyNote });
  const [labForm, setLabForm] = useState({ ...emptyLab });
  const [labSearch, setLabSearch] = useState("");
  const [radForm, setRadForm] = useState({ ...emptyRad });
  const [theatreForm, setTheatreForm] = useState({ ...emptyTheatre });
  const [rxForm, setRxForm] = useState({ ...emptyRx });
  const [drugSearch, setDrugSearch] = useState("");
  const [referralForm, setReferralForm] = useState({ ...emptyReferral });

  const encounterId = String(initialEncounter.id);

  // Live encounter (status/orders can change from actions taken inside this panel)
  const { data: encData, isLoading: encLoading } = useQuery({
    queryKey: ["opd-panel-encounter", encounterId],
    queryFn: () => api.hospital.queue.get(encounterId),
    refetchInterval: 15_000,
  });
  const encounter = encData?.encounter ?? initialEncounter;
  const labOrders: any[] = encData?.lab_orders ?? [];
  const prescriptions: any[] = encData?.prescriptions ?? [];

  const { data: profileData, isLoading: profileLoading } = useQuery({
    queryKey: ["opd-panel-profile", initialEncounter.mrn],
    queryFn: () => api.hospital.patients.profile(initialEncounter.mrn),
    enabled: !!initialEncounter.mrn,
  });
  const patient = profileData?.patient ?? profileData;
  const latestVitals = (profileData?.vitals ?? [])[0];

  const { data: noteTitlesData } = useQuery({
    queryKey: ["opd-panel-note-titles"],
    queryFn: () => api.hospital.clinical.listNoteTitles("OPD"),
    staleTime: 5 * 60_000,
  });
  const noteTitles: any[] = noteTitlesData?.titles ?? [];

  const { data: notesData, refetch: refetchNotes } = useQuery({
    queryKey: ["opd-panel-notes", encounterId],
    queryFn: () => api.hospital.queue.listNotes(encounterId),
  });
  const notes: any[] = notesData?.notes ?? [];

  const { data: problemsData } = useQuery({
    queryKey: ["opd-panel-problems", initialEncounter.patient_id],
    queryFn: () => api.hospital.clinical.listProblems(initialEncounter.patient_id!, "active"),
    enabled: !!initialEncounter.patient_id,
  });
  const activeProblems: any[] = problemsData?.problems ?? [];

  const { data: drugData } = useQuery({
    queryKey: ["opd-panel-drug-search", drugSearch],
    queryFn: () => api.hospital.clinical.searchDrugs(drugSearch),
    enabled: drugSearch.length >= 2,
    staleTime: 300_000,
  });
  const drugResults: any[] = drugData?.drugs ?? [];

  const { data: labCatalogData } = useQuery({
    queryKey: ["opd-panel-lab-catalog-search", labSearch],
    queryFn: () => api.hospital.lab.searchCatalog(labSearch),
    enabled: labSearch.length >= 2,
    staleTime: 300_000,
  });
  const labCatalogResults: any[] = labCatalogData?.tests ?? [];

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["opd-panel-encounter", encounterId] });
    void qc.invalidateQueries({ queryKey: ["opd-panel-notes", encounterId] });
    void qc.invalidateQueries({ queryKey: ["clinical-queue"] });
    void qc.invalidateQueries({ queryKey: ["doctor-ready-queue"] });
    void qc.invalidateQueries({ queryKey: ["doctor-encounters"] });
  };

  const vitalsMut = useMutation({
    mutationFn: () => api.hospital.nursing.recordVitals({
      patient_id: Number(initialEncounter.patient_id),
      encounter_id: Number(encounterId),
      bp_systolic:      vitalsForm.bp_systolic      ? Number(vitalsForm.bp_systolic)      : undefined,
      bp_diastolic:     vitalsForm.bp_diastolic     ? Number(vitalsForm.bp_diastolic)     : undefined,
      temperature:      vitalsForm.temperature      ? Number(vitalsForm.temperature)      : undefined,
      pulse:            vitalsForm.pulse            ? Number(vitalsForm.pulse)            : undefined,
      spo2:             vitalsForm.spo2             ? Number(vitalsForm.spo2)             : undefined,
      respiratory_rate: vitalsForm.respiratory_rate ? Number(vitalsForm.respiratory_rate) : undefined,
      weight:           vitalsForm.weight           ? Number(vitalsForm.weight)           : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Vitals recorded" });
      setVitalsForm({ ...emptyVitals });
      void qc.invalidateQueries({ queryKey: ["opd-panel-profile", initialEncounter.mrn] });
    },
    onError: (e: any) => toast({ title: "Failed to record vitals", description: e.message, variant: "destructive" }),
  });

  const noteMut = useMutation({
    mutationFn: () => api.hospital.queue.addNote(encounterId, {
      note_title_id: noteForm.note_title_id ? Number(noteForm.note_title_id) : undefined,
      note_type: noteForm.note_title_id ? undefined : noteForm.note_type,
      content: noteForm.content,
    }),
    onSuccess: () => {
      toast({ title: "Note saved" });
      setNoteForm({ ...emptyNote });
      void refetchNotes();
    },
    onError: (e: any) => toast({ title: "Failed to save note", description: e.message, variant: "destructive" }),
  });

  const labMut = useMutation({
    mutationFn: () => api.hospital.lab.placeOrder({
      patient_id: Number(initialEncounter.patient_id),
      encounter_id: Number(encounterId),
      test_name: labForm.test_name,
      urgency: labForm.urgency,
      sample_type: labForm.specimen_type || undefined,
      notes: labForm.notes || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Lab order placed" });
      setLabForm({ ...emptyLab });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to order lab test", description: e.message, variant: "destructive" }),
  });

  const radMut = useMutation({
    mutationFn: () => api.hospital.radiology.createOrder({
      patient_id: Number(initialEncounter.patient_id),
      encounter_id: Number(encounterId),
      modality: radForm.modality,
      body_part: radForm.body_part || undefined,
      clinical_indication: radForm.clinical_indication || undefined,
      urgency: radForm.urgency,
      notes: radForm.notes || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Radiology order placed" });
      setRadForm({ ...emptyRad });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to order imaging", description: e.message, variant: "destructive" }),
  });

  const { data: theatreCasesData } = useQuery({
    queryKey: ["opd-panel-theatre-cases", initialEncounter.patient_id],
    queryFn: () => api.hospital.theatre.listCases({ patient_id: Number(initialEncounter.patient_id) }),
    enabled: tab === "orders" && !!initialEncounter.patient_id,
  });
  const theatreCases: any[] = theatreCasesData?.cases ?? [];

  const theatreMut = useMutation({
    mutationFn: () => api.hospital.theatre.scheduleCase({
      encounter_id: Number(encounterId),
      patient_id: Number(initialEncounter.patient_id),
      procedure_name: theatreForm.procedure_name,
      urgency: theatreForm.urgency,
      case_type: theatreForm.case_type || undefined,
      theatre_name: theatreForm.theatre_name || undefined,
      scheduled_date: theatreForm.scheduled_date || undefined,
      start_time: theatreForm.start_time || undefined,
      surgeon_id: theatreForm.surgeon_id || undefined,
      notes: theatreForm.notes || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Surgery booked" });
      setTheatreForm({ ...emptyTheatre });
      void qc.invalidateQueries({ queryKey: ["opd-panel-theatre-cases", initialEncounter.patient_id] });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to book surgery", description: e.message, variant: "destructive" }),
  });

  const rxMut = useMutation({
    mutationFn: (overrideDuplicate = false) => api.hospital.pharmacy.createRx({
      encounter_id: Number(encounterId),
      patient_id: Number(initialEncounter.patient_id),
      drug_name: rxForm.drug_name,
      dosage: rxForm.dosage,
      frequency: rxForm.frequency,
      duration: rxForm.duration,
      route: rxForm.route,
      quantity: Number(rxForm.quantity) || 1,
      unit: rxForm.unit,
      ...(overrideDuplicate ? { override_duplicate: true } : {}),
    }),
    onSuccess: (res: any) => {
      if (res?.duplicate_alert) {
        toast({ title: "Duplicate prescription", description: res.message, variant: "destructive" });
        if (window.confirm(`${res.message}\n\nPrescribe anyway?`)) {
          rxMut.mutate(true);
        }
        return;
      }
      toast({ title: "Prescription written" });
      setRxForm({ ...emptyRx });
      setDrugSearch("");
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to write prescription", description: e.message, variant: "destructive" }),
  });

  const referralMut = useMutation({
    mutationFn: () => api.medicalRecords.generateReferral(encounterId, referralForm),
    onSuccess: () => {
      toast({ title: "Referral letter generated" });
      setReferralForm({ ...emptyReferral });
    },
    onError: (e: any) => toast({ title: "Failed to generate referral", description: e.message, variant: "destructive" }),
  });

  const callMut = useMutation({
    mutationFn: () => api.hospital.queue.callPatient(encounterId),
    onSuccess: () => { toast({ title: "Patient called" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const pauseMut = useMutation({
    mutationFn: () => api.hospital.queue.pauseConsultation(encounterId),
    onSuccess: () => { toast({ title: "Consultation paused" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const resumeMut = useMutation({
    mutationFn: () => api.hospital.queue.resumeConsultation(encounterId),
    onSuccess: () => { toast({ title: "Consultation resumed" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const endConsultMut = useMutation({
    mutationFn: () => api.hospital.queue.endConsultation(encounterId),
    onSuccess: (res: any) => {
      toast({ title: `Routed to ${String(res.routed_to).replace(/_/g, " ")}`, description: res.routing_reason });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Cannot end consultation", description: e.message, variant: "destructive" }),
  });

  const dischargeMut = useMutation({
    mutationFn: (summary: string) => api.hospital.queue.discharge(encounterId, { discharge_summary: summary }),
    onSuccess: () => { toast({ title: "Patient discharged" }); invalidateAll(); onClose(); },
    onError: (e: any) => toast({ title: "Cannot discharge", description: e.message, variant: "destructive" }),
  });

  const admitMut = useMutation({
    mutationFn: () => api.hospital.queue.open({
      patient_id: initialEncounter.patient_id, encounter_type: "inpatient", department: "IPD",
    }),
    onSuccess: () => { toast({ title: "Admission requested — inpatient encounter opened" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const status = encounter.status;
  const isPaused = !!encounter.paused_at;
  const canCall = status === "nurse_assessment";
  const canPause = status === "consulting" && !isPaused;
  const canResume = status === "consulting" && isPaused;
  const canEndConsult = ["consulting", "lab_ordered", "pharmacy_dispensing"].includes(status);
  const canDischarge = status === "billing_pending";

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        {profileLoading || encLoading ? (
          <LoadingSkeleton />
        ) : !patient ? (
          <div className="flex items-center justify-center h-40 text-sm text-muted-foreground">Patient not found.</div>
        ) : (
          <>
            {/* Header */}
            <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <User className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">{patient.first_name} {patient.last_name}</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <Badge variant="outline" className="text-xs font-mono">{patient.mrn}</Badge>
                    <span className="text-xs text-muted-foreground">{ageFromDob(patient.date_of_birth)} · {patient.gender ?? "—"}</span>
                    {patient.blood_group && <Badge className="text-xs bg-red-100 text-red-700 hover:bg-red-100">{patient.blood_group}</Badge>}
                    <Badge className={cn("text-xs capitalize", STATUS_COLORS[status] ?? "bg-slate-100 text-slate-700")}>
                      {(status ?? "—").replace(/_/g, " ")}{isPaused ? " · paused" : ""}
                    </Badge>
                    {encounter.queue_number && <span className="text-xs font-mono text-primary">{encounter.queue_number}</span>}
                  </div>
                  {patient.allergies && patient.allergies.length > 0 && (
                    <p className="text-xs text-destructive mt-1">⚠ Allergies: {Array.isArray(patient.allergies) ? patient.allergies.join(", ") : patient.allergies}</p>
                  )}
                </div>
              </div>
            </SheetHeader>

            {/* Tabs */}
            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="vitals">Vitals</TabsTrigger>
                <TabsTrigger value="notes">Notes</TabsTrigger>
                <TabsTrigger value="orders">Orders</TabsTrigger>
                <TabsTrigger value="prescribe">Prescribe</TabsTrigger>
                <TabsTrigger value="referral">Referral</TabsTrigger>
              </TabsList>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                {/* ── Summary ── */}
                <TabsContent value="summary" className="mt-0 space-y-4">
                  <section>
                    <SectionLabel icon={<HeartPulse className="h-3.5 w-3.5" />} label="Latest Vitals" />
                    {latestVitals ? (
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <VitalCell label="BP" value={latestVitals.bp_systolic && latestVitals.bp_diastolic ? `${latestVitals.bp_systolic}/${latestVitals.bp_diastolic}` : "—"} />
                        <VitalCell label="Temp" value={latestVitals.temperature ? `${latestVitals.temperature}°C` : "—"} />
                        <VitalCell label="Pulse" value={latestVitals.pulse ? `${latestVitals.pulse} bpm` : "—"} />
                        <VitalCell label="SpO₂" value={latestVitals.spo2 ? `${latestVitals.spo2}%` : "—"} />
                        <VitalCell label="RR" value={latestVitals.respiratory_rate ?? "—"} />
                        <VitalCell label="Weight" value={latestVitals.weight ? `${latestVitals.weight}kg` : "—"} />
                      </div>
                    ) : <p className="text-xs text-muted-foreground">No vitals recorded yet.</p>}
                    {latestVitals && (
                      <Button variant="link" size="sm" className="h-auto p-0 mt-1 text-xs gap-1"
                        onClick={() => {
                          const summary = `Vitals: BP ${latestVitals.bp_systolic ?? "—"}/${latestVitals.bp_diastolic ?? "—"}, Temp ${latestVitals.temperature ?? "—"}°C, Pulse ${latestVitals.pulse ?? "—"}bpm, SpO2 ${latestVitals.spo2 ?? "—"}%, RR ${latestVitals.respiratory_rate ?? "—"}`;
                          setNoteForm(f => ({ ...f, content: (f.content ? f.content + "\n" : "") + summary }));
                          setTab("notes");
                        }}>
                        <Copy className="h-3 w-3" /> Insert into note
                      </Button>
                    )}
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<FileText className="h-3.5 w-3.5" />} label="Clinical Snapshot" />
                    <div className="space-y-1 text-sm">
                      <p><span className="text-muted-foreground">Chief Complaint:</span> {encounter.chief_complaint || "—"}</p>
                      <p><span className="text-muted-foreground">Active Problems:</span> {activeProblems.length === 0 ? "None" : activeProblems.map((p: any) => p.description).join(", ")}</p>
                    </div>
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<FlaskConical className="h-3.5 w-3.5" />} label="Orders Summary" />
                    <p className="text-xs text-muted-foreground">
                      {labOrders.length} lab order(s) · {prescriptions.length} prescription(s)
                    </p>
                  </section>
                </TabsContent>

                {/* ── Vitals ── */}
                <TabsContent value="vitals" className="mt-0 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { key: "bp_systolic", label: "BP Systolic (mmHg)" },
                      { key: "bp_diastolic", label: "BP Diastolic (mmHg)" },
                      { key: "temperature", label: "Temperature (°C)", step: "0.1" },
                      { key: "pulse", label: "Pulse (bpm)" },
                      { key: "spo2", label: "SpO₂ (%)" },
                      { key: "respiratory_rate", label: "Respiratory Rate" },
                    ].map(f => (
                      <div key={f.key} className="space-y-1">
                        <Label>{f.label}</Label>
                        <Input type="number" step={f.step} value={(vitalsForm as any)[f.key]}
                          onChange={e => setVitalsForm(v => ({ ...v, [f.key]: e.target.value }))} />
                      </div>
                    ))}
                    <div className="col-span-2 space-y-1">
                      <Label>Weight (kg)</Label>
                      <Input type="number" step="0.1" value={vitalsForm.weight}
                        onChange={e => setVitalsForm(v => ({ ...v, weight: e.target.value }))} />
                    </div>
                  </div>
                  <Button className="w-full bg-teal-600 hover:bg-teal-700" disabled={vitalsMut.isPending} onClick={() => vitalsMut.mutate()}>
                    {vitalsMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save Vitals
                  </Button>
                </TabsContent>

                {/* ── Notes ── */}
                <TabsContent value="notes" className="mt-0 space-y-3">
                  {notes.length > 0 && (
                    <div className="space-y-2 max-h-32 overflow-y-auto rounded-md border p-2">
                      {notes.map((n: any) => (
                        <div key={n.id} className="text-xs border-b border-border/50 pb-1 last:border-0">
                          <span className="font-medium">{n.note_title || n.note_type}</span>
                          <span className="text-muted-foreground"> — {new Date(n.created_at).toLocaleString()}</span>
                          <p className="text-foreground line-clamp-2">{n.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="space-y-1">
                    <Label>Note Title</Label>
                    {noteTitles.length > 0 ? (
                      <Select value={noteForm.note_title_id || FREE_TEXT_TITLE} onValueChange={v => setNoteForm(f => ({ ...f, note_title_id: v === FREE_TEXT_TITLE ? "" : v }))}>
                        <SelectTrigger><SelectValue placeholder="Select a note title…" /></SelectTrigger>
                        <SelectContent>
                          {noteTitles.map((t: any) => <SelectItem key={t.id} value={String(t.id)}>{t.title}</SelectItem>)}
                          <SelectItem value={FREE_TEXT_TITLE}>Other / Free text…</SelectItem>
                        </SelectContent>
                      </Select>
                    ) : (
                      <Select value={noteForm.note_type} onValueChange={v => setNoteForm(f => ({ ...f, note_type: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="soap">SOAP</SelectItem>
                          <SelectItem value="general">General</SelectItem>
                          <SelectItem value="assessment">Assessment</SelectItem>
                          <SelectItem value="plan">Plan</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                  {noteTitles.length > 0 && !noteForm.note_title_id && (
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Free-text type</Label>
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
                  )}
                  <div className="space-y-1">
                    <Label>Content *</Label>
                    <Textarea rows={6} value={noteForm.content} onChange={e => setNoteForm(f => ({ ...f, content: e.target.value }))}
                      placeholder="Clinical note content..." className="font-mono text-sm" />
                  </div>
                  <Button className="w-full" disabled={!noteForm.content.trim() || noteMut.isPending} onClick={() => noteMut.mutate()}>
                    {noteMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save Note
                  </Button>
                </TabsContent>

                {/* ── Orders (Lab + Radiology) ── */}
                <TabsContent value="orders" className="mt-0 space-y-5">
                  <section className="space-y-2">
                    <SectionLabel icon={<FlaskConical className="h-3.5 w-3.5" />} label="Order Lab Test" />
                    <Input placeholder="Test name, e.g. CBC" value={labForm.test_name}
                      onChange={e => { setLabForm(f => ({ ...f, test_name: e.target.value })); setLabSearch(e.target.value); }} />
                    {labCatalogResults.length > 0 && (
                      <div className="rounded-md border max-h-28 overflow-y-auto">
                        {labCatalogResults.map((t: any) => (
                          <button key={t.id} className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted"
                            onClick={() => {
                              setLabForm(f => ({ ...f, test_name: t.name, specimen_type: f.specimen_type || t.specimen_type || "" }));
                              setLabSearch("");
                            }}>
                            {t.name} {t.abbreviation ? `(${t.abbreviation})` : ""} <span className="text-muted-foreground">· {t.category}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-2">
                      <Select value={labForm.urgency} onValueChange={v => setLabForm(f => ({ ...f, urgency: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="routine">Routine</SelectItem>
                          <SelectItem value="urgent">Urgent</SelectItem>
                          <SelectItem value="stat">STAT</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input placeholder="Specimen type (optional)" value={labForm.specimen_type} onChange={e => setLabForm(f => ({ ...f, specimen_type: e.target.value }))} />
                    </div>
                    <Button size="sm" className="w-full" disabled={!labForm.test_name.trim() || labMut.isPending} onClick={() => labMut.mutate()}>
                      {labMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Order Lab Test
                    </Button>
                    {labOrders.length > 0 && (
                      <ul className="text-xs text-muted-foreground space-y-0.5">
                        {labOrders.slice(0, 4).map((o: any) => <li key={o.id}>· {o.test_name} — {o.status}</li>)}
                      </ul>
                    )}
                  </section>
                  <Separator />
                  <section className="space-y-2">
                    <SectionLabel icon={<ScanLine className="h-3.5 w-3.5" />} label="Order Radiology" />
                    <div className="grid grid-cols-2 gap-2">
                      <Select value={radForm.modality} onValueChange={v => setRadForm(f => ({ ...f, modality: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {["xray","ultrasound","ct","mri","ecg","echo","fluoroscopy","mammography","endoscopy","other"].map(m => (
                            <SelectItem key={m} value={m} className="uppercase">{m}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select value={radForm.urgency} onValueChange={v => setRadForm(f => ({ ...f, urgency: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="routine">Routine</SelectItem>
                          <SelectItem value="urgent">Urgent</SelectItem>
                          <SelectItem value="stat">STAT</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <Input placeholder="Body part (optional)" value={radForm.body_part} onChange={e => setRadForm(f => ({ ...f, body_part: e.target.value }))} />
                    <Textarea rows={2} placeholder="Clinical indication" value={radForm.clinical_indication} onChange={e => setRadForm(f => ({ ...f, clinical_indication: e.target.value }))} />
                    <Button size="sm" className="w-full" disabled={radMut.isPending} onClick={() => radMut.mutate()}>
                      {radMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Order Imaging
                    </Button>
                  </section>
                  <Separator />
                  <section className="space-y-2">
                    <SectionLabel icon={<Scissors className="h-3.5 w-3.5" />} label="Book Surgery" />
                    <Input placeholder="Procedure name *" value={theatreForm.procedure_name}
                      onChange={e => setTheatreForm(f => ({ ...f, procedure_name: e.target.value }))} />
                    <div className="grid grid-cols-2 gap-2">
                      <Select value={theatreForm.urgency} onValueChange={v => setTheatreForm(f => ({ ...f, urgency: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {["elective", "urgent", "emergency"].map(u => (
                            <SelectItem key={u} value={u} className="capitalize">{u}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select value={theatreForm.case_type} onValueChange={v => setTheatreForm(f => ({ ...f, case_type: v }))}>
                        <SelectTrigger><SelectValue placeholder="Case type" /></SelectTrigger>
                        <SelectContent>
                          {["general", "regional", "local", "sedation"].map(t => (
                            <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <Input placeholder="Theatre (optional)" value={theatreForm.theatre_name}
                        onChange={e => setTheatreForm(f => ({ ...f, theatre_name: e.target.value }))} />
                      <Input placeholder="Surgeon (optional)" value={theatreForm.surgeon_id}
                        onChange={e => setTheatreForm(f => ({ ...f, surgeon_id: e.target.value }))} />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <Input type="date" value={theatreForm.scheduled_date}
                        onChange={e => setTheatreForm(f => ({ ...f, scheduled_date: e.target.value }))} />
                      <Input type="time" value={theatreForm.start_time}
                        onChange={e => setTheatreForm(f => ({ ...f, start_time: e.target.value }))} />
                    </div>
                    <Textarea rows={2} placeholder="Notes (optional)" value={theatreForm.notes}
                      onChange={e => setTheatreForm(f => ({ ...f, notes: e.target.value }))} />
                    <Button size="sm" className="w-full" disabled={!theatreForm.procedure_name.trim() || theatreMut.isPending} onClick={() => theatreMut.mutate()}>
                      {theatreMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Book Surgery
                    </Button>
                    {theatreCases.length > 0 && (
                      <ul className="text-xs text-muted-foreground space-y-0.5">
                        {theatreCases.slice(0, 4).map((c: any) => <li key={c.id}>· {c.procedure_name} — {c.status}</li>)}
                      </ul>
                    )}
                  </section>
                </TabsContent>

                {/* ── Prescribe ── */}
                <TabsContent value="prescribe" className="mt-0 space-y-3">
                  {prescriptions.length > 0 && (
                    <ul className="text-xs text-muted-foreground space-y-0.5">
                      {prescriptions.slice(0, 4).map((r: any) => <li key={r.id}>· {r.drug_name} {r.dosage} — {r.status}</li>)}
                    </ul>
                  )}
                  <div className="space-y-1">
                    <Label>Drug Name *</Label>
                    <Input value={rxForm.drug_name} onChange={e => { setRxForm(f => ({ ...f, drug_name: e.target.value })); setDrugSearch(e.target.value); }} placeholder="e.g. Amoxicillin 500mg" />
                    {drugResults.length > 0 && (
                      <div className="rounded-md border max-h-28 overflow-y-auto">
                        {drugResults.map((d: any) => (
                          <button key={d.id} className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted"
                            onClick={() => { setRxForm(f => ({ ...f, drug_name: `${d.generic_name}${d.strength ? " " + d.strength + (d.unit ?? "") : ""}`, dosage: d.strength ? `${d.strength}${d.unit ?? ""}` : f.dosage })); setDrugSearch(""); }}>
                            {d.generic_name} {d.strength}{d.unit} {d.brand_name ? `(${d.brand_name})` : ""}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1"><Label>Dosage *</Label><Input value={rxForm.dosage} onChange={e => setRxForm(f => ({ ...f, dosage: e.target.value }))} placeholder="e.g. 500mg" /></div>
                    <div className="space-y-1">
                      <Label>Frequency *</Label>
                      <Select value={rxForm.frequency} onValueChange={v => setRxForm(f => ({ ...f, frequency: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {FREQUENCY_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1"><Label>Duration</Label><Input value={rxForm.duration} onChange={e => setRxForm(f => ({ ...f, duration: e.target.value }))} /></div>
                    <div className="space-y-1">
                      <Label>Route</Label>
                      <Select value={rxForm.route} onValueChange={v => setRxForm(f => ({ ...f, route: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {ROUTE_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1"><Label>Quantity</Label><Input type="number" value={rxForm.quantity} onChange={e => setRxForm(f => ({ ...f, quantity: e.target.value }))} /></div>
                    <div className="space-y-1"><Label>Unit</Label><Input value={rxForm.unit} onChange={e => setRxForm(f => ({ ...f, unit: e.target.value }))} /></div>
                  </div>
                  <Button className="w-full" disabled={!rxForm.drug_name.trim() || !rxForm.dosage.trim() || !rxForm.frequency.trim() || rxMut.isPending} onClick={() => rxMut.mutate()}>
                    {rxMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Write Prescription
                  </Button>
                </TabsContent>

                {/* ── Referral ── */}
                <TabsContent value="referral" className="mt-0 space-y-3">
                  <div className="space-y-1">
                    <Label>Referring To *</Label>
                    <Input value={referralForm.referring_to} onChange={e => setReferralForm(f => ({ ...f, referring_to: e.target.value }))} placeholder="e.g. Cardiology Dept, Lagos Island General Hospital" />
                  </div>
                  <div className="space-y-1">
                    <Label>Reason for Referral *</Label>
                    <Textarea rows={3} value={referralForm.reason} onChange={e => setReferralForm(f => ({ ...f, reason: e.target.value }))} placeholder="Clinical reason for referral..." />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label>Urgency</Label>
                      <Select value={referralForm.urgency} onValueChange={v => setReferralForm(f => ({ ...f, urgency: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="routine">Routine</SelectItem>
                          <SelectItem value="urgent">Urgent</SelectItem>
                          <SelectItem value="emergency">Emergency</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1"><Label>Referring Doctor</Label><Input value={referralForm.referring_doctor} onChange={e => setReferralForm(f => ({ ...f, referring_doctor: e.target.value }))} placeholder="Dr. Name" /></div>
                  </div>
                  <div className="space-y-1">
                    <Label>Additional Notes</Label>
                    <Textarea rows={2} value={referralForm.additional_notes} onChange={e => setReferralForm(f => ({ ...f, additional_notes: e.target.value }))} />
                  </div>
                  <Button className="w-full gap-1.5" disabled={!referralForm.referring_to.trim() || !referralForm.reason.trim() || referralMut.isPending} onClick={() => referralMut.mutate()}>
                    {referralMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Share2 className="h-4 w-4" />}Generate Referral Letter
                  </Button>
                </TabsContent>
              </div>
            </Tabs>

            {/* Footer action bar */}
            <Separator className="shrink-0" />
            <div className="px-5 py-3 flex flex-wrap gap-2 shrink-0">
              {canCall && (
                <Button size="sm" variant="outline" className="gap-1.5" disabled={callMut.isPending} onClick={() => callMut.mutate()}>
                  <PhoneCall className="h-3.5 w-3.5" /> Call Patient
                </Button>
              )}
              {canPause && (
                <Button size="sm" variant="outline" className="gap-1.5" disabled={pauseMut.isPending} onClick={() => pauseMut.mutate()}>
                  <Pause className="h-3.5 w-3.5" /> Pause
                </Button>
              )}
              {canResume && (
                <Button size="sm" variant="outline" className="gap-1.5" disabled={resumeMut.isPending} onClick={() => resumeMut.mutate()}>
                  <Play className="h-3.5 w-3.5" /> Resume
                </Button>
              )}
              {canEndConsult && (
                <Button size="sm" className="gap-1.5 bg-blue-700 hover:bg-blue-800" disabled={endConsultMut.isPending} onClick={() => endConsultMut.mutate()}>
                  {endConsultMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ChevronRight className="h-3.5 w-3.5" />} End Consultation
                </Button>
              )}
              <Button size="sm" variant="outline" className="gap-1.5" disabled={admitMut.isPending} onClick={() => admitMut.mutate()}>
                <BedDouble className="h-3.5 w-3.5" /> Request Admission
              </Button>
              {canDischarge && (
                <Button size="sm" variant="outline" className="gap-1.5 border-green-500/40 text-green-600 hover:bg-green-500/10"
                  disabled={dischargeMut.isPending}
                  onClick={() => dischargeMut.mutate(window.prompt("Discharge summary:") || "Discharged from OPD.")}>
                  <LogOut className="h-3.5 w-3.5" /> Discharge
                </Button>
              )}
              <Button size="sm" variant="ghost" className="gap-1.5 ml-auto"
                onClick={() => { navigate(`/hospital/patients/${initialEncounter.mrn}`); onClose(); }}>
                <ExternalLink className="h-3.5 w-3.5" /> Open Full Chart
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

function VitalCell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border/60 px-2 py-1.5">
      <p className="text-[12px] text-muted-foreground uppercase">{label}</p>
      <p className="font-medium">{value}</p>
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
