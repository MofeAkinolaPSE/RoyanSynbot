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
  ShieldCheck, RefreshCw, Loader2, Plus, AlertTriangle,
  Bug, ClipboardList, ChevronRight, CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { StaffPicker } from "@/components/shared/StaffPicker";

const SEVERITY_COLORS: Record<string, string> = {
  near_miss: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  minor:     "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  moderate:  "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  major:     "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  sentinel:  "bg-red-700/30 text-red-700 dark:text-red-300 border-red-700/50",
};

const STATUS_COLORS: Record<string, string> = {
  reported:      "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  under_review:  "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  investigated:  "bg-sky-500/20 text-sky-700 dark:text-sky-400 border-sky-500/30",
  closed:        "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  escalated:     "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
};

const STATUS_NEXT: Record<string, string> = {
  reported:     "under_review",
  under_review: "investigated",
  investigated: "closed",
  escalated:    "investigated",
};

const CATEGORIES = [
  "medication_error","patient_fall","pressure_injury","surgical_complication",
  "equipment_failure","infection","documentation_error","delay_in_treatment",
  "violence_aggression","other",
];

const HEFAMAA_SECTIONS = [
  {
    title: "A — Environment & Infrastructure",
    fields: [
      ["clean_water_available",         "Clean water available"],
      ["waste_management_compliant",    "Waste management compliant"],
      ["fire_safety_equipment",         "Fire safety equipment present"],
      ["emergency_exits_clear",         "Emergency exits clear"],
      ["adequate_lighting",             "Adequate lighting"],
      ["hand_hygiene_stations",         "Hand hygiene stations stocked"],
    ],
  },
  {
    title: "B — Clinical Standards",
    fields: [
      ["medication_storage_correct",        "Medication storage correct"],
      ["cold_chain_maintained",             "Cold chain maintained"],
      ["sterilisation_process_compliant",   "Sterilisation process compliant"],
      ["patient_records_secured",           "Patient records secured"],
      ["informed_consent_documented",       "Informed consent documented"],
      ["infection_control_protocols_posted","Infection control protocols posted"],
    ],
  },
  {
    title: "C — Staffing",
    fields: [
      ["staff_registers_current",   "Staff registers current"],
      ["cpd_records_maintained",    "CPD records maintained"],
      ["staff_uniforms_worn",       "Staff uniforms worn"],
    ],
  },
  {
    title: "D — Equipment",
    fields: [
      ["equipment_calibration_current",   "Equipment calibration current"],
      ["biomedical_maintenance_records",  "Biomedical maintenance records"],
      ["crash_cart_stocked",              "Crash cart stocked"],
      ["oxygen_supply_available",         "Oxygen supply available"],
    ],
  },
];

function BoolCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <div onClick={() => onChange(!checked)}
        className={cn(
          "w-4 h-4 rounded border flex items-center justify-center cursor-pointer transition-colors flex-shrink-0",
          checked ? "bg-green-100 border-green-500" : "border-border hover:border-primary/50"
        )}>
        {checked && <CheckCircle2 className="w-2.5 h-2.5 text-green-600" />}
      </div>
      <span className="text-xs text-muted-foreground">{label}</span>
    </label>
  );
}

const emptyIncident = {
  category: "other", severity: "minor", ward: "", patient_id: "",
  encounter_id: "", incident_date: "", incident_time: "",
  description: "", immediate_action_taken: "", witnesses: "",
  contributing_factors: "",
};

const emptyInfection = {
  event_type: "", pathogen: "", specimen_type: "", ward: "",
  patient_id: "", encounter_id: "", onset_date: "", culture_result: "",
  healthcare_associated: true, antibiotic_resistant: false,
  antibiotics_prescribed: "", isolation_precautions: "", outcome: "", notes: "",
};

const emptyHefamaa = Object.fromEntries(
  HEFAMAA_SECTIONS.flatMap(s => s.fields.map(([k]) => [k, false]))
) as Record<string, boolean>;

export default function QualitySafety() {
  const { toast } = useToast();
  const qc = useQueryClient();

  const [filterStatus, setFilterStatus] = useState("all");
  const [filterSeverity, setFilterSeverity] = useState("all");

  const [incidentOpen, setIncidentOpen] = useState(false);
  const [incidentForm, setIncidentForm] = useState({ ...emptyIncident });

  const [infectionOpen, setInfectionOpen] = useState(false);
  const [infectionForm, setInfectionForm] = useState({ ...emptyInfection });

  const [hefamaaOpen, setHefamaaOpen] = useState(false);
  const [hefamaaForm, setHefamaaForm] = useState({
    ...emptyHefamaa, assessor: "", department: "", assessment_date: "",
    observations: "", recommendations: "", follow_up_date: "",
  });

  const [investigateOpen, setInvestigateOpen] = useState(false);
  const [investigateId, setInvestigateId] = useState<string | null>(null);
  const [investigateForm, setInvestigateForm] = useState({
    root_cause: "", contributing_factors: "", corrective_actions: "",
    preventive_actions: "", investigated_by: "", outcome: "",
  });

  // Queries
  const { data: statsData } = useQuery({
    queryKey: ["quality-stats"],
    queryFn: () => api.quality.stats(),
  });

  const { data: incidentsData, isLoading: incLoading, refetch: refetchInc } = useQuery({
    queryKey: ["quality-incidents", filterStatus, filterSeverity],
    queryFn: () => api.quality.listIncidents({
      status:   filterStatus   !== "all" ? filterStatus   : undefined,
      severity: filterSeverity !== "all" ? filterSeverity : undefined,
    }),
  });

  const { data: infectionStatsData } = useQuery({
    queryKey: ["infection-stats"],
    queryFn: () => api.quality.infectionStats(),
  });

  const { data: hefamaaData, refetch: refetchHefamaa } = useQuery({
    queryKey: ["hefamaa-list"],
    queryFn: () => api.quality.listHefamaa(),
  });

  const stats    = statsData?.incidents  || { total: 0, open: 0, by_severity: {}, by_status: {}, by_category: {} };
  const infStats = infectionStatsData    || { total: 0, hai_count: 0, amr_count: 0 };
  const hefStats = statsData?.hefamaa    || { submissions: 0, avg_score: 0 };
  const incidents = incidentsData?.incidents || [];
  const hefamaas  = hefamaaData?.checklists  || [];

  // Mutations
  const incidentMut = useMutation({
    mutationFn: () => api.quality.reportIncident({
      ...incidentForm,
      patient_id:  incidentForm.patient_id  ? Number(incidentForm.patient_id)  : undefined,
      encounter_id: incidentForm.encounter_id ? Number(incidentForm.encounter_id) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Incident reported" });
      setIncidentOpen(false);
      setIncidentForm({ ...emptyIncident });
      qc.invalidateQueries({ queryKey: ["quality-incidents"] });
      qc.invalidateQueries({ queryKey: ["quality-stats"] });
    },
    onError: () => toast({ title: "Failed to report incident", variant: "destructive" }),
  });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.quality.updateIncidentStatus(id, { status }),
    onSuccess: () => {
      toast({ title: "Status updated" });
      qc.invalidateQueries({ queryKey: ["quality-incidents"] });
      qc.invalidateQueries({ queryKey: ["quality-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Update failed", variant: "destructive" }),
  });

  const investigateMut = useMutation({
    mutationFn: () => api.quality.submitInvestigation(investigateId!, investigateForm),
    onSuccess: () => {
      toast({ title: "Investigation submitted" });
      setInvestigateOpen(false);
      qc.invalidateQueries({ queryKey: ["quality-incidents"] });
    },
    onError: () => toast({ title: "Failed to submit investigation", variant: "destructive" }),
  });

  const infectionMut = useMutation({
    mutationFn: () => api.quality.logInfection({
      ...infectionForm,
      patient_id: infectionForm.patient_id ? Number(infectionForm.patient_id) : undefined,
      encounter_id: infectionForm.encounter_id ? Number(infectionForm.encounter_id) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Infection event logged" });
      setInfectionOpen(false);
      setInfectionForm({ ...emptyInfection });
      qc.invalidateQueries({ queryKey: ["infection-stats"] });
      qc.invalidateQueries({ queryKey: ["quality-stats"] });
    },
    onError: () => toast({ title: "Failed to log infection event", variant: "destructive" }),
  });

  const hefamaaMut = useMutation({
    mutationFn: () => api.quality.submitHefamaa(hefamaaForm),
    onSuccess: (d) => {
      toast({ title: `HEFAMAA submitted — Score: ${d.score}%` });
      setHefamaaOpen(false);
      setHefamaaForm({ ...emptyHefamaa, assessor: "", department: "", assessment_date: "", observations: "", recommendations: "", follow_up_date: "" });
      refetchHefamaa();
      qc.invalidateQueries({ queryKey: ["quality-stats"] });
    },
    onError: () => toast({ title: "Failed to submit HEFAMAA checklist", variant: "destructive" }),
  });

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 rounded-lg">
            <ShieldCheck className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Quality & Safety</h1>
            <p className="text-sm text-muted-foreground">Incident reporting, infection surveillance, and HEFAMAA compliance</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <Button variant="outline" size="sm" className="border-border" onClick={() => refetchInc()}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" variant="outline" className="border-orange-500/40 text-orange-700 dark:text-orange-400 hover:bg-orange-500/10"
            onClick={() => setInfectionOpen(true)}>
            <Bug className="w-4 h-4 mr-1" /> Log Infection
          </Button>
          <Button size="sm" variant="outline" className="border-blue-500/40 text-blue-700 dark:text-blue-400 hover:bg-blue-500/10"
            onClick={() => setHefamaaOpen(true)}>
            <ClipboardList className="w-4 h-4 mr-1" /> HEFAMAA
          </Button>
          <Button size="sm" className="bg-red-600 hover:bg-red-700"
            onClick={() => setIncidentOpen(true)}>
            <AlertTriangle className="w-4 h-4 mr-1" /> Report Incident
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Total Incidents",  value: stats.total,          color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Open",             value: stats.open,           color: stats.open > 0 ? "text-red-700" : "text-green-700", bg: stats.open > 0 ? "bg-red-50" : "bg-green-50" },
          { label: "HAI Events",       value: infStats.hai_count,   color: "text-orange-700 dark:text-orange-400",  bg: "bg-orange-500/10" },
          { label: "AMR Cases",        value: infStats.amr_count,   color: "text-red-700 dark:text-red-400",     bg: "bg-red-500/10" },
          { label: "HEFAMAA Avg Score",value: `${hefStats.avg_score}%`, color: hefStats.avg_score >= 80 ? "text-green-700" : "text-yellow-700", bg: "bg-muted/30" },
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
      <Tabs defaultValue="incidents">
        <TabsList className="bg-muted border border-border">
          <TabsTrigger value="incidents">Incidents</TabsTrigger>
          <TabsTrigger value="infection">Infection Control</TabsTrigger>
          <TabsTrigger value="hefamaa">HEFAMAA</TabsTrigger>
        </TabsList>

        {/* Incidents Tab */}
        <TabsContent value="incidents" className="mt-4 space-y-4">
          <div className="flex gap-2 flex-wrap">
            {["all","reported","under_review","investigated","escalated","closed"].map(s => (
              <button key={s} onClick={() => setFilterStatus(s)}
                className={cn("px-3 py-1 rounded-full text-xs border transition-colors",
                  filterStatus === s ? "bg-blue-700 border-blue-600 text-foreground" : "border-border text-muted-foreground hover:border-primary/50")}>
                {s === "all" ? "All Statuses" : s.replace("_", " ")}
              </button>
            ))}
            <div className="ml-2 flex gap-2">
              {["all","near_miss","minor","moderate","major","sentinel"].map(sv => (
                <button key={sv} onClick={() => setFilterSeverity(sv)}
                  className={cn("px-3 py-1 rounded-full text-xs border transition-colors",
                    filterSeverity === sv ? "bg-red-600 border-red-500 text-foreground" : "border-border text-muted-foreground hover:border-primary/50")}>
                  {sv === "all" ? "All Severities" : sv.replace("_", " ")}
                </button>
              ))}
            </div>
          </div>

          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["ID","Date","Category","Ward","Severity","Status","Actions"].map(h => (
                    <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {incLoading
                  ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : incidents.length === 0
                    ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No incidents found</TableCell></TableRow>
                    : incidents.map((inc: any) => {
                        const nextStatus = STATUS_NEXT[inc.status];
                        return (
                          <TableRow key={inc.id} className="border-border hover:bg-muted">
                            <TableCell className="font-mono text-xs text-muted-foreground">{inc.id}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{inc.incident_date}</TableCell>
                            <TableCell className="text-xs text-muted-foreground capitalize">{inc.category?.replace("_"," ")}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{inc.ward || "—"}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className={cn("text-xs capitalize", SEVERITY_COLORS[inc.severity] || "")}>
                                {inc.severity?.replace("_"," ")}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className={cn("text-xs", STATUS_COLORS[inc.status] || "")}>
                                {inc.status?.replace("_"," ")}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <div className="flex gap-1">
                                {inc.status === "under_review" && (
                                  <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                                    onClick={() => { setInvestigateId(inc.id); setInvestigateOpen(true); }}>
                                    Investigate
                                  </Button>
                                )}
                                {nextStatus && (
                                  <Button size="sm" className="h-6 text-xs px-2 bg-blue-700 hover:bg-blue-600"
                                    disabled={statusMut.isPending}
                                    onClick={() => statusMut.mutate({ id: inc.id, status: nextStatus })}>
                                    {nextStatus.replace("_"," ")} <ChevronRight className="w-3 h-3 ml-1" />
                                  </Button>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Infection Control Tab */}
        <TabsContent value="infection" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="border-border bg-muted/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">By Infection Type</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(infStats.by_infection_type || {}).length === 0
                  ? <p className="text-muted-foreground text-sm">No infection data</p>
                  : Object.entries(infStats.by_infection_type || {})
                      .sort(([,a],[,b]) => (b as number) - (a as number))
                      .map(([type, count]) => (
                        <div key={type} className="flex justify-between items-center">
                          <span className="text-sm text-muted-foreground">{type}</span>
                          <span className="text-foreground font-semibold">{count as number}</span>
                        </div>
                      ))
                }
              </CardContent>
            </Card>
            <Card className="border-border bg-muted/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">By Ward</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(infStats.by_ward || {}).length === 0
                  ? <p className="text-muted-foreground text-sm">No data</p>
                  : Object.entries(infStats.by_ward || {})
                      .sort(([,a],[,b]) => (b as number) - (a as number))
                      .map(([ward, count]) => (
                        <div key={ward} className="flex justify-between items-center">
                          <span className="text-sm text-muted-foreground">{ward}</span>
                          <span className="text-foreground font-semibold">{count as number}</span>
                        </div>
                      ))
                }
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* HEFAMAA Tab */}
        <TabsContent value="hefamaa" className="mt-4">
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["ID","Date","Inspector","Department","Score","Follow-up"].map(h => (
                    <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {hefamaas.length === 0
                  ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No HEFAMAA submissions yet</TableCell></TableRow>
                  : hefamaas.map((h: any) => (
                    <TableRow key={h.id} className="border-border hover:bg-muted">
                      <TableCell className="font-mono text-xs text-muted-foreground">{h.id}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{h.assessment_date}</TableCell>
                      <TableCell className="text-sm text-foreground">{h.assessor_name || "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{h.department || "—"}</TableCell>
                      <TableCell>
                        <span className={cn("text-sm font-bold",
                          h.overall_score >= 80 ? "text-green-700 dark:text-green-400" : h.overall_score >= 60 ? "text-yellow-700 dark:text-yellow-400" : "text-red-700 dark:text-red-400"
                        )}>{h.overall_score}%</span>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{h.follow_up_date || "—"}</TableCell>
                    </TableRow>
                  ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Report Incident Dialog ─────────────────────────────────────────── */}
      <Dialog open={incidentOpen} onOpenChange={setIncidentOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400" />
              Report Clinical Incident
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Category</Label>
              <Select value={incidentForm.category} onValueChange={v => setIncidentForm(p => ({ ...p, category: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {CATEGORIES.map(c => <SelectItem key={c} value={c} className="capitalize">{c.replace(/_/g," ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Severity</Label>
              <Select value={incidentForm.severity} onValueChange={v => setIncidentForm(p => ({ ...p, severity: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["near_miss","minor","moderate","major","sentinel"].map(s =>
                    <SelectItem key={s} value={s} className="capitalize">{s.replace("_"," ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {[
              { key: "ward",          label: "Ward / Location" },
              { key: "patient_id",    label: "Patient ID",    type: "number" },
              { key: "encounter_id",  label: "Encounter ID",  type: "number" },
              { key: "incident_date", label: "Incident Date", type: "date" },
              { key: "incident_time", label: "Incident Time", type: "time" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type || "text"} value={(incidentForm as any)[f.key] || ""}
                  onChange={e => setIncidentForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            {[
              { key: "description",            label: "Description *", colSpan: 2 },
              { key: "immediate_action_taken", label: "Immediate Action Taken", colSpan: 2 },
              { key: "witnesses",              label: "Witnesses" },
              { key: "equipment_involved",     label: "Equipment Involved" },
              { key: "contributing_factors",   label: "Contributing Factors", colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Textarea value={(incidentForm as any)[f.key] || ""}
                  onChange={e => setIncidentForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-16 resize-none" />
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setIncidentOpen(false)}>Cancel</Button>
            <Button className="bg-red-600 hover:bg-red-700"
              disabled={incidentMut.isPending || !incidentForm.description}
              onClick={() => incidentMut.mutate()}>
              {incidentMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Submit Report
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Investigation Dialog ───────────────────────────────────────────── */}
      <Dialog open={investigateOpen} onOpenChange={setInvestigateOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Submit Investigation — Incident #{investigateId}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            {[
              { key: "root_cause",          label: "Root Cause *" },
              { key: "contributing_factors",label: "Contributing Factors" },
              { key: "corrective_actions",  label: "Corrective Actions" },
              { key: "preventive_actions",  label: "Preventive Actions" },
              { key: "outcome",             label: "Outcome" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Textarea value={(investigateForm as any)[f.key] || ""}
                  onChange={e => setInvestigateForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-16 resize-none" />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Investigated By</Label>
              <StaffPicker value={investigateForm.investigated_by}
                onChange={id => setInvestigateForm(p => ({ ...p, investigated_by: id }))} />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setInvestigateOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={investigateMut.isPending || !investigateForm.root_cause}
              onClick={() => investigateMut.mutate()}>
              {investigateMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Log Infection Dialog ───────────────────────────────────────────── */}
      <Dialog open={infectionOpen} onOpenChange={setInfectionOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bug className="w-5 h-5 text-orange-400" />Log Infection Control Event
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "event_type",       label: "Infection Type *",  colSpan: 2 },
              { key: "pathogen",         label: "Pathogen" },
              { key: "specimen_type",    label: "Specimen Type" },
              { key: "ward",             label: "Ward" },
              { key: "patient_id",       label: "Patient ID",     type: "number" },
              { key: "encounter_id",     label: "Encounter ID",   type: "number" },
              { key: "onset_date",       label: "Onset Date",     type: "date" },
              { key: "culture_result",   label: "Culture Result", colSpan: 2 },
              { key: "antibiotics_prescribed", label: "Antibiotics Prescribed", colSpan: 2 },
              { key: "isolation_precautions",  label: "Isolation Precautions" },
              { key: "outcome",          label: "Outcome" },
              { key: "notes",            label: "Notes",          colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type || "text"} value={(infectionForm as any)[f.key] || ""}
                  onChange={e => setInfectionForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            <div className="col-span-2 flex gap-4">
              <BoolCheck label="Healthcare-associated infection (HAI)"
                checked={infectionForm.healthcare_associated}
                onChange={v => setInfectionForm(p => ({ ...p, healthcare_associated: v }))} />
              <BoolCheck label="Antibiotic resistant (AMR)"
                checked={infectionForm.antibiotic_resistant}
                onChange={v => setInfectionForm(p => ({ ...p, antibiotic_resistant: v }))} />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setInfectionOpen(false)}>Cancel</Button>
            <Button className="bg-orange-600 hover:bg-orange-700"
              disabled={infectionMut.isPending || !infectionForm.event_type}
              onClick={() => infectionMut.mutate()}>
              {infectionMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Log Event
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── HEFAMAA Checklist Dialog ───────────────────────────────────────── */}
      <Dialog open={hefamaaOpen} onOpenChange={setHefamaaOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ClipboardList className="w-5 h-5 text-sky-400" />
              HEFAMAA Facility Inspection Checklist
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Inspector</Label>
                <StaffPicker value={hefamaaForm.assessor}
                  onChange={id => setHefamaaForm(p => ({ ...p, assessor: id }))} />
              </div>
              {[
                { key: "department",       label: "Department" },
                { key: "assessment_date",  label: "Date", type: "date" },
              ].map(f => (
                <div key={f.key} className="space-y-1">
                  <Label className="text-xs text-muted-foreground">{f.label}</Label>
                  <Input type={f.type || "text"} value={(hefamaaForm as any)[f.key] || ""}
                    onChange={e => setHefamaaForm(p => ({ ...p, [f.key]: e.target.value }))}
                    className="bg-background border-border text-foreground text-sm h-8" />
                </div>
              ))}
            </div>
            {HEFAMAA_SECTIONS.map(section => (
              <div key={section.title} className="space-y-2">
                <p className="text-xs font-semibold text-sky-700 dark:text-sky-400 uppercase tracking-wide">{section.title}</p>
                <div className="grid grid-cols-2 gap-2 pl-2">
                  {section.fields.map(([key, label]) => (
                    <BoolCheck key={key} label={label}
                      checked={!!(hefamaaForm as any)[key]}
                      onChange={v => setHefamaaForm(p => ({ ...p, [key]: v }))} />
                  ))}
                </div>
              </div>
            ))}
            {[
              { key: "observations",    label: "Observations" },
              { key: "recommendations", label: "Recommendations" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Textarea value={(hefamaaForm as any)[f.key] || ""}
                  onChange={e => setHefamaaForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-16 resize-none" />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Follow-up Date</Label>
              <Input type="date" value={(hefamaaForm as any).follow_up_date || ""}
                onChange={e => setHefamaaForm(p => ({ ...p, follow_up_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8 w-44" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setHefamaaOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={hefamaaMut.isPending}
              onClick={() => hefamaaMut.mutate()}>
              {hefamaaMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Submit Checklist
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
