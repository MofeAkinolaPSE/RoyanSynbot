import { Fragment, useState } from "react";
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
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  User, HeartPulse, ClipboardList, Plus, CheckCircle2,
  ExternalLink, Loader2, Thermometer, Activity, AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AllergyBanner } from "@/components/AllergyBanner";
import { cn } from "@/lib/utils";
import {
  fmtDate, elapsed, PainBadge, MarStatusBadge, CarePlanStatusBadge,
  CarePlanPriorityBadge, FluidTypeBadge, DetailRow,
} from "@/components/nursing/nursing-shared";

interface NursingWorkspacePanelProps {
  encounter: {
    id: string | number;
    patient_id: string | number;
    patient_mrn?: string;
    patient_name?: string;
    patient_gender?: string;
    patient_dob?: string;
    queue_number?: string;
    department?: string;
    status?: string;
    chief_complaint?: string;
    created_at?: string;
  } & Record<string, any>;
  onClose: () => void;
  initialTab?: string;
}

const emptyVitals = {
  temperature: "", pulse: "", respiratory_rate: "", bp_systolic: "", bp_diastolic: "",
  spo2: "", weight: "", height: "", blood_glucose: "", pain_score: "", gcs: "", notes: "",
};
const emptyFluid = { fluid_type: "intake", route: "", volume_ml: "", fluid_name: "", notes: "" };
const emptyPlan = { problem: "", goal: "", interventions: "", priority: "medium", assigned_to: "" };
const emptyMar = { drug_name: "", dose: "", route: "oral", status: "administered", notes: "", override_reason: "" };
const emptyMarUpdate = { status: "administered", override_reason: "", notes: "" };

export function NursingWorkspacePanel({ encounter: initialEncounter, onClose, initialTab }: NursingWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? "detail");
  const [historyScope, setHistoryScope] = useState<"encounter" | "patient">("encounter");

  const [vitalsFormOpen, setVitalsFormOpen] = useState(false);
  const [vitalsForm, setVitalsForm] = useState({ ...emptyVitals });
  const [fluidFormOpen, setFluidFormOpen] = useState(false);
  const [fluidForm, setFluidForm] = useState({ ...emptyFluid });
  const [planFormOpen, setPlanFormOpen] = useState(false);
  const [planForm, setPlanForm] = useState({ ...emptyPlan });
  const [marFormOpen, setMarFormOpen] = useState(false);
  const [marForm, setMarForm] = useState({ ...emptyMar });
  const [editingMarId, setEditingMarId] = useState<number | null>(null);
  const [marUpdateForm, setMarUpdateForm] = useState({ ...emptyMarUpdate });

  const patientId = initialEncounter.patient_id;
  const encounterId = String(initialEncounter.id);

  const { data: vitalsData, isLoading: vitalsLoading } = useQuery({
    queryKey: ["nursing-panel-vitals", patientId, encounterId, historyScope],
    queryFn: () => api.hospital.nursing.listVitals(patientId, historyScope === "encounter" ? encounterId : undefined),
    staleTime: 15_000,
  });
  const vitalsList: any[] = vitalsData?.vitals ?? [];
  const allergies: string[] = (vitalsData?.allergies ?? []).map((a: any) => a.allergen).filter(Boolean);
  const latestVitals = vitalsList[0];

  const { data: fluidData, isLoading: fluidLoading } = useQuery({
    queryKey: ["nursing-panel-fluid", encounterId],
    queryFn: () => api.hospital.nursing.getFluidBalance(encounterId),
    enabled: tab === "fluid",
    staleTime: 15_000,
  });
  const fluidEntries: any[] = fluidData?.entries ?? [];

  const { data: plansData, isLoading: plansLoading } = useQuery({
    queryKey: ["nursing-panel-plans", patientId, encounterId, historyScope],
    queryFn: () => api.hospital.nursing.listCarePlans(patientId, historyScope === "encounter" ? encounterId : undefined),
    enabled: tab === "plans",
    staleTime: 30_000,
  });
  const carePlans: any[] = plansData?.care_plans ?? [];

  const { data: marData, isLoading: marLoading } = useQuery({
    queryKey: ["nursing-panel-mar", encounterId],
    queryFn: () => api.hospital.nursing.listMAR(encounterId),
    enabled: tab === "mar",
    staleTime: 15_000,
  });
  const marEntries: any[] = marData?.mar ?? [];
  const marSummary: Record<string, number> = marData?.summary ?? {};

  const invalidateVitals = () => void qc.invalidateQueries({ queryKey: ["nursing-panel-vitals", patientId] });
  const invalidateFluid  = () => void qc.invalidateQueries({ queryKey: ["nursing-panel-fluid", encounterId] });
  const invalidatePlans  = () => void qc.invalidateQueries({ queryKey: ["nursing-panel-plans", patientId] });
  const invalidateMar    = () => void qc.invalidateQueries({ queryKey: ["nursing-panel-mar", encounterId] });

  const vitalsMut = useMutation({
    mutationFn: () => api.hospital.nursing.recordVitals({
      ...Object.fromEntries(Object.entries(vitalsForm).filter(([, v]) => v !== "" && v !== null)),
      patient_id: Number(patientId),
      encounter_id: Number(encounterId),
    }),
    onSuccess: () => {
      toast({ title: "Vitals recorded" });
      setVitalsForm({ ...emptyVitals });
      setVitalsFormOpen(false);
      invalidateVitals();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const fluidMut = useMutation({
    mutationFn: () => api.hospital.nursing.logFluid({
      ...fluidForm,
      patient_id: Number(patientId),
      encounter_id: Number(encounterId),
      volume_ml: Number(fluidForm.volume_ml),
    }),
    onSuccess: () => {
      toast({ title: "Fluid entry logged" });
      setFluidForm({ ...emptyFluid });
      setFluidFormOpen(false);
      invalidateFluid();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const planMut = useMutation({
    mutationFn: () => api.hospital.nursing.createCarePlan({
      ...planForm,
      patient_id: Number(patientId),
      encounter_id: Number(encounterId),
    }),
    onSuccess: () => {
      toast({ title: "Care plan created" });
      setPlanForm({ ...emptyPlan });
      setPlanFormOpen(false);
      invalidatePlans();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const resolvePlanMut = useMutation({
    mutationFn: (planId: number) => api.hospital.nursing.updateCarePlan(planId, { status: "resolved" }),
    onSuccess: () => { toast({ title: "Care plan resolved" }); invalidatePlans(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const marMut = useMutation({
    mutationFn: () => api.hospital.nursing.recordMAR({
      ...Object.fromEntries(Object.entries(marForm).filter(([, v]) => v !== "" && v !== null)),
      encounter_id: Number(encounterId),
      patient_id: Number(patientId),
    }),
    onSuccess: () => {
      toast({ title: "MAR entry recorded" });
      setMarForm({ ...emptyMar });
      setMarFormOpen(false);
      invalidateMar();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const marUpdateMut = useMutation({
    mutationFn: (vars: { entryId: number; status: string; override_reason?: string; notes?: string }) =>
      api.hospital.nursing.updateMAR(vars.entryId, {
        status: vars.status,
        override_reason: vars.override_reason || undefined,
        notes: vars.notes || undefined,
      }),
    onSuccess: () => {
      toast({ title: "MAR entry updated" });
      setEditingMarId(null);
      invalidateMar();
    },
    onError: (e: any) => toast({ title: "Failed to update MAR entry", description: e.message, variant: "destructive" }),
  });

  const marUpdateInvalid = (marUpdateForm.status === "held" || marUpdateForm.status === "refused") && !marUpdateForm.override_reason.trim();

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <HeartPulse className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle className="text-base leading-tight">{initialEncounter.patient_name ?? `Patient ID ${patientId}`}</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                {initialEncounter.patient_mrn && <Badge variant="outline" className="text-xs font-mono">{initialEncounter.patient_mrn}</Badge>}
                {initialEncounter.department && <Badge variant="outline" className="text-xs">{initialEncounter.department}</Badge>}
                {initialEncounter.status && <Badge variant="outline" className="text-xs capitalize">{initialEncounter.status.replace(/_/g, " ")}</Badge>}
              </div>
              <p className="text-[13px] text-muted-foreground mt-1">
                {initialEncounter.queue_number ?? `Encounter #${encounterId}`} · Opened {elapsed(initialEncounter.created_at)} ago
              </p>
            </div>
          </div>
          {allergies.length > 0 && <div className="mt-3"><AllergyBanner allergies={allergies} /></div>}
        </SheetHeader>

        <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
          <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
            <TabsTrigger value="detail">Detail</TabsTrigger>
            <TabsTrigger value="vitals">Vitals</TabsTrigger>
            <TabsTrigger value="fluid">Fluid Balance</TabsTrigger>
            <TabsTrigger value="plans">Care Plans</TabsTrigger>
            <TabsTrigger value="mar">MAR</TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {/* ── Detail ── */}
            <TabsContent value="detail" className="mt-0 space-y-4">
              <section>
                <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Patient" />
                <DetailRow label="Name"   value={initialEncounter.patient_name} />
                <DetailRow label="MRN"    value={initialEncounter.patient_mrn} mono />
                <DetailRow label="Gender" value={initialEncounter.patient_gender} />
                <DetailRow label="DOB"    value={initialEncounter.patient_dob} />
              </section>
              <Separator />
              <section>
                <SectionLabel icon={<ClipboardList className="h-3.5 w-3.5" />} label="Encounter" />
                <DetailRow label="Queue #"     value={initialEncounter.queue_number} mono />
                <DetailRow label="Department"  value={initialEncounter.department} />
                <DetailRow label="Status"      value={initialEncounter.status?.replace(/_/g, " ")} />
                <DetailRow label="Chief Complaint" value={initialEncounter.chief_complaint} />
                <DetailRow label="Opened"      value={initialEncounter.created_at ? fmtDate(initialEncounter.created_at) : undefined} />
              </section>
              {latestVitals && (
                <>
                  <Separator />
                  <section>
                    <SectionLabel icon={<Activity className="h-3.5 w-3.5" />} label="Latest Vitals" />
                    <div className="grid grid-cols-2 gap-2">
                      <VitalMini icon={<Thermometer className="h-3.5 w-3.5" />} label="Temp" value={latestVitals.temperature != null ? `${latestVitals.temperature}°C` : "—"} color="text-orange-400" />
                      <VitalMini icon={<HeartPulse className="h-3.5 w-3.5" />} label="Pulse" value={latestVitals.pulse != null ? `${latestVitals.pulse} bpm` : "—"} color="text-red-400" />
                      <VitalMini icon={<Activity className="h-3.5 w-3.5" />} label="SpO₂" value={latestVitals.spo2 != null ? `${latestVitals.spo2}%` : "—"} color={Number(latestVitals.spo2) < 95 ? "text-red-400" : "text-green-400"} />
                      <VitalMini icon={<AlertTriangle className="h-3.5 w-3.5" />} label="Pain" value={latestVitals.pain_score != null ? `${latestVitals.pain_score}/10` : "—"} color={Number(latestVitals.pain_score) >= 7 ? "text-red-400" : "text-yellow-400"} />
                    </div>
                  </section>
                </>
              )}
            </TabsContent>

            {/* ── Vitals ── */}
            <TabsContent value="vitals" className="mt-0 space-y-3">
              <ScopeToggle scope={historyScope} onChange={setHistoryScope} />
              {vitalsLoading ? (
                <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
              ) : vitalsList.length === 0 ? (
                <p className="text-xs text-muted-foreground">No vitals recorded yet.</p>
              ) : (
                <div className="rounded-md border overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Time</TableHead>
                        <TableHead className="text-xs">Temp</TableHead>
                        <TableHead className="text-xs">Pulse</TableHead>
                        <TableHead className="text-xs">BP</TableHead>
                        <TableHead className="text-xs">SpO₂</TableHead>
                        <TableHead className="text-xs">Pain</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {vitalsList.map((v: any) => (
                        <TableRow key={v.id}>
                          <TableCell className="text-[13px] text-muted-foreground whitespace-nowrap">{fmtDate(v.recorded_at)}</TableCell>
                          <TableCell className="text-xs">{v.temperature != null ? `${v.temperature}°C` : "—"}</TableCell>
                          <TableCell className="text-xs">{v.pulse != null ? `${v.pulse}` : "—"}</TableCell>
                          <TableCell className="text-xs font-mono">{v.bp_systolic != null ? `${v.bp_systolic}/${v.bp_diastolic}` : "—"}</TableCell>
                          <TableCell className={cn("text-xs font-semibold", Number(v.spo2) < 95 ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400")}>{v.spo2 != null ? `${v.spo2}%` : "—"}</TableCell>
                          <TableCell><PainBadge score={v.pain_score} /></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {!vitalsFormOpen ? (
                <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => setVitalsFormOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> Record Vitals
                </Button>
              ) : (
                <section className="space-y-2 border-t pt-3">
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { key: "temperature",      label: "Temp (°C)",      placeholder: "37.0" },
                      { key: "pulse",            label: "Pulse (bpm)",    placeholder: "80" },
                      { key: "respiratory_rate", label: "RR (/min)",      placeholder: "16" },
                      { key: "bp_systolic",      label: "BP Systolic",    placeholder: "120" },
                      { key: "bp_diastolic",     label: "BP Diastolic",   placeholder: "80" },
                      { key: "spo2",             label: "SpO₂ (%)",       placeholder: "98" },
                      { key: "weight",           label: "Weight (kg)",    placeholder: "70" },
                      { key: "height",           label: "Height (cm)",    placeholder: "170" },
                      { key: "blood_glucose",    label: "Glucose mmol/L", placeholder: "5.5" },
                      { key: "pain_score",       label: "Pain 0-10",      placeholder: "0" },
                      { key: "gcs",              label: "GCS (3-15)",     placeholder: "15" },
                    ].map(f => (
                      <div key={f.key} className="space-y-1">
                        <Label className="text-xs">{f.label}</Label>
                        <Input type="number" placeholder={f.placeholder} className="h-8 text-sm"
                          value={(vitalsForm as any)[f.key]}
                          onChange={e => setVitalsForm(p => ({ ...p, [f.key]: e.target.value }))} />
                      </div>
                    ))}
                  </div>
                  <Textarea rows={2} placeholder="Notes (optional)" value={vitalsForm.notes}
                    onChange={e => setVitalsForm(p => ({ ...p, notes: e.target.value }))} />
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1" onClick={() => { setVitalsFormOpen(false); setVitalsForm({ ...emptyVitals }); }}>Cancel</Button>
                    <Button size="sm" className="flex-1 gap-1.5" disabled={vitalsMut.isPending} onClick={() => vitalsMut.mutate()}>
                      {vitalsMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Save Vitals
                    </Button>
                  </div>
                </section>
              )}
            </TabsContent>

            {/* ── Fluid Balance ── */}
            <TabsContent value="fluid" className="mt-0 space-y-3">
              {fluidData && (
                <section className="rounded-md border p-3 flex items-center justify-between text-sm">
                  <span>Intake: <strong className="text-blue-700 dark:text-blue-400">{fluidData.total_intake_ml} mL</strong></span>
                  <span>Output: <strong className="text-orange-700 dark:text-orange-400">{fluidData.total_output_ml} mL</strong></span>
                  <span>Balance: <strong className={cn(Number(fluidData.balance_ml) < 0 ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400")}>{fluidData.balance_ml} mL</strong></span>
                </section>
              )}
              {fluidLoading ? (
                <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
              ) : fluidEntries.length === 0 ? (
                <p className="text-xs text-muted-foreground">No fluid entries for this encounter.</p>
              ) : (
                <div className="rounded-md border overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Time</TableHead>
                        <TableHead className="text-xs">Type</TableHead>
                        <TableHead className="text-xs">Route</TableHead>
                        <TableHead className="text-xs">Fluid</TableHead>
                        <TableHead className="text-xs">Volume</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {fluidEntries.map((e: any) => (
                        <TableRow key={e.id}>
                          <TableCell className="text-[13px] text-muted-foreground">{fmtDate(e.recorded_at)}</TableCell>
                          <TableCell><FluidTypeBadge type={e.fluid_type} /></TableCell>
                          <TableCell className="text-xs text-muted-foreground capitalize">{e.route ?? "—"}</TableCell>
                          <TableCell className="text-xs">{e.fluid_name ?? "—"}</TableCell>
                          <TableCell className="text-xs font-semibold">{e.volume_ml} mL</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {!fluidFormOpen ? (
                <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => setFluidFormOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> Log Entry
                </Button>
              ) : (
                <section className="space-y-2 border-t pt-3">
                  <div className="grid grid-cols-2 gap-2">
                    <Select value={fluidForm.fluid_type} onValueChange={v => setFluidForm(f => ({ ...f, fluid_type: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="intake">Intake</SelectItem>
                        <SelectItem value="output">Output</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input type="number" placeholder="Volume (mL) *" value={fluidForm.volume_ml}
                      onChange={e => setFluidForm(f => ({ ...f, volume_ml: e.target.value }))} />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Input placeholder="Fluid / description" value={fluidForm.fluid_name}
                      onChange={e => setFluidForm(f => ({ ...f, fluid_name: e.target.value }))} />
                    <Input placeholder="Route (oral | iv | urine)" value={fluidForm.route}
                      onChange={e => setFluidForm(f => ({ ...f, route: e.target.value }))} />
                  </div>
                  <Input placeholder="Notes (optional)" value={fluidForm.notes}
                    onChange={e => setFluidForm(f => ({ ...f, notes: e.target.value }))} />
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1" onClick={() => { setFluidFormOpen(false); setFluidForm({ ...emptyFluid }); }}>Cancel</Button>
                    <Button size="sm" className="flex-1 gap-1.5" disabled={!fluidForm.volume_ml || fluidMut.isPending} onClick={() => fluidMut.mutate()}>
                      {fluidMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Log Entry
                    </Button>
                  </div>
                </section>
              )}
            </TabsContent>

            {/* ── Care Plans ── */}
            <TabsContent value="plans" className="mt-0 space-y-3">
              <ScopeToggle scope={historyScope} onChange={setHistoryScope} />
              {plansLoading ? (
                <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
              ) : carePlans.length === 0 ? (
                <p className="text-xs text-muted-foreground">No care plans yet.</p>
              ) : (
                <div className="space-y-2">
                  {carePlans.map((plan: any) => (
                    <div key={plan.id} className="rounded-md border p-2.5 space-y-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium">{plan.problem}</p>
                        <div className="flex gap-1 shrink-0">
                          <CarePlanPriorityBadge priority={plan.priority} />
                          <CarePlanStatusBadge status={plan.status} />
                        </div>
                      </div>
                      {plan.goal && <p className="text-xs text-muted-foreground">Goal: {plan.goal}</p>}
                      {plan.interventions && <p className="text-xs text-muted-foreground whitespace-pre-wrap">{plan.interventions}</p>}
                      <div className="flex items-center justify-between">
                        <p className="text-[13px] text-muted-foreground">{plan.assigned_to ? `Assigned to ${plan.assigned_to}` : ""}</p>
                        {plan.status === "active" && (
                          <Button size="sm" variant="ghost" className="h-6 px-2 text-[13px] text-green-500 hover:bg-green-500/10"
                            onClick={() => resolvePlanMut.mutate(plan.id)} disabled={resolvePlanMut.isPending}>
                            <CheckCircle2 className="mr-1 h-3 w-3" /> Resolve
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!planFormOpen ? (
                <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => setPlanFormOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> Add Care Plan
                </Button>
              ) : (
                <section className="space-y-2 border-t pt-3">
                  <Input placeholder="Problem / nursing diagnosis *" value={planForm.problem}
                    onChange={e => setPlanForm(f => ({ ...f, problem: e.target.value }))} />
                  <Input placeholder="Goal (optional)" value={planForm.goal}
                    onChange={e => setPlanForm(f => ({ ...f, goal: e.target.value }))} />
                  <Textarea rows={2} placeholder="Interventions (optional)" value={planForm.interventions}
                    onChange={e => setPlanForm(f => ({ ...f, interventions: e.target.value }))} />
                  <div className="grid grid-cols-2 gap-2">
                    <Select value={planForm.priority} onValueChange={v => setPlanForm(f => ({ ...f, priority: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {["low", "medium", "high", "critical"].map(p => (
                          <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input placeholder="Assigned to (optional)" value={planForm.assigned_to}
                      onChange={e => setPlanForm(f => ({ ...f, assigned_to: e.target.value }))} />
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1" onClick={() => { setPlanFormOpen(false); setPlanForm({ ...emptyPlan }); }}>Cancel</Button>
                    <Button size="sm" className="flex-1 gap-1.5" disabled={!planForm.problem.trim() || planMut.isPending} onClick={() => planMut.mutate()}>
                      {planMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Create Plan
                    </Button>
                  </div>
                </section>
              )}
            </TabsContent>

            {/* ── MAR ── */}
            <TabsContent value="mar" className="mt-0 space-y-3">
              {Object.keys(marSummary).length > 0 && (
                <div className="flex gap-1.5 flex-wrap">
                  {Object.entries(marSummary).map(([s, count]) => (
                    <Badge key={s} variant="outline" className="text-[12px] capitalize">{s.replace(/_/g, " ")}: {count}</Badge>
                  ))}
                </div>
              )}
              {marLoading ? (
                <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
              ) : marEntries.length === 0 ? (
                <p className="text-xs text-muted-foreground">No MAR entries for this encounter.</p>
              ) : (
                <div className="rounded-md border overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Drug</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-xs">Administered</TableHead>
                        <TableHead className="text-xs">By</TableHead>
                        <TableHead className="text-xs"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {marEntries.map((m: any) => (
                        <Fragment key={m.id}>
                          <TableRow>
                            <TableCell className="text-xs font-medium">
                              {m.drug_name}
                              {(m.dose || m.route) && <div className="text-[12px] text-muted-foreground">{[m.dose, m.route?.toUpperCase()].filter(Boolean).join(" · ")}</div>}
                            </TableCell>
                            <TableCell><MarStatusBadge status={m.status} /></TableCell>
                            <TableCell className="text-[13px] text-muted-foreground">{fmtDate(m.administered_at)}</TableCell>
                            <TableCell className="text-[13px] text-muted-foreground">{m.administered_by ?? "—"}</TableCell>
                            <TableCell>
                              {m.status === "scheduled" && (
                                <Button size="sm" variant="ghost" className="h-6 px-2 text-[13px]"
                                  onClick={() => { setEditingMarId(m.id); setMarUpdateForm({ ...emptyMarUpdate }); }}>
                                  Update
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                          {editingMarId === m.id && (
                            <TableRow>
                              <TableCell colSpan={5}>
                                <div className="rounded-md border border-primary/30 bg-muted/30 p-2 space-y-2">
                                  <Select value={marUpdateForm.status} onValueChange={v => setMarUpdateForm(f => ({ ...f, status: v }))}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                      {["administered", "held", "missed", "refused"].map(s => (
                                        <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                  {(marUpdateForm.status === "held" || marUpdateForm.status === "refused") && (
                                    <Input placeholder="Override reason *" value={marUpdateForm.override_reason}
                                      onChange={e => setMarUpdateForm(f => ({ ...f, override_reason: e.target.value }))} />
                                  )}
                                  <Textarea rows={2} placeholder="Notes (optional)" value={marUpdateForm.notes}
                                    onChange={e => setMarUpdateForm(f => ({ ...f, notes: e.target.value }))} />
                                  <div className="flex gap-2">
                                    <Button size="sm" variant="outline" className="flex-1" onClick={() => setEditingMarId(null)}>Cancel</Button>
                                    <Button size="sm" className="flex-1" disabled={marUpdateInvalid || marUpdateMut.isPending}
                                      onClick={() => marUpdateMut.mutate({ entryId: m.id, ...marUpdateForm })}>
                                      {marUpdateMut.isPending && <Loader2 className="h-3 w-3 animate-spin mr-1" />}Save
                                    </Button>
                                  </div>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {!marFormOpen ? (
                <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => setMarFormOpen(true)}>
                  <Plus className="h-3.5 w-3.5" /> Record Administration
                </Button>
              ) : (
                <section className="space-y-2 border-t pt-3">
                  <Input placeholder="Drug name *" value={marForm.drug_name}
                    onChange={e => setMarForm(f => ({ ...f, drug_name: e.target.value }))} />
                  <div className="grid grid-cols-2 gap-2">
                    <Input placeholder="Dose" value={marForm.dose}
                      onChange={e => setMarForm(f => ({ ...f, dose: e.target.value }))} />
                    <Select value={marForm.route} onValueChange={v => setMarForm(f => ({ ...f, route: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {["oral", "iv", "im", "sc", "topical", "inhaled", "sublingual", "rectal"].map(r => (
                          <SelectItem key={r} value={r}>{r.toUpperCase()}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Select value={marForm.status} onValueChange={v => setMarForm(f => ({ ...f, status: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["administered", "scheduled", "held", "missed", "refused"].map(s => (
                        <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {(marForm.status === "held" || marForm.status === "refused") && (
                    <Input placeholder="Override reason *" value={marForm.override_reason}
                      onChange={e => setMarForm(f => ({ ...f, override_reason: e.target.value }))} />
                  )}
                  <Textarea rows={2} placeholder="Notes (optional)" value={marForm.notes}
                    onChange={e => setMarForm(f => ({ ...f, notes: e.target.value }))} />
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1" onClick={() => { setMarFormOpen(false); setMarForm({ ...emptyMar }); }}>Cancel</Button>
                    <Button size="sm" className="flex-1 gap-1.5"
                      disabled={!marForm.drug_name.trim() || ((marForm.status === "held" || marForm.status === "refused") && !marForm.override_reason.trim()) || marMut.isPending}
                      onClick={() => marMut.mutate()}>
                      {marMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Record
                    </Button>
                  </div>
                </section>
              )}
            </TabsContent>
          </div>
        </Tabs>

        <Separator className="shrink-0" />
        <div className="px-5 py-3 flex justify-end shrink-0">
          <Button size="sm" variant="ghost" className="gap-1.5"
            disabled={!initialEncounter.patient_mrn}
            onClick={() => { if (initialEncounter.patient_mrn) { navigate(`/hospital/patients/${initialEncounter.patient_mrn}`); onClose(); } }}>
            <ExternalLink className="h-3.5 w-3.5" /> Open Patient Record
          </Button>
        </div>
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

function VitalMini({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string; color: string }) {
  return (
    <div className="rounded-md border p-2 flex items-center justify-between">
      <div>
        <p className="text-[12px] text-muted-foreground">{label}</p>
        <p className="text-sm font-bold">{value}</p>
      </div>
      <span className={color}>{icon}</span>
    </div>
  );
}

function ScopeToggle({ scope, onChange }: { scope: "encounter" | "patient"; onChange: (s: "encounter" | "patient") => void }) {
  return (
    <div className="flex gap-1.5 text-xs">
      {(["encounter", "patient"] as const).map(s => (
        <button key={s} onClick={() => onChange(s)}
          className={cn("px-2.5 py-1 rounded-full border transition-colors",
            scope === s ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-primary/50")}>
          {s === "encounter" ? "This stay" : "Full history"}
        </button>
      ))}
    </div>
  );
}
