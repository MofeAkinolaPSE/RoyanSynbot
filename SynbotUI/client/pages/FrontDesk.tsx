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
import { Loader2, Search, UserCheck, Ticket, Users, Clock, Activity, RefreshCw, ChevronRight, ConciergeBell, Stethoscope, UserPlus } from "lucide-react";
import { api } from "@/lib/api-client";
import { ShowMeHow } from "@/components/tour/ShowMeHow";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { useNavigate, useLocation } from "react-router-dom";
import { ResultsWaitingQueue } from "@/components/frontdesk/ResultsWaitingQueue";
import { CONSULTING_ROOMS } from "@/components/frontdesk/ConsultingRoomBoard";
import { DoctorPicker, RoomBoard, useDoctorsToday } from "@/components/frontdesk/DoctorsToday";
import { PageHeader } from "@/components/workspace/PageHeader";
import { KpiStrip } from "@/components/workspace/KpiStrip";
import { PharmacyApprovalsCard } from "@/components/frontdesk/PharmacyApprovalsCard";

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
  { value: "normal",    label: "Normal", color: "text-green-700 dark:text-green-400" },
  { value: "urgent",    label: "Urgent", color: "text-yellow-700 dark:text-yellow-400" },
  { value: "emergency", label: "Emergency", color: "text-red-700 dark:text-red-400" },
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
  const [issuedTicket, setIssuedTicket]     = useState<{ queue_number?: string; encounter: any; bill?: any } | null>(null);
  // Stage billing: the front desk bills registration (new patients) + the consultation before the doctor.
  const [specialty, setSpecialty]           = useState("auto");
  const [visitKind, setVisitKind]           = useState("auto");
  const [priority, setPriority]             = useState("normal");
  // Payer chosen at registration. Asked for twice: "they need to be able to
  // select whether the patient is private or HMO". Defaulted from the policy on
  // file rather than making the clerk remember, but always overridable — a
  // patient with cover can still elect to pay privately.
  const [payerType, setPayerType]           = useState<"private" | "hmo">("private");
  const [membershipId, setMembershipId]     = useState("");
  // Where the patient is going: the doctor (royan_staff.id) and room, chosen from doctors on seat today.
  const [doctorId, setDoctorId]             = useState("");
  const [room, setRoom]                     = useState("");
  const doctorsQ = useDoctorsToday();
  const approvalsQ = useQuery({
    queryKey: ["pharmacy-pending-approvals"],
    queryFn: () => api.hospital.pharmacy.pendingApprovals(),
    refetchInterval: 30_000,
  });
  const approvalsWaiting: number = approvalsQ.data?.prescriptions?.length ?? 0;
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

  // Proactive lock — checked as soon as a patient is selected, so front-desk
  // staff see the "already on the queue" state before filling out the rest
  // of the form, not just after clicking submit.
  const { data: activeEncCheck } = useQuery({
    queryKey: ["fd-active-encounter-check", selectedPatient?.id],
    queryFn: () => api.hospital.queue.getActiveEncounter(selectedPatient!.id),
    enabled: !!selectedPatient?.id && showForm,
  });
  const activeEncounter = activeEncCheck?.active_encounter;

  // Insurance on file. royan_patient_insurance was empty until the Phase D load
  // and now covers 18,124 patients, so this is the first time the desk can see
  // a membership number without phoning anyone.
  const { data: insuranceData } = useQuery({
    queryKey: ["fd-patient-insurance", selectedPatient?.id],
    queryFn: () => api.hospital.coverage.listPatientInsurance(selectedPatient!.id),
    enabled: !!selectedPatient?.id,
  });
  const policies: any[] = insuranceData?.policies ?? [];
  const primaryPolicy =
    policies.find((x: any) => x.is_primary && x.status === "active") ??
    policies.find((x: any) => x.status === "active") ??
    null;

  // Default the payer to what the record says, once, when the policy arrives.
  useEffect(() => {
    if (!selectedPatient) return;
    if (primaryPolicy) {
      setPayerType("hmo");
      setMembershipId(primaryPolicy.membership_id ?? "");
    } else {
      setPayerType("private");
      setMembershipId("");
    }
  }, [primaryPolicy?.id, selectedPatient?.id]);

  const tariffsQ = useQuery({ queryKey: ["consultation-tariffs"], queryFn: () => api.hospital.billing.consultationTariffs(), staleTime: 300_000 });
  const quoteQ = useQuery({
    queryKey: ["fd-consult-quote", selectedPatient?.id, form.department, doctorId, specialty, visitKind],
    queryFn: () => api.hospital.billing.consultationQuote({
      patient_id: selectedPatient!.id, department: form.department, doctor_id: doctorId || undefined,
      specialty: specialty === "auto" ? undefined : specialty, kind: visitKind === "auto" ? undefined : visitKind,
    }),
    enabled: !!selectedPatient?.id && showForm,
  });
  const quote = quoteQ.data;

  const openEncounterMut = useMutation({
    mutationFn: () =>
      api.hospital.queue.open({
        patient_id: selectedPatient?.id,
        department: form.department,
        encounter_type: form.encounter_type,
        chief_complaint: form.chief_complaint || undefined,
        payer_type: payerType,
        membership_id: payerType === "hmo" ? (membershipId.trim() || undefined) : undefined,
        priority,
        doctor_id: doctorId || undefined,
        consulting_room: room || undefined,
        consultation_specialty: specialty === "auto" ? undefined : specialty,
        visit_kind: visitKind === "auto" ? undefined : visitKind,
      }),
    onSuccess: (data) => {
      const enc = data?.encounter ?? data;
      setShowForm(false);
      void qc.invalidateQueries({ queryKey: ["fd-kpis"] });
      void qc.invalidateQueries({ queryKey: ["fd-dept-queue"] });
      if (data?.already_active) {
        toast({
          title: "Patient already on the queue",
          description: `${enc?.queue_number ?? "Their encounter"} is still active (${String(enc?.status ?? "").replace(/_/g, " ")}) — no new ticket was issued.`,
          variant: "destructive",
        });
        return;
      }
      setIssuedTicket({ queue_number: enc?.queue_number, encounter: enc, bill: data?.bill });
      void qc.invalidateQueries({ queryKey: ["doctors-today"] });
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
    setDoctorId("");
    setRoom("");
    setSpecialty("auto");
    setVisitKind("auto");
  };

  return (
    <motion.div className="flex flex-col gap-6" {...motionTransitions.fadeInUp}>
      <PageHeader icon={ConciergeBell} title="Front Desk"
        subtitle="Find the patient, check them in to the right doctor and room, and answer pharmacy's approval requests"
        actions={<>
          <ShowMeHow only={["find-register-patient"]} />
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => navigate("/hospital/patients", { state: { fromFrontDesk: true } })}><UserPlus className="h-3.5 w-3.5" />New patient</Button>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => navigate("/hospital/display")}><Activity className="h-3.5 w-3.5" />Display board</Button>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => { void refetchKpi(); void doctorsQ.refetch(); void approvalsQ.refetch(); }}><RefreshCw className="h-3.5 w-3.5" />Refresh</Button>
        </>} />

      <KpiStrip items={[
        { label: "Waiting now", value: kpis.patients_waiting ?? 0, icon: Users, sub: "registered or triaged today",
          onClick: () => navigate("/hospital/queue?status=waiting") },
        { label: "With a doctor", value: kpis.active_consultations ?? 0, icon: Activity, sub: "in consultation now",
          onClick: () => navigate("/hospital/queue?status=consulting") },
        { label: "Average wait to triage", value: kpis.avg_wait_minutes ? `${kpis.avg_wait_minutes} min` : "none yet", icon: Clock,
          tone: (kpis.avg_wait_minutes ?? 0) > 60 ? "danger" : (kpis.avg_wait_minutes ?? 0) > 30 ? "warning" : "default", sub: "today" },
        { label: "Doctors on seat", value: doctorsQ.data?.on_seat ?? 0, icon: Stethoscope,
          tone: approvalsWaiting ? "warning" : "default",
          sub: `${approvalsWaiting} pharmacy approval${approvalsWaiting === 1 ? "" : "s"} waiting` },
      ]} />

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
                  data-tour-id="frontdesk-search"
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
                      <button className="text-primary underline" onClick={() => navigate("/hospital/patients", { state: { fromFrontDesk: true } })}>
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
                    {(primaryPolicy || selectedPatient.hmo_provider) && (
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <Badge variant="outline" className="text-xs">
                          {primaryPolicy?.hmo_name ?? selectedPatient.hmo_provider}
                        </Badge>
                        {primaryPolicy?.membership_id && (
                          <span className="font-mono text-xs text-muted-foreground">
                            {primaryPolicy.membership_id}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => { setSelectedPatient(null); setShowForm(false); }}>
                    Change
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {activeEncounter && (
                  <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-600">
                    This patient already has an active encounter — <strong>{activeEncounter.queue_number ?? `#${activeEncounter.id}`}</strong>{" "}
                    ({String(activeEncounter.status).replace(/_/g, " ")}). They must be discharged before a new one can be registered.
                  </div>
                )}
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

                {/* Payer — private or HMO, decided here so the queue row, the
                    bill and the coverage check all agree from the start. */}
                <div className="space-y-1.5">
                  <Label>Payer</Label>
                  <div className="flex gap-2">
                    {(["private", "hmo"] as const).map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setPayerType(t)}
                        className={cn(
                          "flex-1 rounded-md border px-3 py-1.5 text-xs font-medium capitalize transition-colors",
                          payerType === t
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-border text-muted-foreground hover:bg-muted/40",
                        )}
                      >
                        {t === "hmo" ? "HMO / Insurance" : "Private"}
                      </button>
                    ))}
                  </div>

                  {payerType === "hmo" && (
                    <div className="mt-2 space-y-1.5 rounded-md border bg-muted/30 p-2.5">
                      {primaryPolicy ? (
                        <>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-xs">
                              {primaryPolicy.hmo_name ?? "HMO"}
                            </Badge>
                            {primaryPolicy.plan_name && (
                              <span className="text-xs text-muted-foreground">{primaryPolicy.plan_name}</span>
                            )}
                          </div>
                          <Label className="text-xs">Membership number</Label>
                          <Input
                            value={membershipId}
                            onChange={(e) => setMembershipId(e.target.value)}
                            className="h-8 font-mono text-xs"
                          />
                          <p className="text-xs text-muted-foreground">
                            Filled from the patient record. Correct it here if the card differs.
                          </p>
                        </>
                      ) : (
                        <>
                          <Label className="text-xs">Membership number</Label>
                          <Input
                            value={membershipId}
                            onChange={(e) => setMembershipId(e.target.value)}
                            placeholder="Enter from the patient's card"
                            className="h-8 font-mono text-xs"
                          />
                          <p className="text-xs text-amber-600 dark:text-amber-500">
                            No insurance on file for this patient. Anything entered here applies
                            to this visit; add the policy on their chart to keep it.
                          </p>
                        </>
                      )}
                    </div>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label>Doctor <span className="font-normal text-muted-foreground">(optional - their consulting room today comes with them)</span></Label>
                  <div data-tour-id="frontdesk-doctor">
                    <DoctorPicker value={doctorId} onChange={(d) => { setDoctorId(d?.id ?? ""); setRoom(d?.room ?? ""); }} />
                  </div>
                  {doctorId && (
                    <div className="flex items-center gap-2">
                      <Label className="shrink-0 text-xs">Consulting room</Label>
                      <Select value={room || "none"} onValueChange={(v) => setRoom(v === "none" ? "" : v)}>
                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">No room yet</SelectItem>
                          {Array.from(new Set([...(room ? [room] : []), ...CONSULTING_ROOMS])).map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
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

                {/* What the patient pays before seeing the doctor (pre-filled; the specialty / visit type can be changed). */}
                <div className="space-y-2 rounded-md border bg-muted/30 p-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">Consultation</Label>
                      <Select value={specialty} onValueChange={setSpecialty}>
                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">From the doctor / clinic{quote?.consultation?.specialty ? ` (${quote.consultation.specialty})` : ""}</SelectItem>
                          {(tariffsQ.data?.tariffs ?? []).filter((t: any) => t.is_active !== false).map((t: any) => (
                            <SelectItem key={t.id} value={t.specialty}>{t.specialty}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Visit</Label>
                      <Select value={visitKind} onValueChange={setVisitKind}>
                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Automatic{quote?.consultation?.kind ? ` (${String(quote.consultation.kind).replace(/_/g, " ")})` : ""}</SelectItem>
                          <SelectItem value="initial">First visit</SelectItem>
                          <SelectItem value="follow_up">Follow-up</SelectItem>
                          <SelectItem value="review">Review</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  {quoteQ.isLoading ? <p className="text-xs text-muted-foreground">Working out the fee…</p> : quote && (
                    <div className="space-y-0.5 text-xs">
                      {quote.new_patient && quote.registration && (
                        <div className="flex justify-between"><span>{quote.registration.name} (new patient)</span><span>₦{Number(quote.registration.base_price).toLocaleString()}</span></div>
                      )}
                      <div className="flex justify-between"><span>{quote.consultation?.description ?? "Consultation"}</span><span>₦{Number(quote.consultation?.unit_price ?? 0).toLocaleString()}</span></div>
                      <div className="flex justify-between border-t pt-1 text-sm font-semibold"><span>To pay at the cashier</span><span>₦{Number(quote.total ?? 0).toLocaleString()}</span></div>
                      {payerType === "hmo" && <p className="text-muted-foreground">HMO patient: the bill goes to the HMO for what the plan covers.</p>}
                      {quote.consultation?.doctor_fee && <p className="text-muted-foreground">The doctor's own consultation fee.</p>}
                    </div>
                  )}
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
                  data-tour-id="frontdesk-register"
                  className="w-full"
                  disabled={openEncounterMut.isPending || !!activeEncounter}
                  onClick={() => openEncounterMut.mutate()}
                >
                  {openEncounterMut.isPending
                    ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Registering…</>
                    : activeEncounter ? "Already on the queue" : "Register Encounter & Issue Ticket"
                  }
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Ticket issued confirmation */}
          {issuedTicket && (
            <Card className="border-green-500/30 bg-green-500/5">
              <CardContent className="pt-6 text-center space-y-3">
                <div className="flex items-center justify-center gap-2 text-green-700 dark:text-green-400">
                  <Ticket className="h-5 w-5" />
                  <span className="text-sm font-medium">Ticket Issued</span>
                </div>
                <div className="text-5xl font-bold font-mono tracking-widest text-green-700 dark:text-green-400">
                  {issuedTicket.queue_number ?? String(issuedTicket.encounter?.id ?? "—")}
                </div>
                <p className="text-sm text-muted-foreground">
                  {selectedPatient?.first_name} {selectedPatient?.last_name} · {issuedTicket.encounter?.department}{issuedTicket.encounter?.consulting_doctor ? ` · ${issuedTicket.encounter.consulting_doctor}` : ""}{issuedTicket.encounter?.consulting_room ? ` · ${issuedTicket.encounter.consulting_room}` : ""}
                </p>
                {issuedTicket.bill?.bill && (
                  <div className="rounded-md border bg-background px-3 py-2 text-left text-sm">
                    <p className="font-medium">Bill {issuedTicket.bill.bill.bill_number} · ₦{Number(issuedTicket.bill.bill.patient_balance ?? 0).toLocaleString()} to pay</p>
                    <p className="text-xs text-muted-foreground">Send the patient to the cashier before the doctor.</p>
                    <Button size="sm" variant="ghost" className="mt-1 h-7 px-2 text-xs"
                      onClick={() => window.open(`#/hospital/billing/${issuedTicket.bill.bill.id}/invoice`, "_blank")}>Print invoice</Button>
                  </div>
                )}
                {issuedTicket.bill?.error && <p className="text-xs text-amber-600">{issuedTicket.bill.error}</p>}
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
          <div data-tour-id="frontdesk-approvals"><PharmacyApprovalsCard /></div>
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
                    <span className="text-yellow-700 dark:text-yellow-400">{d.waiting} waiting</span>
                    <span className="text-blue-700 dark:text-blue-400">{d.consulting} consulting</span>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <div data-tour-id="frontdesk-rooms"><RoomBoard /></div>

        </div>
      </div>

      {/* Patients waiting only on a result — kept out of the main queue so it
          reflects genuinely-new arrivals. Full width: front desk reads this as
          a worklist, not a sidebar statistic. */}
      <ResultsWaitingQueue onOpenPatient={(enc) => enc.mrn && navigate(`/hospital/patients/${enc.mrn}`)} />
    </motion.div>
  );
}
