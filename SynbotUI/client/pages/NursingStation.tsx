import { useState, useMemo } from "react";
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
  Activity, Heart, Thermometer, Droplets, Wind, Plus, RefreshCw,
  Loader2, ClipboardList, AlertTriangle, CheckCircle2, Pill,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { AllergyBanner } from "@/components/AllergyBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function PainBadge({ score }: { score?: number | null }) {
  if (score == null) return <span className="text-muted-foreground text-xs">—</span>;
  const cls = score >= 7 ? "bg-red-500/20 text-red-400 border-red-500/30"
    : score >= 4 ? "bg-orange-500/20 text-orange-400 border-orange-500/30"
    : "bg-green-500/20 text-green-400 border-green-500/30";
  return <Badge variant="outline" className={cn("text-xs", cls)}>{score}/10</Badge>;
}

const EMPTY_VITALS = {
  patient_id: "", encounter_id: "",
  temperature: "", pulse: "", respiratory_rate: "", bp_systolic: "", bp_diastolic: "",
  spo2: "", weight: "", height: "", blood_glucose: "", pain_score: "", gcs: "", notes: "",
};

const EMPTY_FLUID = { patient_id: "", encounter_id: "", fluid_type: "intake", route: "", volume_ml: "", fluid_name: "", notes: "" };

const EMPTY_PLAN = { patient_id: "", encounter_id: "", problem: "", goal: "", interventions: "", priority: "medium", assigned_to: "" };

const EMPTY_MAR = { encounter_id: "", patient_id: "", drug_name: "", dose: "", route: "oral", status: "administered", notes: "", override_reason: "" };

// ─── Component ────────────────────────────────────────────────────────────────
export default function NursingStation() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [tab, setTab] = useState("vitals");
  const [patientIdInput, setPatientIdInput] = useState("");
  const [encounterIdInput, setEncounterIdInput] = useState("");
  const [lookupPatientId, setLookupPatientId] = useState<string | null>(null);
  const [lookupEncounterId, setLookupEncounterId] = useState<string | null>(null);

  // Dialog state
  const [vitalsOpen, setVitalsOpen]     = useState(false);
  const [fluidOpen, setFluidOpen]       = useState(false);
  const [planOpen, setPlanOpen]         = useState(false);
  const [marOpen, setMarOpen]           = useState(false);
  const [vitalsForm, setVitalsForm]     = useState({ ...EMPTY_VITALS });
  const [fluidForm, setFluidForm]       = useState({ ...EMPTY_FLUID });
  const [planForm, setPlanForm]         = useState({ ...EMPTY_PLAN });
  const [marForm, setMarForm]           = useState({ ...EMPTY_MAR });

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data: vitalsData, isLoading: vitalsLoading, refetch: refetchVitals } = useQuery({
    queryKey: ["nursing-vitals", lookupPatientId],
    queryFn: () => api.hospital.nursing.listVitals(lookupPatientId!, lookupEncounterId ?? undefined),
    enabled: !!lookupPatientId,
    staleTime: 30_000,
  });
  const vitalsList: any[] = Array.isArray(vitalsData?.vitals) ? vitalsData.vitals : [];

  const { data: fluidData, isLoading: fluidLoading, refetch: refetchFluid } = useQuery({
    queryKey: ["nursing-fluid", lookupEncounterId],
    queryFn: () => api.hospital.nursing.getFluidBalance(lookupEncounterId!),
    enabled: !!lookupEncounterId && tab === "fluid",
    staleTime: 30_000,
  });
  const fluidEntries: any[] = Array.isArray(fluidData?.entries) ? fluidData.entries : [];

  const { data: plansData, isLoading: plansLoading, refetch: refetchPlans } = useQuery({
    queryKey: ["nursing-plans", lookupPatientId],
    queryFn: () => api.hospital.nursing.listCarePlans(lookupPatientId!, lookupEncounterId ?? undefined),
    enabled: !!lookupPatientId && tab === "plans",
    staleTime: 60_000,
  });
  const carePlans: any[] = Array.isArray(plansData?.care_plans) ? plansData.care_plans : [];

  const { data: marData, isLoading: marLoading, refetch: refetchMAR } = useQuery({
    queryKey: ["nursing-mar", lookupEncounterId],
    queryFn: () => api.hospital.nursing.listMAR(lookupEncounterId!),
    enabled: !!lookupEncounterId && tab === "mar",
    staleTime: 30_000,
  });
  const marEntries: any[] = Array.isArray(marData?.mar) ? marData.mar : [];

  // Most recent vitals for summary cards
  const latest = vitalsList[0];

  // Patient allergy lookup — search by patient ID to retrieve demographics
  const { data: patientSearchData } = useQuery({
    queryKey: ["nursing-patient-allergy", lookupPatientId],
    queryFn: () => api.hospital.patients.search(lookupPatientId!),
    enabled: !!lookupPatientId,
    staleTime: 300_000,
  });
  const patientAllergies: string[] = useMemo(() => {
    const results = patientSearchData?.patients ?? patientSearchData?.results ?? [];
    const match = results.find((p: any) => String(p.id) === String(lookupPatientId));
    return match?.allergies ?? [];
  }, [patientSearchData, lookupPatientId]);

  // ── Mutations ──────────────────────────────────────────────────────────────
  const vitalsMut = useMutation({
    mutationFn: () => api.hospital.nursing.recordVitals({
      ...Object.fromEntries(Object.entries(vitalsForm).filter(([, v]) => v !== "" && v !== null)),
      patient_id: Number(vitalsForm.patient_id),
      ...(vitalsForm.encounter_id ? { encounter_id: Number(vitalsForm.encounter_id) } : {}),
    }),
    onSuccess: () => {
      toast({ title: "Vitals recorded" });
      setVitalsOpen(false);
      setVitalsForm({ ...EMPTY_VITALS });
      void qc.invalidateQueries({ queryKey: ["nursing-vitals"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const fluidMut = useMutation({
    mutationFn: () => api.hospital.nursing.logFluid({
      ...fluidForm,
      patient_id: Number(fluidForm.patient_id),
      encounter_id: Number(fluidForm.encounter_id),
      volume_ml: Number(fluidForm.volume_ml),
    }),
    onSuccess: () => {
      toast({ title: "Fluid entry logged" });
      setFluidOpen(false);
      setFluidForm({ ...EMPTY_FLUID });
      void qc.invalidateQueries({ queryKey: ["nursing-fluid"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const planMut = useMutation({
    mutationFn: () => api.hospital.nursing.createCarePlan({
      ...planForm,
      patient_id: Number(planForm.patient_id),
      ...(planForm.encounter_id ? { encounter_id: Number(planForm.encounter_id) } : {}),
    }),
    onSuccess: () => {
      toast({ title: "Care plan created" });
      setPlanOpen(false);
      setPlanForm({ ...EMPTY_PLAN });
      void qc.invalidateQueries({ queryKey: ["nursing-plans"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const resolvePlanMut = useMutation({
    mutationFn: (planId: number) => api.hospital.nursing.updateCarePlan(planId, { status: "resolved" }),
    onSuccess: () => { toast({ title: "Care plan resolved" }); void qc.invalidateQueries({ queryKey: ["nursing-plans"] }); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const marMut = useMutation({
    mutationFn: () => api.hospital.nursing.recordMAR({
      ...Object.fromEntries(Object.entries(marForm).filter(([, v]) => v !== "" && v !== null)),
      encounter_id: Number(marForm.encounter_id),
      patient_id: Number(marForm.patient_id),
    }),
    onSuccess: () => {
      toast({ title: "MAR entry recorded" });
      setMarOpen(false);
      setMarForm({ ...EMPTY_MAR });
      void qc.invalidateQueries({ queryKey: ["nursing-mar"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  function doLookup() {
    setLookupPatientId(patientIdInput.trim() || null);
    setLookupEncounterId(encounterIdInput.trim() || null);
  }

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      {lookupPatientId && <AllergyBanner allergies={patientAllergies} />}
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Nursing Station</h1>
          <p className="text-sm text-muted-foreground">Vitals, care plans, and fluid balance</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { void refetchVitals(); void refetchFluid(); void refetchPlans(); }} className="gap-2">
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* Patient / Encounter lookup */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="space-y-1 flex-1 min-w-[140px]">
              <Label className="text-xs">Patient ID</Label>
              <Input value={patientIdInput} onChange={e => setPatientIdInput(e.target.value)}
                placeholder="Enter patient ID" className="h-8 text-sm" />
            </div>
            <div className="space-y-1 flex-1 min-w-[140px]">
              <Label className="text-xs">Encounter ID (optional)</Label>
              <Input value={encounterIdInput} onChange={e => setEncounterIdInput(e.target.value)}
                placeholder="Enter encounter ID" className="h-8 text-sm" />
            </div>
            <Button size="sm" onClick={doLookup} className="h-8">Load Patient</Button>
          </div>
        </CardContent>
      </Card>

      {/* Latest vitals summary cards */}
      {latest && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Temp (°C)",    value: latest.temperature ?? "—",    icon: <Thermometer className="h-4 w-4" />, color: "text-orange-400" },
            { label: "Pulse (bpm)",  value: latest.pulse ?? "—",           icon: <Heart className="h-4 w-4" />,      color: "text-red-400"    },
            { label: "SpO₂ (%)",    value: latest.spo2 ?? "—",            icon: <Activity className="h-4 w-4" />,   color: Number(latest.spo2) < 95 ? "text-red-400" : "text-green-400" },
            { label: "Pain Score",  value: latest.pain_score != null ? `${latest.pain_score}/10` : "—", icon: <AlertTriangle className="h-4 w-4" />, color: Number(latest.pain_score) >= 7 ? "text-red-400" : "text-yellow-400" },
          ].map(k => (
            <Card key={k.label}>
              <CardContent className="pt-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground">{k.label}</p>
                    <p className="text-xl font-bold">{k.value}</p>
                  </div>
                  <span className={k.color}>{k.icon}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="vitals">Vitals</TabsTrigger>
          <TabsTrigger value="fluid">Fluid Balance</TabsTrigger>
          <TabsTrigger value="plans">Care Plans</TabsTrigger>
          <TabsTrigger value="mar">MAR</TabsTrigger>
        </TabsList>

        {/* ── Vitals Tab ─────────────────────────────────────────────────── */}
        <TabsContent value="vitals" className="space-y-4">
          <div className="mt-4 flex justify-end">
            <Button size="sm" className="gap-2" onClick={() => {
              setVitalsForm(f => ({ ...f, patient_id: patientIdInput, encounter_id: encounterIdInput }));
              setVitalsOpen(true);
            }}>
              <Plus className="h-3.5 w-3.5" /> Record Vitals
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {vitalsLoading ? (
                <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Temp</TableHead>
                      <TableHead>Pulse</TableHead>
                      <TableHead>BP</TableHead>
                      <TableHead>SpO₂</TableHead>
                      <TableHead>RR</TableHead>
                      <TableHead>Pain</TableHead>
                      <TableHead>GCS</TableHead>
                      <TableHead>Weight</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {vitalsList.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                          <Activity className="mx-auto mb-2 h-6 w-6 opacity-30" />
                          {lookupPatientId ? "No vitals recorded for this patient" : "Enter a patient ID above to load vitals"}
                        </TableCell>
                      </TableRow>
                    ) : vitalsList.map((v: any) => (
                      <TableRow key={v.id}>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{fmtDate(v.recorded_at)}</TableCell>
                        <TableCell className="text-sm">{v.temperature != null ? `${v.temperature}°C` : "—"}</TableCell>
                        <TableCell className="text-sm">{v.pulse != null ? `${v.pulse} bpm` : "—"}</TableCell>
                        <TableCell className="text-sm font-mono">
                          {v.bp_systolic != null ? `${v.bp_systolic}/${v.bp_diastolic}` : "—"}
                        </TableCell>
                        <TableCell className={cn("text-sm font-semibold", Number(v.spo2) < 95 ? "text-red-400" : "text-green-400")}>
                          {v.spo2 != null ? `${v.spo2}%` : "—"}
                        </TableCell>
                        <TableCell className="text-sm">{v.respiratory_rate != null ? `${v.respiratory_rate}/min` : "—"}</TableCell>
                        <TableCell><PainBadge score={v.pain_score} /></TableCell>
                        <TableCell className="text-sm">{v.gcs ?? "—"}</TableCell>
                        <TableCell className="text-sm">{v.weight != null ? `${v.weight} kg` : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Fluid Balance Tab ──────────────────────────────────────────── */}
        <TabsContent value="fluid" className="space-y-4">
          <div className="mt-4 flex justify-between items-center">
            {fluidData && (
              <div className="flex gap-4 text-sm">
                <span>Intake: <strong className="text-blue-400">{fluidData.total_intake_ml} mL</strong></span>
                <span>Output: <strong className="text-orange-400">{fluidData.total_output_ml} mL</strong></span>
                <span>Balance: <strong className={cn(Number(fluidData.balance_ml) < 0 ? "text-red-400" : "text-green-400")}>{fluidData.balance_ml} mL</strong></span>
              </div>
            )}
            <Button size="sm" className="gap-2 ml-auto" onClick={() => {
              setFluidForm(f => ({ ...f, patient_id: patientIdInput, encounter_id: encounterIdInput }));
              setFluidOpen(true);
            }}>
              <Plus className="h-3.5 w-3.5" /> Log Entry
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {fluidLoading ? (
                <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Route</TableHead>
                      <TableHead>Fluid</TableHead>
                      <TableHead>Volume (mL)</TableHead>
                      <TableHead>Notes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {fluidEntries.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                          <Droplets className="mx-auto mb-2 h-6 w-6 opacity-30" />
                          {lookupEncounterId ? "No fluid entries for this encounter" : "Enter an encounter ID above"}
                        </TableCell>
                      </TableRow>
                    ) : fluidEntries.map((entry: any) => (
                      <TableRow key={entry.id}>
                        <TableCell className="text-xs text-muted-foreground">{fmtDate(entry.recorded_at)}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize",
                            entry.fluid_type === "intake" ? "text-blue-400 border-blue-500/30 bg-blue-500/10" : "text-orange-400 border-orange-500/30 bg-orange-500/10"
                          )}>{entry.fluid_type}</Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground capitalize">{entry.route ?? "—"}</TableCell>
                        <TableCell className="text-sm">{entry.fluid_name ?? "—"}</TableCell>
                        <TableCell className="text-sm font-semibold">{entry.volume_ml}</TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">{entry.notes ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Care Plans Tab ─────────────────────────────────────────────── */}
        <TabsContent value="plans" className="space-y-4">
          <div className="mt-4 flex justify-end">
            <Button size="sm" className="gap-2" onClick={() => {
              setPlanForm(f => ({ ...f, patient_id: patientIdInput, encounter_id: encounterIdInput }));
              setPlanOpen(true);
            }}>
              <Plus className="h-3.5 w-3.5" /> Add Care Plan
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {plansLoading ? (
                <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Problem</TableHead>
                      <TableHead>Goal</TableHead>
                      <TableHead>Priority</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Assigned To</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {carePlans.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                          <ClipboardList className="mx-auto mb-2 h-6 w-6 opacity-30" />
                          {lookupPatientId ? "No care plans for this patient" : "Enter a patient ID above"}
                        </TableCell>
                      </TableRow>
                    ) : carePlans.map((plan: any) => (
                      <TableRow key={plan.id}>
                        <TableCell className="text-sm font-medium max-w-[200px]">{plan.problem}</TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[180px] truncate">{plan.goal ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize",
                            plan.priority === "critical" ? "text-red-400 border-red-500/30" :
                            plan.priority === "high" ? "text-orange-400 border-orange-500/30" :
                            plan.priority === "medium" ? "text-yellow-400 border-yellow-500/30" :
                            "text-slate-400 border-slate-500/30"
                          )}>{plan.priority}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize",
                            plan.status === "active" ? "text-blue-400 border-blue-500/30" :
                            plan.status === "resolved" ? "text-green-400 border-green-500/30" :
                            "text-slate-400 border-slate-500/30"
                          )}>{plan.status}</Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{plan.assigned_to ?? "—"}</TableCell>
                        <TableCell>
                          {plan.status === "active" && (
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-green-400 hover:bg-green-500/10"
                              onClick={() => resolvePlanMut.mutate(plan.id)} disabled={resolvePlanMut.isPending}>
                              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Resolve
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── MAR Tab ──────────────────────────────────────────────────────── */}
        <TabsContent value="mar" className="space-y-4">
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              {!lookupEncounterId ? "Enter an Encounter ID above to load MAR" : `${marEntries.length} entries`}
            </p>
            <Button size="sm" className="gap-2" onClick={() => {
              setMarForm(f => ({ ...f, patient_id: patientIdInput, encounter_id: encounterIdInput }));
              setMarOpen(true);
            }}>
              <Plus className="h-3.5 w-3.5" /> Record Administration
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {marLoading ? (
                <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : marEntries.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 py-12 text-center text-sm text-muted-foreground">
                  <Pill className="h-7 w-7 opacity-30" />
                  {lookupEncounterId ? "No MAR entries for this encounter" : "Load a patient encounter to view MAR"}
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Drug</TableHead>
                      <TableHead>Dose / Route</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Administered</TableHead>
                      <TableHead>By</TableHead>
                      <TableHead>Notes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {marEntries.map((m: any) => {
                      const statusCls =
                        m.status === "administered" ? "border-green-500/30 text-green-400 bg-green-500/10" :
                        m.status === "held"         ? "border-yellow-500/30 text-yellow-400 bg-yellow-500/10" :
                        m.status === "refused"      ? "border-red-500/30 text-red-400 bg-red-500/10" :
                        m.status === "missed"       ? "border-orange-500/30 text-orange-400 bg-orange-500/10" :
                        "border-slate-500/30 text-slate-400";
                      return (
                        <TableRow key={m.id}>
                          <TableCell className="font-medium">{m.drug_name}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {m.dose && <span>{m.dose}</span>}
                            {m.route && <span className="ml-1 uppercase text-[10px]">· {m.route}</span>}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={cn("text-[10px] capitalize", statusCls)}>
                              {m.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">{fmtDate(m.administered_at)}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{m.administered_by ?? "—"}</TableCell>
                          <TableCell className="text-xs text-muted-foreground max-w-[160px] truncate">
                            {m.override_reason || m.notes || "—"}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── MAR Dialog ─────────────────────────────────────────────────────────── */}
      <Dialog open={marOpen} onOpenChange={setMarOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Record MAR Entry</DialogTitle>
            <DialogDescription>Medication Administration Record</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Patient ID *</Label>
                <Input value={marForm.patient_id} onChange={e => setMarForm(f => ({ ...f, patient_id: e.target.value }))} placeholder="Patient ID" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Encounter ID *</Label>
                <Input value={marForm.encounter_id} onChange={e => setMarForm(f => ({ ...f, encounter_id: e.target.value }))} placeholder="Encounter ID" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Drug Name *</Label>
              <Input value={marForm.drug_name} onChange={e => setMarForm(f => ({ ...f, drug_name: e.target.value }))} placeholder="e.g. Amoxicillin 500mg" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Dose</Label>
                <Input value={marForm.dose} onChange={e => setMarForm(f => ({ ...f, dose: e.target.value }))} placeholder="e.g. 500mg" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Route</Label>
                <Select value={marForm.route} onValueChange={v => setMarForm(f => ({ ...f, route: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["oral","iv","im","sc","topical","inhaled","sublingual","rectal"].map(r => (
                      <SelectItem key={r} value={r}>{r.toUpperCase()}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Status</Label>
              <Select value={marForm.status} onValueChange={v => setMarForm(f => ({ ...f, status: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["administered","scheduled","held","missed","refused"].map(s => (
                    <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {(marForm.status === "held" || marForm.status === "refused") && (
              <div className="space-y-1">
                <Label className="text-xs">Override Reason *</Label>
                <Input value={marForm.override_reason} onChange={e => setMarForm(f => ({ ...f, override_reason: e.target.value }))} placeholder="Reason for hold/refusal" />
              </div>
            )}
            <div className="space-y-1">
              <Label className="text-xs">Notes</Label>
              <Textarea value={marForm.notes} onChange={e => setMarForm(f => ({ ...f, notes: e.target.value }))} rows={2} placeholder="Optional notes..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMarOpen(false)}>Cancel</Button>
            <Button
              disabled={!marForm.drug_name.trim() || !marForm.patient_id || !marForm.encounter_id || marMut.isPending}
              onClick={() => marMut.mutate()}
            >
              {marMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Record
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Record Vitals Dialog ────────────────────────────────────────────── */}
      <Dialog open={vitalsOpen} onOpenChange={setVitalsOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Record Vitals</DialogTitle>
            <DialogDescription>Patient ID: {vitalsForm.patient_id || "—"}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-3 py-2">
            {[
              { key: "temperature",      label: "Temp (°C)",     type: "number", placeholder: "37.0" },
              { key: "pulse",            label: "Pulse (bpm)",   type: "number", placeholder: "80"   },
              { key: "respiratory_rate", label: "RR (/min)",     type: "number", placeholder: "16"   },
              { key: "bp_systolic",      label: "BP Systolic",   type: "number", placeholder: "120"  },
              { key: "bp_diastolic",     label: "BP Diastolic",  type: "number", placeholder: "80"   },
              { key: "spo2",             label: "SpO₂ (%)",     type: "number", placeholder: "98"   },
              { key: "weight",           label: "Weight (kg)",   type: "number", placeholder: "70"   },
              { key: "height",           label: "Height (cm)",   type: "number", placeholder: "170"  },
              { key: "blood_glucose",    label: "Glucose mmol/L",type: "number", placeholder: "5.5"  },
              { key: "pain_score",       label: "Pain Score 0-10",type: "number",placeholder: "0"    },
              { key: "gcs",              label: "GCS (3-15)",    type: "number", placeholder: "15"   },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs">{f.label}</Label>
                <Input type={f.type} placeholder={f.placeholder} className="h-8 text-sm"
                  value={(vitalsForm as any)[f.key]}
                  onChange={e => setVitalsForm(prev => ({ ...prev, [f.key]: e.target.value }))} />
              </div>
            ))}
            <div className="col-span-3 space-y-1">
              <Label className="text-xs">Notes</Label>
              <Input value={vitalsForm.notes} onChange={e => setVitalsForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Clinical notes..." className="h-8 text-sm" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setVitalsOpen(false)}>Cancel</Button>
            <Button disabled={!vitalsForm.patient_id.trim() || vitalsMut.isPending} onClick={() => vitalsMut.mutate()}>
              {vitalsMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Save Vitals
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Log Fluid Entry Dialog ─────────────────────────────────────────── */}
      <Dialog open={fluidOpen} onOpenChange={setFluidOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Log Fluid Entry</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Type *</Label>
                <Select value={fluidForm.fluid_type} onValueChange={v => setFluidForm(f => ({ ...f, fluid_type: v }))}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="intake">Intake</SelectItem>
                    <SelectItem value="output">Output</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Volume (mL) *</Label>
                <Input type="number" value={fluidForm.volume_ml} onChange={e => setFluidForm(f => ({ ...f, volume_ml: e.target.value }))}
                  placeholder="250" className="h-8 text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Fluid / Description</Label>
                <Input value={fluidForm.fluid_name} onChange={e => setFluidForm(f => ({ ...f, fluid_name: e.target.value }))}
                  placeholder="Normal Saline" className="h-8 text-sm" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Route</Label>
                <Input value={fluidForm.route} onChange={e => setFluidForm(f => ({ ...f, route: e.target.value }))}
                  placeholder="oral | iv | urine" className="h-8 text-sm" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notes</Label>
              <Input value={fluidForm.notes} onChange={e => setFluidForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Optional..." className="h-8 text-sm" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFluidOpen(false)}>Cancel</Button>
            <Button disabled={!fluidForm.volume_ml || !fluidForm.encounter_id || fluidMut.isPending} onClick={() => fluidMut.mutate()}>
              {fluidMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Log Entry
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Care Plan Dialog ───────────────────────────────────────────── */}
      <Dialog open={planOpen} onOpenChange={setPlanOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Care Plan</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Problem / Nursing Diagnosis *</Label>
              <Input value={planForm.problem} onChange={e => setPlanForm(f => ({ ...f, problem: e.target.value }))}
                placeholder="e.g. Risk for infection related to IV catheter" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Goal</Label>
              <Input value={planForm.goal} onChange={e => setPlanForm(f => ({ ...f, goal: e.target.value }))}
                placeholder="Expected outcome" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Interventions</Label>
              <Textarea value={planForm.interventions} onChange={e => setPlanForm(f => ({ ...f, interventions: e.target.value }))}
                placeholder="Nursing actions and frequency..." rows={3} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Priority</Label>
                <Select value={planForm.priority} onValueChange={v => setPlanForm(f => ({ ...f, priority: v }))}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Assigned To</Label>
                <Input value={planForm.assigned_to} onChange={e => setPlanForm(f => ({ ...f, assigned_to: e.target.value }))}
                  placeholder="Nurse name" className="h-8 text-sm" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPlanOpen(false)}>Cancel</Button>
            <Button disabled={!planForm.problem.trim() || !planForm.patient_id || planMut.isPending} onClick={() => planMut.mutate()}>
              {planMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Create Plan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
