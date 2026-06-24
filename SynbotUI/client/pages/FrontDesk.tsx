import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Loader2, Search, UserCheck, Ticket, Users, Clock, Activity, RefreshCw, ChevronRight } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { useNavigate, useLocation } from "react-router-dom";

const DEPARTMENTS = [
  "OPD", "A&E", "Maternity", "Surgery", "Inpatient Ward",
  "Laboratory & Diagnostics", "Pharmacy", "Billing & Finance", "Administration",
];

const ENCOUNTER_TYPES = [
  { value: "outpatient",  label: "Walk-In / Outpatient" },
  { value: "emergency",   label: "Emergency" },
  { value: "inpatient",   label: "Inpatient Admission" },
  { value: "maternity",   label: "Maternity" },
  { value: "surgical",    label: "Surgical" },
];

const PRIORITIES = [
  { value: "normal",    label: "Normal", color: "text-green-400" },
  { value: "urgent",    label: "Urgent", color: "text-yellow-400" },
  { value: "emergency", label: "Emergency", color: "text-red-400" },
];

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const d = new Date(dob);
  const age = Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000));
  return isNaN(age) ? "—" : `${age}y`;
}

export default function FrontDesk() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [searchQuery, setSearchQuery]       = useState("");
  const [debouncedQ, setDebouncedQ]         = useState("");
  const [selectedPatient, setSelectedPatient] = useState<any>(null);
  const [showForm, setShowForm]             = useState(false);
  const [issuedTicket, setIssuedTicket]     = useState<{ queue_number?: string; encounter: any } | null>(null);
  const [priority, setPriority]             = useState("normal");
  const [form, setForm] = useState({
    department: "OPD",
    encounter_type: "outpatient",
    chief_complaint: "",
  });

  // Live queue KPIs + department breakdown (single call to hospital-status)
  const { data: statusData, refetch: refetchKpi } = useQuery({
    queryKey: ["fd-hospital-status"],
    queryFn: () => api.dashboard.hospitalStatus(),
    refetchInterval: 30_000,
  });
  const kpis = statusData?.kpis ?? statusData ?? {};
  const deptQueue: any[] = Array.isArray(statusData?.queue_by_department)
    ? statusData.queue_by_department
    : [];

  // Patient search
  const { data: searchData, isFetching: searching } = useQuery({
    queryKey: ["fd-patient-search", debouncedQ],
    queryFn: () => api.hospital.patients.search(debouncedQ),
    enabled: debouncedQ.length >= 2,
  });
  const patients: any[] = Array.isArray(searchData) ? searchData : (searchData?.patients ?? []);

  const handleSearchChange = (val: string) => {
    setSearchQuery(val);
    setSelectedPatient(null);
    setShowForm(false);
    setIssuedTicket(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQ(val), 400);
  };

  const handleSelectPatient = (p: any) => {
    setSelectedPatient(p);
    setShowForm(true);
    setIssuedTicket(null);
  };

  // Pre-fill patient when navigated from the Patient Registry side panel
  useEffect(() => {
    const pre = (location.state as any)?.prefillPatient;
    if (pre?.id) {
      handleSelectPatient(pre);
      // Clear router state so a back-navigation doesn't re-trigger
      window.history.replaceState({}, "");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEncounterMut = useMutation({
    mutationFn: () =>
      api.hospital.queue.open({
        patient_id: selectedPatient?.id,
        department: form.department,
        encounter_type: form.encounter_type,
        chief_complaint: form.chief_complaint || undefined,
      }),
    onSuccess: (data) => {
      const enc = data?.encounter ?? data;
      setIssuedTicket({ queue_number: enc?.queue_number, encounter: enc });
      setShowForm(false);
      void qc.invalidateQueries({ queryKey: ["fd-kpis"] });
      void qc.invalidateQueries({ queryKey: ["fd-dept-queue"] });
      toast({ title: "Encounter registered", description: `Ticket ${enc?.queue_number ?? enc?.id} issued` });
    },
    onError: (e: any) =>
      toast({ title: "Registration failed", description: e.message, variant: "destructive" }),
  });

  const resetAll = () => {
    setSearchQuery("");
    setDebouncedQ("");
    setSelectedPatient(null);
    setShowForm(false);
    setIssuedTicket(null);
    setForm({ department: "OPD", encounter_type: "outpatient", chief_complaint: "" });
    setPriority("normal");
  };

  return (
    <motion.div className="flex flex-col gap-6" {...motionTransitions.fadeInUp}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Front Desk</h1>
          <p className="text-sm text-muted-foreground">Patient check-in and encounter registration</p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={() => { void refetchKpi(); }}>
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* ─── LEFT PANEL: Search + Registration ─────────────────────────── */}
        <div className="lg:col-span-3 space-y-4">

          {/* Search bar */}
          <Card>
            <CardContent className="pt-5">
              <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Search Patient
              </Label>
              <div className="relative mt-2">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="Name, MRN, or phone…"
                  value={searchQuery}
                  onChange={e => handleSearchChange(e.target.value)}
                  autoFocus
                />
                {searching && <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />}
              </div>

              {/* Search results */}
              {debouncedQ.length >= 2 && (
                <div className="mt-3 space-y-2 max-h-72 overflow-y-auto pr-1">
                  {patients.length === 0 && !searching && (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No patients found.{" "}
                      <button className="text-primary underline" onClick={() => navigate("/hospital/patients")}>
                        Register new patient →
                      </button>
                    </p>
                  )}
                  {patients.map((p: any) => (
                    <button
                      key={p.id}
                      className={cn(
                        "w-full text-left rounded-lg border px-4 py-3 transition-colors hover:bg-muted/40",
                        selectedPatient?.id === p.id ? "border-primary bg-primary/5" : "border-border"
                      )}
                      onClick={() => handleSelectPatient(p)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <p className="font-medium text-sm">{p.first_name} {p.last_name}</p>
                          <p className="text-xs text-muted-foreground">
                            MRN: {p.mrn} · {ageFromDob(p.date_of_birth)} · {p.gender ?? "—"} · {p.phone ?? "—"}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {p.hmo_provider && (
                            <Badge variant="outline" className="text-xs">{p.hmo_provider}</Badge>
                          )}
                          <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Selected patient + encounter form */}
          {selectedPatient && showForm && (
            <Card className="border-primary/30">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-base flex items-center gap-2">
                      <UserCheck className="h-4 w-4 text-primary" />
                      {selectedPatient.first_name} {selectedPatient.last_name}
                    </CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      MRN: {selectedPatient.mrn} · {ageFromDob(selectedPatient.date_of_birth)} · {selectedPatient.gender ?? "—"}
                    </p>
                    {selectedPatient.hmo_provider && (
                      <Badge variant="outline" className="mt-1 text-xs">{selectedPatient.hmo_provider}</Badge>
                    )}
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => { setSelectedPatient(null); setShowForm(false); }}>
                    Change
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label>Department</Label>
                    <Select value={form.department} onValueChange={v => setForm(f => ({ ...f, department: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {DEPARTMENTS.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label>Encounter Type</Label>
                    <Select value={form.encounter_type} onValueChange={v => setForm(f => ({ ...f, encounter_type: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {ENCOUNTER_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-1">
                  <Label>Priority</Label>
                  <div className="flex gap-2">
                    {PRIORITIES.map(p => (
                      <button
                        key={p.value}
                        onClick={() => setPriority(p.value)}
                        className={cn(
                          "flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                          priority === p.value
                            ? "border-primary bg-primary/10 " + p.color
                            : "border-border text-muted-foreground hover:bg-muted/40"
                        )}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-1">
                  <Label>Chief Complaint</Label>
                  <Textarea
                    rows={2}
                    placeholder="Brief description of patient's main complaint…"
                    value={form.chief_complaint}
                    onChange={e => setForm(f => ({ ...f, chief_complaint: e.target.value }))}
                  />
                </div>

                <Button
                  className="w-full"
                  disabled={openEncounterMut.isPending}
                  onClick={() => openEncounterMut.mutate()}
                >
                  {openEncounterMut.isPending
                    ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Registering…</>
                    : "Register Encounter & Issue Ticket"
                  }
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Ticket issued confirmation */}
          {issuedTicket && (
            <Card className="border-green-500/30 bg-green-500/5">
              <CardContent className="pt-6 text-center space-y-3">
                <div className="flex items-center justify-center gap-2 text-green-400">
                  <Ticket className="h-5 w-5" />
                  <span className="text-sm font-medium">Ticket Issued</span>
                </div>
                <div className="text-5xl font-bold font-mono tracking-widest text-green-400">
                  {issuedTicket.queue_number ?? String(issuedTicket.encounter?.id ?? "—")}
                </div>
                <p className="text-sm text-muted-foreground">
                  {selectedPatient?.first_name} {selectedPatient?.last_name} · {issuedTicket.encounter?.department}
                </p>
                <div className="flex gap-2 pt-2">
                  <Button variant="outline" className="flex-1" onClick={resetAll}>
                    Register Another
                  </Button>
                  <Button variant="outline" className="flex-1" onClick={() => navigate("/hospital/queue")}>
                    View Queue
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* ─── RIGHT PANEL: Live Queue Status ─────────────────────────────── */}
        <div className="lg:col-span-2 space-y-4">
          {/* KPI cards */}
          <div className="grid grid-cols-1 gap-3">
            {[
              { label: "Waiting",         value: kpis.patients_waiting ?? 0,     icon: <Users className="h-4 w-4" />,    color: "text-yellow-400" },
              { label: "In Consultation", value: kpis.active_consultations ?? 0, icon: <Activity className="h-4 w-4" />, color: "text-blue-400"   },
              { label: "Avg Wait (min)",  value: kpis.avg_wait_minutes ?? "—",   icon: <Clock className="h-4 w-4" />,    color: "text-slate-400"  },
            ].map(k => (
              <Card key={k.label}>
                <CardContent className="py-3 px-4">
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

          {/* Department breakdown */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Queue by Department</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {deptQueue.length === 0 ? (
                <p className="text-xs text-muted-foreground py-2">No active patients</p>
              ) : deptQueue.slice(0, 8).map((d: any) => (
                <div key={d.department} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground truncate max-w-[150px]">{d.department}</span>
                  <div className="flex gap-3 text-xs">
                    <span className="text-yellow-400">{d.waiting} waiting</span>
                    <span className="text-blue-400">{d.consulting} consulting</span>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Button variant="outline" className="w-full gap-2" onClick={() => navigate("/hospital/display")}>
            <Activity className="h-4 w-4" /> Open Display Board
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
