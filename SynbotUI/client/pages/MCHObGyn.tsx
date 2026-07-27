import { useState } from "react";
import { useNavigate } from "react-router-dom";
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
  Heart, RefreshCw, Loader2, Plus, Baby, ClipboardList,
  ActivitySquare, Syringe, CheckCircle2, ChevronRight, Search, Trash2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const ANC_STATUS_COLORS: Record<string, string> = {
  active:      "bg-green-100 text-green-700 border-green-300",
  delivered:   "bg-blue-100 text-blue-700 border-blue-300",
  miscarriage: "bg-red-100 text-red-700 border-red-300",
  referred:    "bg-orange-100 text-orange-700 border-orange-300",
};

const DELIVERY_MODE_COLORS: Record<string, string> = {
  svd:      "bg-green-100 text-green-700 border-green-300",
  assisted: "bg-yellow-100 text-yellow-700 border-yellow-300",
  cs:       "bg-sky-100 text-sky-700 border-sky-300",
  breech:   "bg-orange-100 text-orange-700 border-orange-300",
};

// ─── ANC Registration form ───────────────────────────────────────────────────

const emptyAnc = {
  patient_id: "", encounter_id: "", gravida: "", para: "",
  lmp: "", edd: "", gestational_age_weeks: "",
  blood_group: "", rhesus: "positive",
  hiv_status: "unknown", hbsag: "unknown", syphilis: "unknown",
  malaria_prophylaxis: false, tetanus_toxoid: false, iron_folic_acid: false,
  risk_factors: "", referred_from: "", notes: "",
};

const emptyVisit = {
  visit_date: "", gestational_age_weeks: "", weight_kg: "",
  bp_systolic: "", bp_diastolic: "", fundal_height_cm: "",
  fetal_heart_rate: "", presentation: "", engagement: "",
  oedema: false, proteinuria: false, haemoglobin: "",
  malaria_rapid_test: "", drugs_given: "", counselling_given: "",
  next_visit_date: "", clinician_id: "", notes: "",
};

const emptyDelivery = {
  delivery_date: "", delivery_time: "",
  mode_of_delivery: "svd", indication: "",
  duration_of_labour_hours: "", blood_loss_ml: "",
  placenta_complete: true, perineal_tear: "", episiotomy: false,
  maternal_complications: "", anaesthesia_type: "", attending_clinician: "", notes: "",
};

const emptyNewborn = {
  sex: "male", birth_weight_kg: "", length_cm: "", head_circumference_cm: "",
  apgar_1min: "", apgar_5min: "", apgar_10min: "",
  gestational_age_at_birth: "",
  cry_at_birth: true, resuscitation_needed: false, resuscitation_type: "",
  congenital_anomalies: "",
  eye_prophylaxis: false, vitamin_k_given: false, bcg_given: false,
  opv0_given: false, hbv_given: false,
  breast_feeding_initiated: true, notes: "",
};

const emptyImmunisation = {
  vaccine_name: "", dose_number: "", date_given: "", batch_number: "",
  site: "", next_due_date: "", reaction: "", notes: "",
};

function BoolCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <div
        onClick={() => onChange(!checked)}
        className={cn(
          "w-4 h-4 rounded border flex items-center justify-center cursor-pointer transition-colors flex-shrink-0",
          checked ? "bg-green-100 border-green-500" : "border-border hover:border-ring"
        )}
      >
        {checked && <CheckCircle2 className="w-2.5 h-2.5 text-green-600" />}
      </div>
      <span className="text-xs text-muted-foreground">{label}</span>
    </label>
  );
}

export default function MCHObGyn() {
  const { toast } = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [patientSearch, setPatientSearch] = useState("");
  const [lookupId, setLookupId] = useState<number | null>(null);

  // Dialog states
  const [ancOpen, setAncOpen] = useState(false);
  const [ancForm, setAncForm] = useState({ ...emptyAnc });

  const [visitOpen, setVisitOpen] = useState(false);
  const [visitAncId, setVisitAncId] = useState<number | null>(null);
  const [visitForm, setVisitForm] = useState({ ...emptyVisit });

  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const [deliveryAncId, setDeliveryAncId] = useState<number | null>(null);
  const [deliveryForm, setDeliveryForm] = useState({ ...emptyDelivery });

  const [newbornOpen, setNewbornOpen] = useState(false);
  const [newbornDeliveryId, setNewbornDeliveryId] = useState<number | null>(null);
  const [newbornForm, setNewbornForm] = useState({ ...emptyNewborn });

  const [immunOpen, setImmunOpen] = useState(false);
  const [immunPatientId, setImmunPatientId] = useState<number | null>(null);
  const [immunRows, setImmunRows] = useState([{ ...emptyImmunisation }]);

  const [babyResult, setBabyResult] = useState<any | null>(null);
  const [babyResultOpen, setBabyResultOpen] = useState(false);

  const [visitsViewAncId, setVisitsViewAncId] = useState<number | null>(null);
  const [visitsViewOpen, setVisitsViewOpen] = useState(false);

  // Queries
  const { data: statsData } = useQuery({
    queryKey: ["mch-stats"],
    queryFn: () => api.hospital.mch.stats(),
  });

  const { data: ancData, isLoading: ancLoading, refetch: refetchAnc } = useQuery({
    queryKey: ["anc-list", lookupId],
    queryFn: () => api.hospital.mch.listAnc(lookupId ? { patient_id: lookupId } : {}),
  });

  const { data: visitsData } = useQuery({
    queryKey: ["anc-visits", visitsViewAncId],
    queryFn: () => api.hospital.mch.listVisits(visitsViewAncId!),
    enabled: !!visitsViewAncId,
  });

  const [immunLookupId, setImmunLookupId] = useState<number | null>(null);
  const { data: vaccineScheduleData, isLoading: scheduleLoading } = useQuery({
    queryKey: ["vaccine-schedule", immunLookupId],
    queryFn: () => api.hospital.mch.listVaccineSchedule(immunLookupId ? { patient_id: immunLookupId } : undefined),
    enabled: !!immunLookupId,
  });
  const vaccineSchedule: any[] = vaccineScheduleData?.schedule ?? [];

  const { data: immunHistoryData } = useQuery({
    queryKey: ["immunisation-history", immunLookupId],
    queryFn: () => api.hospital.mch.getImmunisationHistory(immunLookupId!),
    enabled: !!immunLookupId,
  });
  const immunHistory: any[] = immunHistoryData?.immunisations ?? [];

  const { data: babiesData } = useQuery({
    queryKey: ["mch-babies", lookupId],
    queryFn: () => api.hospital.mch.listBabies(lookupId!),
    enabled: !!lookupId,
  });
  const babies: any[] = babiesData?.babies ?? [];

  const stats = statsData?.anc || { total: 0, active: 0, delivered: 0, referred: 0 };
  const deliveryModes = statsData?.delivery_modes || {};
  const vaccineStats = statsData?.immunisation_counts || {};
  const ancList = ancData?.records || [];
  const visits = visitsData?.visits || [];

  // Mutations
  const ancMut = useMutation({
    mutationFn: (d: typeof ancForm) => api.hospital.mch.registerAnc({
      ...d,
      patient_id: Number(d.patient_id),
      encounter_id: d.encounter_id ? Number(d.encounter_id) : undefined,
      gravida: d.gravida ? Number(d.gravida) : undefined,
      para: d.para ? Number(d.para) : undefined,
      gestational_age_weeks: d.gestational_age_weeks ? Number(d.gestational_age_weeks) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "ANC registration complete" });
      setAncOpen(false);
      setAncForm({ ...emptyAnc });
      qc.invalidateQueries({ queryKey: ["anc-list"] });
      qc.invalidateQueries({ queryKey: ["mch-stats"] });
    },
    onError: () => toast({ title: "Failed to register ANC patient", variant: "destructive" }),
  });

  const visitMut = useMutation({
    mutationFn: (d: typeof visitForm) => api.hospital.mch.logVisit(visitAncId!, {
      ...d,
      gestational_age_weeks: d.gestational_age_weeks ? Number(d.gestational_age_weeks) : undefined,
      weight_kg: d.weight_kg ? Number(d.weight_kg) : undefined,
      bp_systolic: d.bp_systolic ? Number(d.bp_systolic) : undefined,
      bp_diastolic: d.bp_diastolic ? Number(d.bp_diastolic) : undefined,
      fundal_height_cm: d.fundal_height_cm ? Number(d.fundal_height_cm) : undefined,
      fetal_heart_rate: d.fetal_heart_rate ? Number(d.fetal_heart_rate) : undefined,
      haemoglobin: d.haemoglobin ? Number(d.haemoglobin) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "ANC visit recorded" });
      setVisitOpen(false);
      setVisitForm({ ...emptyVisit });
      qc.invalidateQueries({ queryKey: ["anc-visits"] });
    },
    onError: () => toast({ title: "Failed to record visit", variant: "destructive" }),
  });

  const deliveryMut = useMutation({
    mutationFn: (d: typeof deliveryForm) => api.hospital.mch.recordDelivery(deliveryAncId!, {
      ...d,
      duration_of_labour_hours: d.duration_of_labour_hours ? Number(d.duration_of_labour_hours) : undefined,
      blood_loss_ml: d.blood_loss_ml ? Number(d.blood_loss_ml) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Delivery recorded" });
      setDeliveryOpen(false);
      setDeliveryForm({ ...emptyDelivery });
      qc.invalidateQueries({ queryKey: ["anc-list"] });
      qc.invalidateQueries({ queryKey: ["mch-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Failed to record delivery", variant: "destructive" }),
  });

  const newbornMut = useMutation({
    mutationFn: (d: typeof newbornForm) => api.hospital.mch.addNewbornAssessment(newbornDeliveryId!, {
      ...d,
      birth_weight_kg: d.birth_weight_kg ? Number(d.birth_weight_kg) : undefined,
      length_cm: d.length_cm ? Number(d.length_cm) : undefined,
      head_circumference_cm: d.head_circumference_cm ? Number(d.head_circumference_cm) : undefined,
      apgar_1min: d.apgar_1min !== "" ? Number(d.apgar_1min) : undefined,
      apgar_5min: d.apgar_5min !== "" ? Number(d.apgar_5min) : undefined,
      apgar_10min: d.apgar_10min !== "" ? Number(d.apgar_10min) : undefined,
      gestational_age_at_birth: d.gestational_age_at_birth ? Number(d.gestational_age_at_birth) : undefined,
    }),
    onSuccess: (res: any) => {
      toast({ title: "Newborn assessment saved", description: res?.baby_patient?.mrn ? `Baby MRN ${res.baby_patient.mrn} created` : undefined });
      setNewbornOpen(false);
      setNewbornForm({ ...emptyNewborn });
      if (res?.baby_patient) {
        setBabyResult(res.baby_patient);
        setBabyResultOpen(true);
      }
    },
    onError: () => toast({ title: "Failed to save newborn assessment", variant: "destructive" }),
  });

  const immunMut = useMutation({
    mutationFn: (rows: typeof immunRows) => api.hospital.mch.logImmunisation(
      immunPatientId!,
      rows
        .filter(r => r.vaccine_name.trim())
        .map(d => ({ ...d, dose_number: d.dose_number ? Number(d.dose_number) : undefined })),
    ),
    onSuccess: (res: any) => {
      toast({ title: `${res?.count ?? "Immunisation"} dose(s) recorded` });
      setImmunOpen(false);
      setImmunRows([{ ...emptyImmunisation }]);
      qc.invalidateQueries({ queryKey: ["immunisation-history"] });
      qc.invalidateQueries({ queryKey: ["vaccine-schedule"] });
    },
    onError: () => toast({ title: "Failed to log immunisation", variant: "destructive" }),
  });

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 rounded-lg">
            <Heart className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">MCH / OB-GYN</h1>
            <p className="text-sm text-muted-foreground">Antenatal care, deliveries, newborn assessment, and immunisation</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="border-border"
            onClick={() => { refetchAnc(); qc.invalidateQueries({ queryKey: ["mch-stats"] }); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" className="bg-blue-700 hover:bg-blue-800"
            onClick={() => setAncOpen(true)}>
            <Plus className="w-4 h-4 mr-1" /> Register ANC
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total ANC",  value: stats.total,    color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Active",     value: stats.active,   color: "text-green-700",   bg: "bg-green-50" },
          { label: "Delivered",  value: stats.delivered,color: "text-blue-700",    bg: "bg-blue-50" },
          { label: "Referred",   value: stats.referred, color: "text-orange-700",  bg: "bg-orange-50" },
        ].map(k => (
          <Card key={k.label} className={cn("border-border", k.bg)}>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">{k.label}</p>
              <p className={cn("text-2xl font-bold mt-1", k.color)}>{k.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="anc">
        <TabsList className="bg-muted border border-border">
          <TabsTrigger value="anc">ANC Register</TabsTrigger>
          <TabsTrigger value="stats">Delivery Stats</TabsTrigger>
          <TabsTrigger value="immunisation">Immunisation</TabsTrigger>
        </TabsList>

        {/* ANC Register Tab */}
        <TabsContent value="anc" className="mt-4 space-y-4">
          <div className="flex items-center gap-2">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Filter by Patient ID"
                value={patientSearch}
                onChange={e => setPatientSearch(e.target.value)}
                className="pl-9 bg-background border-border text-foreground text-sm h-8"
              />
            </div>
            <Button size="sm" variant="outline" className="border-border h-8"
              onClick={() => setLookupId(patientSearch ? Number(patientSearch) : null)}>
              <Search className="w-3 h-3 mr-1" /> Search
            </Button>
            {lookupId && (
              <Button size="sm" variant="ghost" className="h-8 text-muted-foreground"
                onClick={() => { setLookupId(null); setPatientSearch(""); }}>
                Clear
              </Button>
            )}
          </div>

          <Card className="border-border bg-muted/20">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground text-xs">ID</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Patient ID</TableHead>
                  <TableHead className="text-muted-foreground text-xs">G/P</TableHead>
                  <TableHead className="text-muted-foreground text-xs">EDD</TableHead>
                  <TableHead className="text-muted-foreground text-xs">GA (wks)</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Status</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ancLoading
                  ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : ancList.length === 0
                    ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No ANC records found</TableCell></TableRow>
                    : ancList.map((r: any) => (
                      <TableRow key={r.id} className="border-border/50 hover:bg-muted/30">
                        <TableCell className="font-mono text-xs text-muted-foreground">{r.id}</TableCell>
                        <TableCell className="text-sm text-foreground">{r.patient_id}</TableCell>
                        <TableCell className="text-sm">
                          G{r.gravida ?? "?"}/P{r.para ?? "?"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.edd || "—"}</TableCell>
                        <TableCell className="text-sm">{r.gestational_age_weeks ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize", ANC_STATUS_COLORS[r.status] || "")}>
                            {r.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1 flex-wrap">
                            <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                              onClick={() => {
                                setVisitsViewAncId(r.id);
                                setVisitsViewOpen(true);
                              }}>
                              <ClipboardList className="w-3 h-3 mr-1" /> Visits
                            </Button>
                            <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                              onClick={() => { setVisitAncId(r.id); setVisitOpen(true); }}>
                              <Plus className="w-3 h-3 mr-1" /> Log Visit
                            </Button>
                            {r.status === "active" && (
                              <Button size="sm" className="h-6 text-xs px-2 bg-blue-600 hover:bg-blue-700"
                                onClick={() => { setDeliveryAncId(r.id); setDeliveryOpen(true); }}>
                                <Baby className="w-3 h-3 mr-1" /> Delivery
                              </Button>
                            )}
                            <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                              onClick={() => { setImmunPatientId(r.patient_id); setImmunRows([{ ...emptyImmunisation }]); setImmunOpen(true); }}>
                              <Syringe className="w-3 h-3 mr-1" /> Immun.
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>

          {lookupId && babies.length > 0 && (
            <Card className="border-border bg-muted/20">
              <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Baby className="w-4 h-4 text-sky-400" /> Babies</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {babies.map((b: any) => (
                  <div key={b.id} className="flex items-center justify-between text-sm border-b border-border/50 pb-1">
                    <span>{b.first_name} {b.last_name} · {b.gender ?? "—"} · MRN {b.mrn}</span>
                    <Button size="sm" variant="ghost" className="h-6 text-xs"
                      onClick={() => navigate(`/hospital/patients/${b.mrn}`)}>
                      View Chart <ChevronRight className="w-3 h-3 ml-1" />
                    </Button>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Delivery Stats Tab */}
        <TabsContent value="stats" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="border-border bg-muted/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Delivery Modes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(deliveryModes).length === 0
                  ? <p className="text-muted-foreground text-sm">No delivery data</p>
                  : Object.entries(deliveryModes).map(([mode, count]) => (
                    <div key={mode} className="flex justify-between items-center">
                      <Badge variant="outline" className={cn("text-xs uppercase", DELIVERY_MODE_COLORS[mode] || "bg-muted text-muted-foreground")}>
                        {mode}
                      </Badge>
                      <span className="text-foreground font-semibold">{count as number}</span>
                    </div>
                  ))
                }
              </CardContent>
            </Card>
            <Card className="border-border bg-muted/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Top Vaccines Administered</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(vaccineStats).length === 0
                  ? <p className="text-muted-foreground text-sm">No immunisation data</p>
                  : Object.entries(vaccineStats)
                      .sort(([, a], [, b]) => (b as number) - (a as number))
                      .slice(0, 8)
                      .map(([vaccine, count]) => (
                        <div key={vaccine} className="flex justify-between items-center">
                          <span className="text-sm text-muted-foreground">{vaccine}</span>
                          <span className="text-foreground font-semibold">{count as number}</span>
                        </div>
                      ))
                }
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Immunisation Tab */}
        <TabsContent value="immunisation" className="mt-4 space-y-4">
          <div className="flex items-center gap-2">
            <div className="relative max-w-xs flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Patient ID (patient or baby)"
                value={patientSearch}
                onChange={e => setPatientSearch(e.target.value)}
                className="pl-9 bg-background border-border text-foreground text-sm h-8"
              />
            </div>
            <Button size="sm" variant="outline" className="border-border h-8"
              disabled={!patientSearch}
              onClick={() => setImmunLookupId(Number(patientSearch))}>
              <Search className="w-3 h-3 mr-1" /> Load
            </Button>
            <Button size="sm" className="bg-blue-700 hover:bg-blue-800 h-8"
              disabled={!immunLookupId}
              onClick={() => { setImmunPatientId(immunLookupId); setImmunRows([{ ...emptyImmunisation }]); setImmunOpen(true); }}>
              <Syringe className="w-3 h-3 mr-1" /> Record Dose(s)
            </Button>
          </div>

          {!immunLookupId ? (
            <p className="text-muted-foreground text-sm">Enter a patient ID and click Load to see their immunisation schedule and history.</p>
          ) : (
            <div className="grid md:grid-cols-2 gap-4">
              <Card className="border-border bg-muted/20">
                <CardHeader><CardTitle className="text-sm">Vaccine Schedule — Patient {immunLookupId}</CardTitle></CardHeader>
                <CardContent className="p-0">
                  {scheduleLoading ? (
                    <div className="text-center py-6"><Loader2 className="w-5 h-5 animate-spin inline text-muted-foreground" /></div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow className="border-border">
                          <TableHead className="text-xs text-muted-foreground">Age</TableHead>
                          <TableHead className="text-xs text-muted-foreground">Vaccine</TableHead>
                          <TableHead className="text-xs text-muted-foreground">Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {vaccineSchedule.map((v: any) => (
                          <TableRow key={v.id} className="border-border/50">
                            <TableCell className="text-xs text-muted-foreground">{v.age_milestone}</TableCell>
                            <TableCell className="text-sm">{v.vaccine_name}</TableCell>
                            <TableCell>
                              {v.administered
                                ? <Badge variant="outline" className="text-xs bg-green-100 text-green-700 border-green-300">Given</Badge>
                                : <Badge variant="outline" className="text-xs bg-orange-100 text-orange-700 border-orange-300">Due</Badge>}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>

              <Card className="border-border bg-muted/20">
                <CardHeader><CardTitle className="text-sm">Immunisation History</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {immunHistory.length === 0
                    ? <p className="text-muted-foreground text-sm">No doses recorded yet</p>
                    : immunHistory.map((h: any) => (
                      <div key={h.id} className="flex justify-between items-center text-sm border-b border-border/50 pb-1">
                        <span>{h.vaccine_name} {h.dose_number ? `(dose ${h.dose_number})` : ""}</span>
                        <span className="text-xs text-muted-foreground">{h.date_given || "—"}</span>
                      </div>
                    ))}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* ── ANC Register Dialog ─────────────────────────────────────────────── */}
      <Dialog open={ancOpen} onOpenChange={setAncOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register ANC Patient</DialogTitle>
            <DialogDescription className="text-muted-foreground">Antenatal care registration</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "patient_id",            label: "Patient ID *",         type: "number" },
              { key: "encounter_id",           label: "Encounter ID",         type: "number" },
              { key: "gravida",                label: "Gravida",              type: "number" },
              { key: "para",                   label: "Para",                 type: "number" },
              { key: "lmp",                    label: "LMP (last period)",    type: "date" },
              { key: "edd",                    label: "Expected Delivery",    type: "date" },
              { key: "gestational_age_weeks",  label: "GA (weeks)",           type: "number" },
              { key: "blood_group",            label: "Blood Group" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type || "text"} value={(ancForm as any)[f.key] || ""}
                  onChange={e => setAncForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            {[
              { key: "rhesus",    label: "Rhesus",     opts: ["positive", "negative"] },
              { key: "hiv_status",label: "HIV Status", opts: ["negative", "positive", "unknown"] },
              { key: "hbsag",     label: "HBsAg",      opts: ["negative", "positive", "unknown"] },
              { key: "syphilis",  label: "Syphilis",   opts: ["negative", "positive", "unknown"] },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Select value={(ancForm as any)[f.key]}
                  onValueChange={v => setAncForm(p => ({ ...p, [f.key]: v }))}>
                  <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    {f.opts.map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ))}
            <div className="col-span-2 flex flex-wrap gap-4 mt-1">
              {[
                ["malaria_prophylaxis", "Malaria prophylaxis"],
                ["tetanus_toxoid", "Tetanus toxoid"],
                ["iron_folic_acid", "Iron/Folic acid"],
              ].map(([k, l]) => (
                <BoolCheck key={k} label={l} checked={!!(ancForm as any)[k]}
                  onChange={v => setAncForm(p => ({ ...p, [k]: v }))} />
              ))}
            </div>
            {[
              { key: "risk_factors",  label: "Risk Factors",   colSpan: 2 },
              { key: "referred_from", label: "Referred From" },
              { key: "notes",         label: "Notes",          colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Textarea value={(ancForm as any)[f.key] || ""}
                  onChange={e => setAncForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-16 resize-none" />
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setAncOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={ancMut.isPending || !ancForm.patient_id}
              onClick={() => ancMut.mutate(ancForm)}>
              {ancMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Register
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── ANC Visits View Dialog ─────────────────────────────────────────── */}
      <Dialog open={visitsViewOpen} onOpenChange={setVisitsViewOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>ANC Visits — Record #{visitsViewAncId}</DialogTitle>
          </DialogHeader>
          {visits.length === 0
            ? <p className="text-muted-foreground text-sm py-4 text-center">No visits recorded yet</p>
            : <Table>
                <TableHeader>
                  <TableRow className="border-border">
                    {["Date","GA","BP","FHR","Weight","Oedema","Notes"].map(h => (
                      <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visits.map((v: any) => (
                    <TableRow key={v.id} className="border-border/50">
                      <TableCell className="text-xs">{v.visit_date}</TableCell>
                      <TableCell className="text-xs">{v.gestational_age_weeks ?? "—"}</TableCell>
                      <TableCell className="text-xs">{v.bp_systolic && v.bp_diastolic ? `${v.bp_systolic}/${v.bp_diastolic}` : "—"}</TableCell>
                      <TableCell className="text-xs">{v.fetal_heart_rate ?? "—"}</TableCell>
                      <TableCell className="text-xs">{v.weight_kg ? `${v.weight_kg}kg` : "—"}</TableCell>
                      <TableCell className="text-xs">{v.oedema ? <span className="text-yellow-400">Yes</span> : "No"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">{v.notes || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
          }
          <DialogFooter>
            <Button variant="outline" className="border-border" onClick={() => setVisitsViewOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Log ANC Visit Dialog ──────────────────────────────────────────── */}
      <Dialog open={visitOpen} onOpenChange={setVisitOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ActivitySquare className="w-5 h-5 text-blue-400" />
              Log ANC Visit — #{visitAncId}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "visit_date",             label: "Visit Date",           type: "date" },
              { key: "gestational_age_weeks",  label: "GA (weeks)",           type: "number" },
              { key: "weight_kg",              label: "Weight (kg)",          type: "number" },
              { key: "bp_systolic",            label: "BP Systolic",          type: "number" },
              { key: "bp_diastolic",           label: "BP Diastolic",         type: "number" },
              { key: "fundal_height_cm",       label: "Fundal Height (cm)",   type: "number" },
              { key: "fetal_heart_rate",       label: "FHR (bpm)",            type: "number" },
              { key: "haemoglobin",            label: "Haemoglobin (g/dL)",   type: "number" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type} value={(visitForm as any)[f.key] || ""}
                  onChange={e => setVisitForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Presentation</Label>
              <Select value={visitForm.presentation || ""}
                onValueChange={v => setVisitForm(p => ({ ...p, presentation: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["cephalic", "breech", "transverse"].map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Malaria RDT</Label>
              <Select value={visitForm.malaria_rapid_test || ""}
                onValueChange={v => setVisitForm(p => ({ ...p, malaria_rapid_test: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["negative", "positive"].map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 flex gap-4">
              <BoolCheck label="Oedema" checked={visitForm.oedema} onChange={v => setVisitForm(p => ({ ...p, oedema: v }))} />
              <BoolCheck label="Proteinuria" checked={visitForm.proteinuria} onChange={v => setVisitForm(p => ({ ...p, proteinuria: v }))} />
            </div>
            {[
              { key: "drugs_given",       label: "Drugs Given",       colSpan: 2 },
              { key: "counselling_given", label: "Counselling Given",  colSpan: 2 },
              { key: "next_visit_date",   label: "Next Visit Date",   type: "date" },
              { key: "clinician_id",      label: "Clinician ID" },
              { key: "notes",             label: "Notes",             colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                {(f as any).colSpan === 2 && !f.type
                  ? <Textarea value={(visitForm as any)[f.key] || ""}
                      onChange={e => setVisitForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-12 resize-none" />
                  : <Input type={f.type || "text"} value={(visitForm as any)[f.key] || ""}
                      onChange={e => setVisitForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-8" />
                }
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setVisitOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={visitMut.isPending}
              onClick={() => visitMut.mutate(visitForm)}>
              {visitMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Visit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Record Delivery Dialog ──────────────────────────────────────────── */}
      <Dialog open={deliveryOpen} onOpenChange={setDeliveryOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Baby className="w-5 h-5 text-blue-400" />
              Record Delivery — ANC #{deliveryAncId}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Delivery Date</Label>
              <Input type="date" value={deliveryForm.delivery_date}
                onChange={e => setDeliveryForm(p => ({ ...p, delivery_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Delivery Time</Label>
              <Input type="time" value={deliveryForm.delivery_time}
                onChange={e => setDeliveryForm(p => ({ ...p, delivery_time: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Mode of Delivery</Label>
              <Select value={deliveryForm.mode_of_delivery}
                onValueChange={v => setDeliveryForm(p => ({ ...p, mode_of_delivery: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["svd","assisted","cs","breech"].map(o => <SelectItem key={o} value={o} className="uppercase">{o.toUpperCase()}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Anaesthesia</Label>
              <Input value={deliveryForm.anaesthesia_type}
                onChange={e => setDeliveryForm(p => ({ ...p, anaesthesia_type: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            {[
              { key: "duration_of_labour_hours", label: "Labour Duration (hrs)", type: "number" },
              { key: "blood_loss_ml",            label: "Blood Loss (mL)",       type: "number" },
              { key: "perineal_tear",            label: "Perineal Tear Grade" },
              { key: "attending_clinician",      label: "Attending Clinician" },
              { key: "indication",               label: "Indication (if CS/assisted)", colSpan: 2 },
              { key: "maternal_complications",   label: "Maternal Complications", colSpan: 2 },
              { key: "notes",                    label: "Notes",                  colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                {(f as any).colSpan === 2
                  ? <Textarea value={(deliveryForm as any)[f.key] || ""}
                      onChange={e => setDeliveryForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-14 resize-none" />
                  : <Input type={f.type || "text"} value={(deliveryForm as any)[f.key] || ""}
                      onChange={e => setDeliveryForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-8" />
                }
              </div>
            ))}
            <div className="col-span-2 flex gap-4">
              <BoolCheck label="Placenta complete" checked={deliveryForm.placenta_complete}
                onChange={v => setDeliveryForm(p => ({ ...p, placenta_complete: v }))} />
              <BoolCheck label="Episiotomy performed" checked={deliveryForm.episiotomy}
                onChange={v => setDeliveryForm(p => ({ ...p, episiotomy: v }))} />
            </div>
          </div>
          <DialogFooter className="mt-4 gap-2">
            <Button variant="outline" className="border-border" onClick={() => setDeliveryOpen(false)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700"
              disabled={deliveryMut.isPending}
              onClick={() => deliveryMut.mutate(deliveryForm)}>
              {deliveryMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Record Delivery
            </Button>
            <Button variant="outline" className="border-sky-500/50 text-sky-400 hover:bg-sky-500/10"
              onClick={() => {
                setDeliveryOpen(false);
                setNewbornDeliveryId(null);
                setNewbornOpen(true);
              }}>
              <Baby className="w-3 h-3 mr-1" /> + Newborn Assessment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Newborn Assessment Dialog ──────────────────────────────────────── */}
      <Dialog open={newbornOpen} onOpenChange={setNewbornOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Baby className="w-5 h-5 text-sky-400" />
              Newborn Assessment
            </DialogTitle>
            <DialogDescription className="text-muted-foreground text-sm">
              Delivery ID: {newbornDeliveryId ?? "enter below"}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {!newbornDeliveryId && (
              <div className="col-span-2 space-y-1">
                <Label className="text-xs text-muted-foreground">Delivery Record ID *</Label>
                <Input type="number" placeholder="Enter delivery ID"
                  onChange={e => setNewbornDeliveryId(Number(e.target.value) || null)}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            )}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Sex</Label>
              <Select value={newbornForm.sex}
                onValueChange={v => setNewbornForm(p => ({ ...p, sex: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["male","female","indeterminate"].map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {[
              { key: "birth_weight_kg",        label: "Birth Weight (kg)",   type: "number" },
              { key: "length_cm",              label: "Length (cm)",          type: "number" },
              { key: "head_circumference_cm",  label: "Head Circ. (cm)",      type: "number" },
              { key: "apgar_1min",             label: "Apgar 1min (0-10)",    type: "number" },
              { key: "apgar_5min",             label: "Apgar 5min (0-10)",    type: "number" },
              { key: "apgar_10min",            label: "Apgar 10min (0-10)",   type: "number" },
              { key: "gestational_age_at_birth",label: "GA at Birth (wks)",  type: "number" },
              { key: "resuscitation_type",     label: "Resuscitation Type" },
              { key: "congenital_anomalies",   label: "Congenital Anomalies", colSpan: 2 },
              { key: "notes",                  label: "Notes",                colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                {(f as any).colSpan === 2
                  ? <Textarea value={(newbornForm as any)[f.key] || ""}
                      onChange={e => setNewbornForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-14 resize-none" />
                  : <Input type={f.type || "text"} value={(newbornForm as any)[f.key] || ""}
                      onChange={e => setNewbornForm(p => ({ ...p, [f.key]: e.target.value }))}
                      className="bg-background border-border text-foreground text-sm h-8" />
                }
              </div>
            ))}
            <div className="col-span-2 grid grid-cols-2 gap-2">
              {[
                ["cry_at_birth",           "Cry at birth"],
                ["resuscitation_needed",   "Resuscitation needed"],
                ["eye_prophylaxis",        "Eye prophylaxis given"],
                ["vitamin_k_given",        "Vitamin K given"],
                ["bcg_given",              "BCG given"],
                ["opv0_given",             "OPV 0 given"],
                ["hbv_given",              "HBV birth dose given"],
                ["breast_feeding_initiated","Breastfeeding initiated"],
              ].map(([k, l]) => (
                <BoolCheck key={k} label={l} checked={!!(newbornForm as any)[k]}
                  onChange={v => setNewbornForm(p => ({ ...p, [k]: v }))} />
              ))}
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setNewbornOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={newbornMut.isPending || !newbornDeliveryId}
              onClick={() => newbornMut.mutate(newbornForm)}>
              {newbornMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Assessment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Immunisation Dialog ─────────────────────────────────────────────── */}
      <Dialog open={immunOpen} onOpenChange={setImmunOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Syringe className="w-5 h-5 text-blue-400" />
              Log Immunisation — Patient {immunPatientId}
            </DialogTitle>
            <DialogDescription className="text-muted-foreground text-xs">
              Add one row per dose being given today — submits together in a single call.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            {immunRows.map((row, i) => (
              <div key={i} className="rounded border border-border p-3 space-y-2 relative">
                {immunRows.length > 1 && (
                  <Button size="icon" variant="ghost" className="absolute top-1 right-1 h-6 w-6"
                    onClick={() => setImmunRows(rows => rows.filter((_, j) => j !== i))}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2 space-y-1">
                    <Label className="text-xs text-muted-foreground">Vaccine Name *</Label>
                    {vaccineSchedule.length > 0 ? (
                      <Select value={row.vaccine_name}
                        onValueChange={v => setImmunRows(rows => rows.map((r, j) => j === i ? { ...r, vaccine_name: v } : r))}>
                        <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue placeholder="Select vaccine…" /></SelectTrigger>
                        <SelectContent className="bg-popover border-border">
                          {Array.from(new Set(vaccineSchedule.map((v: any) => v.vaccine_name))).map((name: any) => (
                            <SelectItem key={name} value={name}>{name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input value={row.vaccine_name}
                        onChange={e => setImmunRows(rows => rows.map((r, j) => j === i ? { ...r, vaccine_name: e.target.value } : r))}
                        className="bg-background border-border text-foreground text-sm h-8" />
                    )}
                  </div>
                  {[
                    { key: "dose_number",   label: "Dose No.",     type: "number" },
                    { key: "date_given",    label: "Date Given",   type: "date" },
                    { key: "batch_number",  label: "Batch No." },
                    { key: "site",          label: "Site (LTA/RTA/oral)" },
                    { key: "next_due_date", label: "Next Due",     type: "date" },
                    { key: "reaction",      label: "Reaction" },
                  ].map(f => (
                    <div key={f.key} className="space-y-1">
                      <Label className="text-xs text-muted-foreground">{f.label}</Label>
                      <Input type={f.type || "text"} value={(row as any)[f.key] || ""}
                        onChange={e => setImmunRows(rows => rows.map((r, j) => j === i ? { ...r, [f.key]: e.target.value } : r))}
                        className="bg-background border-border text-foreground text-sm h-8" />
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <Button size="sm" variant="outline" className="border-border gap-1"
              onClick={() => setImmunRows(rows => [...rows, { ...emptyImmunisation }])}>
              <Plus className="w-3.5 h-3.5" /> Add Dose
            </Button>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setImmunOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={immunMut.isPending || !immunRows.some(r => r.vaccine_name.trim()) || !immunPatientId}
              onClick={() => immunMut.mutate(immunRows)}>
              {immunMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save {immunRows.filter(r => r.vaccine_name.trim()).length || ""} Dose(s)
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Baby Created Dialog (after Newborn Assessment) ───────────────────── */}
      <Dialog open={babyResultOpen} onOpenChange={setBabyResultOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Baby className="w-5 h-5 text-sky-400" /> Baby Record Created
            </DialogTitle>
            <DialogDescription className="text-muted-foreground text-sm">
              A new patient record was created for this newborn.
            </DialogDescription>
          </DialogHeader>
          {babyResult && (
            <div className="space-y-1 text-sm">
              <p><span className="text-muted-foreground">Name:</span> {babyResult.first_name} {babyResult.last_name}</p>
              <p><span className="text-muted-foreground">MRN:</span> {babyResult.mrn}</p>
              <p><span className="text-muted-foreground">DOB:</span> {babyResult.date_of_birth}</p>
              <p><span className="text-muted-foreground">Gender:</span> {babyResult.gender ?? "—"}</p>
            </div>
          )}
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border"
              onClick={() => {
                setImmunPatientId(babyResult?.id ?? null);
                setImmunLookupId(babyResult?.id ?? null);
                setImmunRows([{ ...emptyImmunisation }]);
                setBabyResultOpen(false);
                setImmunOpen(true);
              }}>
              <Syringe className="w-3.5 h-3.5 mr-1" /> Log Immunisation
            </Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              onClick={() => { setBabyResultOpen(false); if (babyResult?.mrn) navigate(`/hospital/patients/${babyResult.mrn}`); }}>
              <ChevronRight className="w-3.5 h-3.5 mr-1" /> View Baby Chart
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
