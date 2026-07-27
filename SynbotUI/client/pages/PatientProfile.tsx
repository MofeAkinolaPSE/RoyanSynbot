import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft, User, Phone, MapPin, Heart, Droplets, AlertTriangle,
  ShieldCheck, ShieldOff, Clock, Stethoscope, FlaskConical, Pill,
  Receipt, Activity, Plus, CalendarPlus, MessageSquare, UserCheck,
  ChevronRight, FileText, Loader2, ListChecks, ShieldAlert, CheckCircle2,
  XCircle, PenLine, Thermometer, TrendingUp, ClipboardCheck, Upload, Send,
  Scissors, ScanLine, Eye, NotebookPen, Megaphone, CalendarClock, Bell, Syringe, Baby,
} from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { CoverageQuote } from "@/components/CoverageQuote";
import { AlertBanner } from "@/components/AlertBanner";
import { AllergyBanner } from "@/components/AllergyBanner";
import { CoverSheetWidget } from "@/components/patient/CoverSheetWidget";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Patient {
  id: string | number;
  mrn: string;
  first_name: string;
  last_name: string;
  date_of_birth?: string;
  gender?: string;
  phone?: string;
  email?: string;
  address?: string;
  blood_group?: string;
  genotype?: string;
  allergies?: string[];
  next_of_kin_name?: string;
  next_of_kin_phone?: string;
  hmo_provider?: string;
  hmo_id?: string;
  registered_at?: string;
  is_active?: boolean;
}

interface Insurance {
  active: boolean;
  hmo_name?: string;
  plan_name?: string;
  membership_id?: string;
  legacy_only?: boolean;
}

interface TimelineItem {
  type: "encounter" | "lab_order" | "prescription" | "bill";
  timestamp: string;
  record: Record<string, any>;
}

interface ProfileData {
  patient: Patient & { insurance?: Insurance; current_encounter?: any };
  insurance?: Insurance;
  active_encounter?: Record<string, any>;
  last_encounter?: Record<string, any>;
  encounters: any[];
  lab_orders: any[];
  prescriptions: any[];
  bills: any[];
  appointments: any[];
  postings: any[];
  immunisations: any[];
  timeline: TimelineItem[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function calcAge(dob?: string): string {
  if (!dob) return "—";
  const years = new Date().getFullYear() - new Date(dob).getFullYear();
  return `${years} yrs`;
}

// Hope's historical dump never captured the actual drug/test name for
// pharmacy or lab records (its "pharmacy" export turned out to be billing
// invoice data with no medication fields at all, and lab orders only carry
// an internal catalog ID) — the ETL writes these exact sentinel strings when
// the source has nothing to map. Render them as an honest "no detail
// captured" state instead of fake-looking clinical content a clinician could
// mistake for real dosing/test information.
const HOPE_PLACEHOLDER_NAMES = new Set(["Imported prescription", "Imported lab order"]);
function isPlaceholderRecord(name: string | undefined, source: string | undefined): boolean {
  return source === "hope" && !!name && HOPE_PLACEHOLDER_NAMES.has(name);
}

// Same root cause, a different shape: Hope's dump resolves "who" (a doctor,
// orderer, prescriber) to either a bare internal numeric ID (appointment
// slots' doctor_name, most of lab_orders.ordered_by) or a generic ETL-bot
// sentinel ("hope_ingest", all of prescriptions.prescribed_by — the source
// never captured a real prescriber at all). Showing either as if it were a
// real name is misleading; label them honestly until the reference/catalog
// tables get re-extracted from Hope to resolve the IDs to real names.
function isRawIdAttribution(value: string | undefined | null): boolean {
  return !!value && /^\d+$/.test(value.trim());
}
function formatAttribution(value: string | undefined | null): string | null {
  if (!value) return null;
  if (value === "hope_ingest") return "Not recorded by source system";
  if (isRawIdAttribution(value)) return `Staff ID ${value} (name not yet resolved)`;
  return value;
}

function fmtDate(ts?: string): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
}

function fmtDateTime(ts?: string): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function waitMins(ts?: string): string {
  if (!ts) return "";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m ago`;
}


// ─── Sub-components ───────────────────────────────────────────────────────────

function InfoRow({ label, value, icon: Icon }: { label: string; value?: string | null; icon?: React.ElementType }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      {Icon && <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="truncate font-medium">{value || "—"}</p>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PatientProfile() {
  const { mrn } = useParams<{ mrn: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();

  const [encounterOpen, setEncounterOpen] = useState(false);
  const [labOpen, setLabOpen] = useState(false);
  const [rxOpen, setRxOpen] = useState(false);
  const [duplicateRxAlert, setDuplicateRxAlert] = useState<{ existing: any[]; message: string } | null>(null);
  const [mainTab, setMainTab] = useState<"timeline" | "problems" | "meds" | "orders" | "notes" | "labs" | "surgery" | "consent" | "specialist">("timeline");
  const [vitalsDialogOpen, setVitalsDialogOpen] = useState(false);
  // Generic "view full record" popup shared by every Cover Sheet card —
  // each card builds its own [label, value] rows at click time so this one
  // dialog covers appointments/visits, meds, labs, reminders, and
  // immunizations without repeating the same dialog shell 5 times.
  const [recordDetail, setRecordDetail] = useState<{ title: string; subtitle?: string; rows: [string, any][] } | null>(null);
  const [postingOpen, setPostingOpen] = useState(false);
  const [postingForm, setPostingForm] = useState({ posting_type: "alert", message: "", severity: "info" });
  const [immunisationOpen, setImmunisationOpen] = useState(false);
  const [immunisationForm, setImmunisationForm] = useState({ vaccine_name: "", dose_number: "", site: "" });
  const [allergyOpen, setAllergyOpen] = useState(false);
  const [allergyForm, setAllergyForm] = useState({ allergen: "", severity: "moderate", reaction: "" });
  const [editPatientOpen, setEditPatientOpen] = useState(false);
  const [editPatientForm, setEditPatientForm] = useState({
    phone: "", address: "", next_of_kin_name: "", next_of_kin_phone: "",
    blood_group: "", genotype: "", allergies: "",
  });
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteForm, setNoteForm] = useState({ note_type: "soap", subjective: "", objective: "", assessment: "", plan: "" });
  const [problemOpen, setProblemOpen] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const [problemForm, setProblemForm] = useState({ description: "", icd10_code: "", status: "active", onset_date: "" });
  const [icd10Search, setIcd10Search] = useState("");
  const [consentForm, setConsentForm] = useState({ consent_type: "general_treatment", consented: true, notes: "", witness_name: "" });
  const [encounterForm, setEncounterForm] = useState({
    encounter_type: "outpatient", department: "OPD", chief_complaint: "",
  });
  const [labForm, setLabForm] = useState({
    test_name: "", urgency: "routine", notes: "",
  });
  const [rxForm, setRxForm] = useState({
    drug_name: "", frequency: "twice daily", dosage: "", duration: "5 days", route: "oral",
  });

  const [followUpOpen, setFollowUpOpen] = useState(false);
  const [followUpForm, setFollowUpForm] = useState({
    slot_date: new Date().toISOString().split("T")[0],
    slot_id: "",
    appointment_type: "follow_up",
    notes: "",
  });

  const [docUploadOpen, setDocUploadOpen]   = useState(false);
  const [referralOpen, setReferralOpen]     = useState(false);
  const [uploadedFile, setUploadedFile]     = useState<File | null>(null);
  const [referralForm, setReferralForm]     = useState({
    referring_to: "", reason: "", urgency: "routine", additional_notes: "", referring_doctor: "",
  });
  const [generatedLetter, setGeneratedLetter] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery<ProfileData>({
    queryKey: ["patient-profile", mrn],
    queryFn: () => api.hospital.patients.profile(mrn!),
    enabled: !!mrn,
    // Override the global 3-minute staleTime/refetchOnMount:false defaults (App.tsx)
    // for this page specifically — active_encounter drives which action buttons are
    // enabled, and a stale snapshot here made freshly-created encounters invisible,
    // pushing users toward opening duplicate encounters.
    staleTime: 0,
    refetchOnMount: "always",
  });

  const patient = data?.patient;
  const insurance = data?.insurance ?? patient?.insurance;
  const timeline = data?.timeline ?? [];

  // Open encounter mutation
  const openEncMut = useMutation({
    mutationFn: () => api.hospital.queue.open({
      patient_id: patient?.mrn ?? patient?.id,
      ...encounterForm,
    }),
    onSuccess: (res: any) => {
      if (res?.already_active) {
        toast({
          title: "Encounter already open",
          description: `${patient?.first_name} already has an active encounter${res.encounter?.queue_number ? ` (${res.encounter.queue_number})` : ""} — using that one instead of opening a duplicate.`,
        });
      } else {
        toast({ title: "Encounter opened", description: `${patient?.first_name} added to the clinical queue.` });
      }
      setEncounterOpen(false);
      setEncounterForm({ encounter_type: "outpatient", department: "OPD", chief_complaint: "" });
      void qc.invalidateQueries({ queryKey: ["patient-profile", mrn] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // Lab order mutation
  const labMut = useMutation({
    mutationFn: () => api.hospital.lab.placeOrder({
      patient_id: Number(patient?.id),
      encounter_id: data?.active_encounter?.id,
      ...labForm,
    }),
    onSuccess: () => {
      toast({ title: "Lab order placed" });
      setLabOpen(false);
      setLabForm({ test_name: "", urgency: "routine", notes: "" });
      void qc.invalidateQueries({ queryKey: ["patient-profile", mrn] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // Prescription mutation
  const rxMut = useMutation({
    mutationFn: (overrideDuplicate = false) => api.hospital.pharmacy.createRx({
      patient_id: Number(patient?.id),
      encounter_id: Number(data?.active_encounter?.id),
      ...rxForm,
      ...(overrideDuplicate ? { override_duplicate: true } : {}),
    }),
    onSuccess: (res: any) => {
      if (res?.ok === false && res.duplicate_alert) {
        setDuplicateRxAlert({ existing: res.existing_prescriptions ?? [], message: res.message ?? "" });
        return;
      }
      toast({ title: "Prescription written" });
      setRxOpen(false);
      setDuplicateRxAlert(null);
      setRxForm({ drug_name: "", frequency: "twice daily", dosage: "", duration: "5 days", route: "oral" });
      void qc.invalidateQueries({ queryKey: ["patient-profile", mrn] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // Discharge mutation
  const [dischargeOpen, setDischargeOpen] = useState(false);
  const [dischargeForm, setDischargeForm] = useState({ disposition: "home", discharge_summary: "" });
  const dischargeMut = useMutation({
    mutationFn: () => api.hospital.queue.discharge(
      String(data?.active_encounter?.id),
      dischargeForm,
    ),
    onSuccess: () => {
      toast({ title: "Patient discharged" });
      setDischargeOpen(false);
      setDischargeForm({ disposition: "home", discharge_summary: "" });
      void qc.invalidateQueries({ queryKey: ["patient-profile", mrn] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // Available slots for the in-CPRS Schedule Follow-up picker
  const { data: followUpSlotsData, isLoading: followUpSlotsLoading } = useQuery({
    queryKey: ["appointment-slots", "follow-up", followUpForm.slot_date],
    queryFn: () => api.hospital.appointments.listSlots({ date: followUpForm.slot_date }),
    enabled: followUpOpen,
    staleTime: 15_000,
  });
  const followUpSlots: any[] = Array.isArray(followUpSlotsData?.slots) ? followUpSlotsData.slots : Array.isArray(followUpSlotsData) ? followUpSlotsData : [];

  const followUpMut = useMutation({
    mutationFn: () => api.hospital.appointments.book({
      patient_id: patient?.mrn ?? patient?.id,
      slot_id: followUpForm.slot_id,
      appointment_type: followUpForm.appointment_type,
      notes: followUpForm.notes,
    }),
    onSuccess: () => {
      toast({ title: "Follow-up scheduled" });
      setFollowUpOpen(false);
      setFollowUpForm({ slot_date: new Date().toISOString().split("T")[0], slot_id: "", appointment_type: "follow_up", notes: "" });
      void qc.invalidateQueries({ queryKey: ["appointments"] });
      void qc.invalidateQueries({ queryKey: ["appointments-calendar"] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // Document upload mutation
  const docUploadMut = useMutation({
    mutationFn: async () => {
      if (!uploadedFile) throw new Error("No file selected");
      // Create document record first, then upload file
      const docRes = await api.medicalRecords.createDocument({
        title: uploadedFile.name,
        document_type: "patient_file",
        patient_id: patient?.id,
        encounter_id: data?.active_encounter?.id ?? null,
        tags: ["patient_upload"],
      });
      const docId = docRes?.document?.id ?? docRes?.id;
      if (!docId) throw new Error("Document creation failed");
      return api.medicalRecords.uploadFile(String(docId), uploadedFile);
    },
    onSuccess: () => {
      toast({ title: "Document uploaded" });
      setDocUploadOpen(false);
      setUploadedFile(null);
    },
    onError: (e: any) => toast({ title: "Upload failed", description: e.message, variant: "destructive" }),
  });

  // Referral letter mutation
  const referralMut = useMutation({
    mutationFn: () => api.medicalRecords.generateReferral(
      String(data?.active_encounter?.id),
      referralForm,
    ),
    onSuccess: (res: any) => {
      toast({ title: "Referral letter generated" });
      setGeneratedLetter(res?.letter ?? null);
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Problem List queries + mutations ─────────────────────────────────────────
  const patientNumId = patient ? Number(patient.id) : undefined;

  const { data: problemsData, refetch: refetchProblems } = useQuery({
    queryKey: ["patient-problems", patientNumId],
    queryFn: () => api.hospital.clinical.listProblems(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const problems: any[] = Array.isArray(problemsData?.problems) ? problemsData.problems : [];

  const { data: icd10Data } = useQuery({
    queryKey: ["icd10-search", icd10Search],
    queryFn: () => api.hospital.clinical.searchIcd10(icd10Search),
    enabled: icd10Search.length >= 2,
    staleTime: 300_000,
  });
  const icd10Results: any[] = Array.isArray(icd10Data?.codes) ? icd10Data.codes : [];

  const addProblemMut = useMutation({
    mutationFn: () => api.hospital.clinical.addProblem(patientNumId!, {
      ...problemForm,
      // icd10_code only gets set when a search suggestion is clicked (see the
      // dropdown onClick below) — if the user typed a code but never clicked a
      // match, fall back to whatever they typed instead of silently dropping it.
      icd10_code: problemForm.icd10_code || icd10Search.trim(),
    }),
    onSuccess: () => {
      toast({ title: "Problem added" });
      setProblemOpen(false);
      setProblemForm({ description: "", icd10_code: "", status: "active", onset_date: "" });
      setIcd10Search("");
      void refetchProblems();
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  const resolveProblemMut = useMutation({
    mutationFn: (problemId: number) => api.hospital.clinical.updateProblem(problemId, { status: "resolved" }),
    onSuccess: () => { toast({ title: "Problem resolved" }); void refetchProblems(); },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Consent queries + mutations ───────────────────────────────────────────────
  const { data: consentData, refetch: refetchConsents } = useQuery({
    queryKey: ["patient-consents", patientNumId],
    queryFn: () => api.hospital.consent.list(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const consents: any[] = Array.isArray(consentData?.consents) ? consentData.consents : [];

  const addConsentMut = useMutation({
    mutationFn: () => api.hospital.consent.add(patientNumId!, {
      ...consentForm,
      encounter_id: data?.active_encounter?.id ?? null,
    }),
    onSuccess: () => {
      toast({ title: "Consent recorded" });
      setConsentOpen(false);
      setConsentForm({ consent_type: "general_treatment", consented: true, notes: "", witness_name: "" });
      void refetchConsents();
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Vitals query ─────────────────────────────────────────────────────────────
  const { data: vitalsData } = useQuery({
    queryKey: ["patient-vitals", patientNumId],
    queryFn: () => api.hospital.nursing.listVitals(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const vitals: any[] = Array.isArray(vitalsData?.vitals) ? vitalsData.vitals : [];
  const lastVitals = vitals[0] ?? null;

  // ── Specialist notes query ────────────────────────────────────────────────────
  const { data: specialistData } = useQuery({
    queryKey: ["patient-specialist-notes", patientNumId],
    queryFn: () => api.specialist.listNotes({ patient_id: patientNumId }),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const specialistNotes: any[] = Array.isArray(specialistData?.notes) ? specialistData.notes : [];

  // ── Radiology orders ─────────────────────────────────────────────────────────
  const { data: radData } = useQuery({
    queryKey: ["patient-radiology", patientNumId],
    queryFn: () => api.hospital.radiology.listOrders({ patient_id: patientNumId }),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const radOrders: any[] = Array.isArray(radData?.orders) ? radData.orders : [];

  // ── Theatre cases ─────────────────────────────────────────────────────────────
  const { data: theatreData } = useQuery({
    queryKey: ["patient-theatre", patientNumId],
    queryFn: () => api.hospital.theatre.listCases({ patient_id: patientNumId }),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const theatreCases: any[] = Array.isArray(theatreData?.cases) ? theatreData.cases : [];

  // ── Lab reference ranges ──────────────────────────────────────────────────────
  const { data: refRangesData } = useQuery({
    queryKey: ["lab-ref-ranges"],
    queryFn: () => api.hospital.lab.listReferenceRanges(),
    staleTime: 300_000,
  });
  const refRanges: any[] = Array.isArray(refRangesData?.ranges) ? refRangesData.ranges : [];

  // ── Encounter notes (batch fetch — lazy, only on Notes tab) ──────────────────
  const encounters: any[] = Array.isArray(data?.encounters) ? data.encounters : [];
  const { data: notesData } = useQuery({
    queryKey: ["patient-enc-notes", patientNumId],
    queryFn: async () => {
      const encIds = encounters.slice(0, 10).map((e: any) => String(e.id));
      const results = await Promise.allSettled(
        encIds.map(id => api.hospital.queue.listNotes(id))
      );
      return results
        .filter(r => r.status === "fulfilled")
        .flatMap((r: any) => r.value?.notes ?? [])
        .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    },
    enabled: !!patientNumId && mainTab === "notes" && encounters.length > 0,
    staleTime: 60_000,
  });
  const encNotes: any[] = Array.isArray(notesData) ? notesData : [];

  // ── Roles (for notes write access) ───────────────────────────────────────────
  const { roles } = useAuth();
  const isDoctor = roles.some(r => ["doctor", "admin"].includes(r));

  // ── Computed CPRS summary values ──────────────────────────────────────────────
  const activeMeds = useMemo(() =>
    (data?.prescriptions ?? []).filter((rx: any) => ["pending", "partially_dispensed"].includes(rx.status)),
    [data?.prescriptions]
  );
  const pendingOrders = useMemo(() =>
    (data?.lab_orders ?? []).filter((o: any) => ["ordered", "sample_collected", "processing"].includes(o.status)),
    [data?.lab_orders]
  );
  const resultedLabs = useMemo(() =>
    (data?.lab_orders ?? []).filter((o: any) => o.result_summary),
    [data?.lab_orders]
  );

  // ── Postings (CPRS cover-sheet clinical flags/notices) ───────────────────────
  const { data: postingsData, refetch: refetchPostings } = useQuery({
    queryKey: ["patient-postings", patientNumId],
    queryFn: () => api.hospital.clinical.listPostings(patientNumId!, true),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const postings: any[] = Array.isArray(postingsData?.postings) ? postingsData.postings : [];

  const addPostingMut = useMutation({
    mutationFn: () => api.hospital.clinical.addPosting(patientNumId!, postingForm),
    onSuccess: () => {
      toast({ title: "Posting added" });
      setPostingOpen(false);
      setPostingForm({ posting_type: "alert", message: "", severity: "info" });
      void refetchPostings();
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  const resolvePostingMut = useMutation({
    mutationFn: (postingId: number) => api.hospital.clinical.resolvePosting(postingId),
    onSuccess: () => { toast({ title: "Posting resolved" }); void refetchPostings(); },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Clinical Reminders ────────────────────────────────────────────────────────
  const { data: remindersData, refetch: refetchReminders } = useQuery({
    queryKey: ["patient-reminders", patientNumId],
    queryFn: () => api.hospital.clinical.listReminders(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const reminders: any[] = Array.isArray(remindersData?.reminders) ? remindersData.reminders : [];

  const dismissReminderMut = useMutation({
    mutationFn: (reminderId: number) => api.hospital.clinical.dismissReminder(reminderId),
    onSuccess: () => { toast({ title: "Reminder dismissed" }); void refetchReminders(); },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Immunisations ──────────────────────────────────────────────────────────────
  const { data: immunisationsData, refetch: refetchImmunisations } = useQuery({
    queryKey: ["patient-immunisations", patientNumId],
    queryFn: () => api.hospital.mch.getImmunisationHistory(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const immunisations: any[] = Array.isArray(immunisationsData?.immunisations) ? immunisationsData.immunisations : [];

  const addImmunisationMut = useMutation({
    mutationFn: () => api.hospital.mch.logImmunisation(patientNumId!, {
      ...immunisationForm,
      dose_number: immunisationForm.dose_number ? Number(immunisationForm.dose_number) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Immunisation recorded" });
      setImmunisationOpen(false);
      setImmunisationForm({ vaccine_name: "", dose_number: "", site: "" });
      void refetchImmunisations();
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Structured allergies (severity/reaction detail) ───────────────────────────
  const { data: allergiesData, refetch: refetchAllergies } = useQuery({
    queryKey: ["patient-allergies-structured", patientNumId],
    queryFn: () => api.hospital.pharmacy.listAllergies(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const structuredAllergies: any[] = Array.isArray(allergiesData?.allergies) ? allergiesData.allergies : [];

  // ── Babies (mother-baby linkage) ───────────────────────────────────────────
  const { data: babiesData } = useQuery({
    queryKey: ["patient-babies", patientNumId],
    queryFn: () => api.hospital.mch.listBabies(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 60_000,
  });
  const babies: any[] = Array.isArray(babiesData?.babies) ? babiesData.babies : [];

  const addAllergyMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.addAllergy(patientNumId!, allergyForm),
    onSuccess: () => {
      toast({ title: "Allergy recorded" });
      setAllergyOpen(false);
      setAllergyForm({ allergen: "", severity: "moderate", reaction: "" });
      void refetchAllergies();
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Edit Patient Information (backfill missing demographics) ─────────────────
  const openEditPatient = () => {
    setEditPatientForm({
      phone: patient.phone ?? "",
      address: patient.address ?? "",
      next_of_kin_name: patient.next_of_kin_name ?? "",
      next_of_kin_phone: patient.next_of_kin_phone ?? "",
      blood_group: patient.blood_group ?? "",
      genotype: patient.genotype ?? "",
      allergies: (patient.allergies ?? []).join(", "),
    });
    setEditPatientOpen(true);
  };

  const editPatientMut = useMutation({
    mutationFn: () => api.hospital.patients.update(mrn!, {
      // The form always shows every field's current value (openEditPatient
      // pre-fills from the patient record), so this save is authoritative
      // for all of them: a blank field means "clear this," sent as an
      // explicit null (not "" — royan_patients.blood_group/genotype have DB
      // CHECK constraints that reject an empty string but allow NULL; see
      // update_patient()'s exclude_unset handling on the backend).
      phone: editPatientForm.phone || null,
      address: editPatientForm.address || null,
      next_of_kin_name: editPatientForm.next_of_kin_name || null,
      next_of_kin_phone: editPatientForm.next_of_kin_phone || null,
      blood_group: editPatientForm.blood_group || null,
      genotype: editPatientForm.genotype || null,
      allergies: editPatientForm.allergies
        ? editPatientForm.allergies.split(",").map(s => s.trim()).filter(Boolean)
        : null,
    }),
    onSuccess: () => {
      toast({ title: "Patient information updated" });
      setEditPatientOpen(false);
      void qc.invalidateQueries({ queryKey: ["patient-profile", mrn] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Appointments/Visits (real bookings + native encounters, merged) ───────────
  const appointmentsAndVisits = useMemo(() => {
    const appts = (data?.appointments ?? []).map((a: any) => {
      // Doctor names on Hope-imported appointment slots are always a raw
      // internal ID (see formatAttribution) — not informative at a glance,
      // so leave them out of the compact label; the detail dialog shows
      // them honestly labeled instead.
      const doctorForLabel = a.doctor_name && !isRawIdAttribution(a.doctor_name) ? a.doctor_name : null;
      return {
        kind: "appointment" as const,
        date: a.slot_date ? `${a.slot_date}T${a.slot_time ?? "00:00"}` : a.booked_at,
        label: a.department ? `${a.department}${doctorForLabel ? " · " + doctorForLabel : ""}` : (doctorForLabel ?? "Appointment"),
        status: a.ui_status ?? a.status,
        record: a,
      };
    });
    const visits = (data?.encounters ?? []).map((e: any) => ({
      kind: "visit" as const,
      date: e.created_at,
      label: e.department ? `${e.department} · ${(e.encounter_type ?? "").replace(/_/g, " ")}` : (e.encounter_type ?? "Visit"),
      status: e.status,
      record: e,
    }));
    return [...appts, ...visits].sort((a, b) => new Date(b.date || 0).getTime() - new Date(a.date || 0).getTime());
  }, [data?.appointments, data?.encounters]);

  // ── Note write mutation ──────────────────────────────────────────────────────
  const noteMut = useMutation({
    mutationFn: () => {
      if (!data?.active_encounter?.id) throw new Error("No active encounter — open one first");
      return api.hospital.queue.addNote(String(data.active_encounter.id), {
        note_type: noteForm.note_type,
        content: JSON.stringify({
          subjective: noteForm.subjective,
          objective: noteForm.objective,
          assessment: noteForm.assessment,
          plan: noteForm.plan,
        }),
      });
    },
    onSuccess: () => {
      toast({ title: "Progress note saved" });
      setNoteOpen(false);
      setNoteForm({ note_type: "soap", subjective: "", objective: "", assessment: "", plan: "" });
      void qc.invalidateQueries({ queryKey: ["patient-enc-notes", patientNumId] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Loading ──────────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex h-full gap-4 p-1">
        <div className="w-64 shrink-0 space-y-4">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-32 w-full rounded-xl" />
        </div>
        <div className="flex-1 space-y-3">
          <Skeleton className="h-6 w-40" />
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
        </div>
        <div className="w-48 shrink-0 space-y-3">
          <Skeleton className="h-8 w-full rounded-lg" />
          <Skeleton className="h-8 w-full rounded-lg" />
          <Skeleton className="h-8 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  if (isError || !patient) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center text-sm text-muted-foreground">
        <AlertTriangle className="h-8 w-8 text-destructive opacity-60" />
        <p>Patient not found or failed to load.</p>
        <Button variant="outline" size="sm" onClick={() => navigate("/hospital/patients")}>
          Back to Patients
        </Button>
      </div>
    );
  }

  const fullName = `${patient.first_name} ${patient.last_name}`;
  const hasActiveEnc = !!data?.active_encounter;
  const insuranceActive = insurance?.active ?? false;

  return (
    <motion.div className="flex h-full min-h-0 flex-col gap-0" {...motionTransitions.fadeInUp}>
      <AlertBanner className="mb-2" />
      <AllergyBanner allergies={patient.allergies} className="mb-2" />
      {/* Page header */}
      <div className="mb-4 flex items-center gap-3">
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => navigate("/hospital/patients")}>
          <ArrowLeft className="h-4 w-4" /> Patients
        </Button>
        <ChevronRight className="h-4 w-4 text-muted-foreground" />
        <span className="font-semibold">{fullName}</span>
        <Badge variant="outline" className="font-mono text-xs">{patient.mrn}</Badge>
        {!patient.is_active && (
          <Badge variant="outline" className="bg-destructive/10 text-destructive text-xs">Inactive</Badge>
        )}
      </div>

      {/* 3-panel layout */}
      <div className="flex min-h-0 flex-1 gap-4 overflow-hidden">

        {/* ── LEFT: Sticky Patient Summary ──────────────────────────────── */}
        <aside className="flex w-64 shrink-0 flex-col gap-3 overflow-y-auto">

          {/* Avatar + name */}
          <Card>
            <CardContent className="pt-5">
              <div className="flex flex-col items-center gap-2 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary/30 to-primary/10 text-lg font-bold">
                  {patient.first_name[0]}{patient.last_name[0]}
                </div>
                <div>
                  <p className="font-semibold leading-tight">{fullName}</p>
                  <p className="text-xs text-muted-foreground">
                    {calcAge(patient.date_of_birth)} · {patient.gender ?? "—"}
                  </p>
                </div>
                {/* HMO status */}
                <div className={cn(
                  "flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs font-medium",
                  insuranceActive
                    ? "border-green-500/30 bg-green-500/10 text-green-400"
                    : "border-slate-500/30 bg-slate-500/10 text-slate-400",
                )}>
                  {insuranceActive ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldOff className="h-3.5 w-3.5" />}
                  {insurance?.hmo_name ?? patient.hmo_provider ?? (insuranceActive ? "HMO Active" : "No HMO")}
                </div>
                {insurance?.plan_name && (
                  <p className="text-[11px] text-muted-foreground">{insurance.plan_name}</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Clinical Info */}
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Clinical</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 px-4 pb-4">
              <InfoRow label="Blood Group" value={patient.blood_group} icon={Droplets} />
              <InfoRow label="Genotype" value={patient.genotype} icon={Activity} />
              {patient.allergies && patient.allergies.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Allergies</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {patient.allergies.map((a) => (
                      <Badge key={a} variant="outline" className="text-[10px] bg-destructive/10 text-destructive border-destructive/30">
                        {a}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {/* Active problems mini-list */}
              {problems.filter(p => p.status === "active").length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Active Problems</p>
                  <div className="mt-1 space-y-1">
                    {problems.filter(p => p.status === "active").slice(0, 4).map((p: any) => (
                      <div key={p.id} className="flex items-start gap-1.5">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-blue-400 shrink-0" />
                        <span className="text-xs leading-tight">
                          {p.icd10_code && <span className="font-mono text-muted-foreground mr-1">{p.icd10_code}</span>}
                          {p.description}
                        </span>
                      </div>
                    ))}
                    {problems.filter(p => p.status === "active").length > 4 && (
                      <button
                        className="text-[10px] text-primary underline underline-offset-2"
                        onClick={() => setMainTab("problems")}
                      >
                        +{problems.filter(p => p.status === "active").length - 4} more
                      </button>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Contact */}
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Contact</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 px-4 pb-4">
              <InfoRow label="Phone" value={patient.phone} icon={Phone} />
              <InfoRow label="Address" value={patient.address} icon={MapPin} />
              <InfoRow label="Next of Kin" value={patient.next_of_kin_name} icon={User} />
              <InfoRow label="NOK Phone" value={patient.next_of_kin_phone} icon={Phone} />
            </CardContent>
          </Card>

          {/* Registration */}
          <Card>
            <CardContent className="pt-4 px-4 pb-4 text-xs text-muted-foreground">
              <p>Registered: {fmtDate(patient.registered_at)}</p>
              {insurance?.membership_id && (
                <p className="mt-1">HMO ID: <span className="font-mono">{insurance.membership_id}</span></p>
              )}
            </CardContent>
          </Card>

          {/* Last Vitals */}
          {lastVitals && (
            <Card>
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Thermometer className="h-3 w-3" /> Last Vitals
                  <span className="ml-auto font-normal normal-case text-[10px]">{fmtDate(lastVitals.recorded_at)}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                {lastVitals.bp_systolic && (
                  <div><p className="text-muted-foreground text-[10px]">BP</p><p className="font-medium">{lastVitals.bp_systolic}/{lastVitals.bp_diastolic}</p></div>
                )}
                {lastVitals.pulse && (
                  <div><p className="text-muted-foreground text-[10px]">Pulse</p><p className="font-medium">{lastVitals.pulse} bpm</p></div>
                )}
                {lastVitals.temperature && (
                  <div><p className="text-muted-foreground text-[10px]">Temp</p><p className="font-medium">{lastVitals.temperature}°C</p></div>
                )}
                {lastVitals.spo2 && (
                  <div><p className="text-muted-foreground text-[10px]">SpO2</p><p className="font-medium">{lastVitals.spo2}%</p></div>
                )}
                {lastVitals.weight && (
                  <div><p className="text-muted-foreground text-[10px]">Weight</p><p className="font-medium">{lastVitals.weight} kg</p></div>
                )}
                {lastVitals.pain_score != null && (
                  <div><p className="text-muted-foreground text-[10px]">Pain</p><p className="font-medium">{lastVitals.pain_score}/10</p></div>
                )}
              </CardContent>
            </Card>
          )}
        </aside>

        {/* ── CENTER: Main Panel ─────────────────────────────────────────── */}
        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
          {/* Active encounter banner */}
          {hasActiveEnc && (
            <div className="mb-4 flex items-center gap-3 rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-2.5 text-sm text-blue-400">
              <Activity className="h-4 w-4 shrink-0 animate-pulse" />
              <span>
                Active encounter — <strong className="capitalize">
                  {(data.active_encounter!.status ?? "").replace(/_/g, " ")}
                </strong>
                {data.active_encounter!.department && ` · ${data.active_encounter.department}`}
              </span>
            </div>
          )}

          {/* No active encounter — show the most recent past visit instead */}
          {!hasActiveEnc && data?.last_encounter && (
            <div className="mb-4 flex items-center gap-3 rounded-xl border border-border bg-muted/30 px-4 py-2.5 text-sm text-muted-foreground">
              <Clock className="h-4 w-4 shrink-0" />
              <span>
                No active encounter — last visit <strong className="capitalize text-foreground">
                  {(data.last_encounter.status ?? "").replace(/_/g, " ")}
                </strong>
                {data.last_encounter.department && ` · ${data.last_encounter.department}`}
                {data.last_encounter.created_at && ` · ${fmtDate(data.last_encounter.created_at)}`}
              </span>
            </div>
          )}

          <div className="mb-3">
            {/* Tab navigation — horizontal scroll for 9 CPRS tabs */}
            <div className="overflow-x-auto whitespace-nowrap rounded-lg border p-0.5 text-xs scrollbar-none">
              <div className="inline-flex gap-0.5">
                {[
                  { key: "timeline",   label: "Cover Sheet", icon: Activity },
                  { key: "problems",   label: `Problems (${problems.length})`, icon: ListChecks },
                  { key: "meds",       label: `Meds (${activeMeds.length})`, icon: Pill },
                  { key: "orders",     label: `Orders (${pendingOrders.length})`, icon: FlaskConical },
                  { key: "notes",      label: "Notes", icon: NotebookPen },
                  { key: "labs",       label: "Labs", icon: TrendingUp },
                  { key: "surgery",    label: `Surgery (${theatreCases.length})`, icon: Scissors },
                  { key: "consent",    label: `Consent (${consents.length})`, icon: ShieldAlert },
                  { key: "specialist", label: `Specialist (${specialistNotes.length})`, icon: ClipboardCheck },
                ].map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    onClick={() => setMainTab(key as typeof mainTab)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 transition-colors shrink-0",
                      mainTab === key
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted",
                    )}
                  >
                    <Icon className="h-3 w-3" />{label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* ── Tab: Cover Sheet ── */}
          {mainTab === "timeline" && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {/* Active Problems */}
              <CoverSheetWidget
                title="Active Problems" icon={ListChecks}
                count={problems.filter((p: any) => p.status === "active").length}
                isEmpty={problems.filter((p: any) => p.status === "active").length === 0}
                emptyLabel="No active problems"
                onAdd={() => setProblemOpen(true)} addLabel="Add problem"
                onViewAll={() => setMainTab("problems")}
              >
                <div className="space-y-1.5">
                  {problems.filter((p: any) => p.status === "active").slice(0, 6).map((p: any) => (
                    <div key={p.id} className="flex items-start justify-between gap-2 text-xs">
                      <span className="min-w-0 truncate">{p.description}</span>
                      {p.icd10_code && <span className="shrink-0 font-mono text-muted-foreground">{p.icd10_code}</span>}
                    </div>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Allergies */}
              <CoverSheetWidget
                title="Allergies / Adverse Reactions" icon={AlertTriangle}
                count={structuredAllergies.length || patient.allergies?.length || 0}
                isEmpty={structuredAllergies.length === 0 && !patient.allergies?.length}
                emptyLabel="No known allergies"
                onAdd={() => setAllergyOpen(true)} addLabel="Add allergy"
              >
                <div className="space-y-1.5">
                  {structuredAllergies.length > 0
                    ? structuredAllergies.slice(0, 6).map((a: any) => (
                      <div key={a.id} className="flex items-center justify-between gap-2 text-xs">
                        <span className="min-w-0 truncate font-medium text-red-600 dark:text-red-400">{a.allergen}</span>
                        <Badge variant="outline" className="text-[10px] capitalize shrink-0">{a.severity}</Badge>
                      </div>
                    ))
                    : (patient.allergies ?? []).slice(0, 6).map((a: string) => (
                      <div key={a} className="text-xs font-medium text-red-600 dark:text-red-400">{a}</div>
                    ))}
                </div>
              </CoverSheetWidget>

              {/* Babies (mother-baby linkage) — only shown for patients with recorded deliveries */}
              {babies.length > 0 && (
                <CoverSheetWidget
                  title="Babies" icon={Baby}
                  count={babies.length}
                  isEmpty={false}
                >
                  <div className="space-y-1.5">
                    {babies.map((b: any) => (
                      <div key={b.id} className="flex items-center justify-between gap-2 text-xs">
                        <span className="min-w-0 truncate">{b.first_name} {b.last_name} · {b.gender ?? "—"} · {b.date_of_birth}</span>
                        <button
                          className="shrink-0 text-primary hover:underline"
                          onClick={() => navigate(`/hospital/patients/${b.mrn}`)}
                        >
                          View
                        </button>
                      </div>
                    ))}
                  </div>
                </CoverSheetWidget>
              )}

              {/* Postings */}
              <CoverSheetWidget
                title="Postings" icon={Megaphone}
                count={postings.length}
                isEmpty={postings.length === 0}
                emptyLabel="No active postings"
                onAdd={() => setPostingOpen(true)} addLabel="Add posting"
              >
                <div className="space-y-1.5">
                  {postings.slice(0, 6).map((p: any) => (
                    <div key={p.id} className="flex items-start justify-between gap-2 text-xs">
                      <div className="min-w-0">
                        <Badge variant="outline" className={cn("text-[10px] capitalize mr-1.5",
                          p.severity === "critical" ? "border-red-500/30 text-red-500 bg-red-500/10" :
                          p.severity === "warning" ? "border-amber-500/30 text-amber-500 bg-amber-500/10" :
                          "border-slate-500/30 text-slate-400"
                        )}>{p.posting_type}</Badge>
                        <span className="align-middle">{p.message}</span>
                      </div>
                      <button
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                        onClick={() => resolvePostingMut.mutate(p.id)}
                        title="Resolve"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Active Medications */}
              <CoverSheetWidget
                title="Active Medications" icon={Pill}
                count={activeMeds.length}
                isEmpty={activeMeds.length === 0}
                emptyLabel="No active medications"
                onAdd={() => setRxOpen(true)} addLabel="Prescribe"
                onViewAll={() => setMainTab("meds")}
              >
                <div className="space-y-1.5">
                  {activeMeds.slice(0, 6).map((rx: any) => {
                    const noDetail = isPlaceholderRecord(rx.drug_name, rx.external_source);
                    return (
                      <button
                        key={rx.id}
                        onClick={() => setRecordDetail({
                          title: "Medication Details",
                          subtitle: noDetail ? "No drug detail captured" : rx.drug_name,
                          rows: [
                            ["Drug", noDetail ? "Not captured by source" : rx.drug_name],
                            ["Dosage", rx.dosage],
                            ["Frequency", rx.frequency],
                            ["Duration", rx.duration],
                            ["Route", rx.route],
                            ["Status", rx.status?.replace(/_/g, " ")],
                            ["Prescribed by", formatAttribution(rx.prescribed_by)],
                            ["Prescribed at", rx.prescribed_at ? fmtDateTime(rx.prescribed_at) : null],
                            ["Dispensed at", rx.dispensed_at ? fmtDateTime(rx.dispensed_at) : null],
                            ["Source", rx.external_source ?? "Native (prescribed in app)"],
                            ["External ID", rx.external_id],
                          ],
                        })}
                        className="flex w-full items-center justify-between gap-2 text-xs text-left rounded px-1 -mx-1 py-0.5 hover:bg-muted/60 transition-colors"
                      >
                        <span className={cn("min-w-0 truncate", noDetail && "italic text-muted-foreground")}>
                          {noDetail ? "No drug detail captured" : rx.drug_name}
                        </span>
                        <Badge variant="outline" className="text-[10px] capitalize shrink-0">{rx.status?.replace(/_/g, " ")}</Badge>
                      </button>
                    );
                  })}
                </div>
              </CoverSheetWidget>

              {/* Recent Lab Results */}
              <CoverSheetWidget
                title="Recent Lab Results" icon={TrendingUp}
                count={resultedLabs.length}
                isEmpty={resultedLabs.length === 0}
                emptyLabel="No resulted labs yet"
                onViewAll={() => setMainTab("labs")}
              >
                <div className="space-y-1.5">
                  {resultedLabs.slice(0, 6).map((o: any) => (
                    <button
                      key={o.id}
                      onClick={() => setRecordDetail({
                        title: "Lab Result Details",
                        subtitle: o.test_name,
                        rows: [
                          ["Test", o.test_name],
                          ["Result", o.result_summary],
                          ["Reference range", o.reference_range],
                          ["Interpretation", o.interpretation],
                          ["Critical", o.is_critical ? "Yes" : null],
                          ["Urgency", o.urgency],
                          ["Sample type", o.sample_type],
                          ["Ordered by", formatAttribution(o.ordered_by)],
                          ["Ordered at", o.ordered_at ? fmtDateTime(o.ordered_at) : null],
                          ["Resulted at", o.resulted_at ? fmtDateTime(o.resulted_at) : null],
                          ["Notes", o.notes],
                          ["Source", o.external_source ?? "Native (ordered in app)"],
                          ["External ID", o.external_id],
                        ],
                      })}
                      className="flex w-full items-center justify-between gap-2 text-xs text-left rounded px-1 -mx-1 py-0.5 hover:bg-muted/60 transition-colors"
                    >
                      <span className="min-w-0 truncate">{o.test_name}</span>
                      <span className="shrink-0 text-muted-foreground">{o.result_summary}</span>
                    </button>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Vitals */}
              <CoverSheetWidget
                title="Vitals" icon={Thermometer}
                count={vitals.length}
                isEmpty={!lastVitals}
                emptyLabel="No vitals recorded yet"
                onViewAll={vitals.length > 0 ? () => setVitalsDialogOpen(true) : undefined}
              >
                {lastVitals && (
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                    {lastVitals.bp_systolic != null && <div><span className="text-muted-foreground">BP </span>{lastVitals.bp_systolic}/{lastVitals.bp_diastolic}</div>}
                    {lastVitals.pulse != null && <div><span className="text-muted-foreground">Pulse </span>{lastVitals.pulse}</div>}
                    {lastVitals.temperature != null && <div><span className="text-muted-foreground">Temp </span>{lastVitals.temperature}°C</div>}
                    {lastVitals.spo2 != null && <div><span className="text-muted-foreground">SpO2 </span>{lastVitals.spo2}%</div>}
                    {lastVitals.weight != null && <div><span className="text-muted-foreground">Wt </span>{lastVitals.weight}kg</div>}
                    {lastVitals.height != null && <div><span className="text-muted-foreground">Ht </span>{lastVitals.height}cm</div>}
                  </div>
                )}
              </CoverSheetWidget>

              {/* Appointments / Visits */}
              <CoverSheetWidget
                title="Appointments / Visits" icon={CalendarClock}
                count={appointmentsAndVisits.length}
                isEmpty={appointmentsAndVisits.length === 0}
                emptyLabel="No appointments or visits"
                onAdd={() => setFollowUpOpen(true)} addLabel="Schedule follow-up"
              >
                <div className="space-y-1.5">
                  {appointmentsAndVisits.slice(0, 6).map((v, idx) => (
                    <button
                      key={idx}
                      onClick={() => setRecordDetail({
                        title: v.kind === "appointment" ? "Appointment Details" : "Visit Details",
                        subtitle: `${fmtDate(v.date)} · ${v.label}`,
                        rows: v.kind === "appointment"
                          ? [
                              ["Status", (v.record.ui_status ?? v.record.status)?.replace(/_/g, " ")],
                              ["Department", v.record.department],
                              ["Doctor", formatAttribution(v.record.doctor_name)],
                              ["Date", v.record.slot_date ? fmtDate(v.record.slot_date) : null],
                              ["Time", v.record.slot_time],
                              ["Duration", v.record.duration_mins != null ? `${v.record.duration_mins} min` : null],
                              ["Type", v.record.appointment_type],
                              ["Reason", v.record.reason],
                              ["Booked by", v.record.booked_by],
                              ["Booked at", v.record.booked_at ? fmtDateTime(v.record.booked_at) : null],
                              ["Reminder sent", v.record.reminder_sent ? `Yes${v.record.reminder_sent_at ? " · " + fmtDateTime(v.record.reminder_sent_at) : ""}` : "No"],
                              ["Cancellation reason", v.record.cancellation_reason],
                              ["Notes", v.record.notes],
                              ["MRN", v.record.mrn],
                              ["Phone", v.record.patient_phone],
                              ["Source", v.record.external_source ?? "Native (booked in app)"],
                              ["External ID", v.record.external_id],
                            ]
                          : [
                              ["Status", v.record.status?.replace(/_/g, " ")],
                              ["Department", v.record.department],
                              ["Encounter type", v.record.encounter_type?.replace(/_/g, " ")],
                              ["Created", v.record.created_at ? fmtDateTime(v.record.created_at) : null],
                              ["Discharged", v.record.discharge_at ? fmtDateTime(v.record.discharge_at) : null],
                              ["Triage level", v.record.triage_level],
                              ["Consulting doctor", v.record.consulting_doctor],
                              ["Ward", v.record.ward_id],
                              ["Chief complaint", v.record.chief_complaint],
                              ["Notes", v.record.notes],
                              ["Source", v.record.external_source ?? "Native (opened in app)"],
                              ["External ID", v.record.external_id],
                            ],
                      })}
                      className="flex w-full items-center justify-between gap-2 text-xs text-left rounded px-1 -mx-1 py-0.5 hover:bg-muted/60 transition-colors"
                    >
                      <div className="min-w-0">
                        <span className="text-muted-foreground mr-1">{fmtDate(v.date)}</span>
                        <span className="truncate">{v.label}</span>
                      </div>
                      <Badge variant="outline" className="text-[10px] capitalize shrink-0">{v.status?.replace(/_/g, " ")}</Badge>
                    </button>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Clinical Reminders */}
              <CoverSheetWidget
                title="Clinical Reminders" icon={Bell}
                count={reminders.length}
                isEmpty={reminders.length === 0}
                emptyLabel="No reminders due"
              >
                <div className="space-y-1.5">
                  {reminders.slice(0, 6).map((r: any) => (
                    <div key={r.id} className="flex items-start justify-between gap-2 text-xs">
                      <button
                        onClick={() => setRecordDetail({
                          title: "Reminder Details",
                          subtitle: r.message,
                          rows: [
                            ["Message", r.message],
                            ["Severity", r.severity],
                            ["Rule", r.rule_key],
                            ["Due since", r.due_since ? fmtDate(r.due_since) : null],
                            ["Created", r.created_at ? fmtDateTime(r.created_at) : null],
                          ],
                        })}
                        className="min-w-0 text-left text-amber-600 dark:text-amber-400 hover:underline"
                      >
                        {r.message}
                      </button>
                      <button
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                        onClick={() => dismissReminderMut.mutate(r.id)}
                        title="Dismiss"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Recent Immunizations */}
              <CoverSheetWidget
                title="Recent Immunizations" icon={Syringe}
                count={immunisations.length}
                isEmpty={immunisations.length === 0}
                emptyLabel="No immunizations recorded"
                onAdd={() => setImmunisationOpen(true)} addLabel="Log immunization"
              >
                <div className="space-y-1.5">
                  {immunisations.slice(0, 6).map((im: any) => (
                    <button
                      key={im.id}
                      onClick={() => setRecordDetail({
                        title: "Immunization Details",
                        subtitle: im.vaccine_name,
                        rows: [
                          ["Vaccine", im.vaccine_name],
                          ["Dose #", im.dose_number],
                          ["Date given", im.date_given ? fmtDate(im.date_given) : null],
                          ["Batch #", im.batch_number],
                          ["Site", im.site],
                          ["Administered by", formatAttribution(im.administered_by)],
                          ["Next due", im.next_due_date ? fmtDate(im.next_due_date) : null],
                          ["Reaction", im.reaction],
                          ["Notes", im.notes],
                        ],
                      })}
                      className="flex w-full items-center justify-between gap-2 text-xs text-left rounded px-1 -mx-1 py-0.5 hover:bg-muted/60 transition-colors"
                    >
                      <span className="min-w-0 truncate">{im.vaccine_name}{im.dose_number ? ` (dose ${im.dose_number})` : ""}</span>
                      <span className="shrink-0 text-muted-foreground">{fmtDate(im.date_given)}</span>
                    </button>
                  ))}
                </div>
              </CoverSheetWidget>
            </div>
          )}

          {/* ── Tab: Problems ── */}
          {mainTab === "problems" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">{problems.filter(p => p.status === "active").length} active, {problems.filter(p => p.status === "resolved").length} resolved</p>
                <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" onClick={() => setProblemOpen(true)}>
                  <Plus className="h-3 w-3" /> Add Problem
                </Button>
              </div>
              {problems.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                  <ListChecks className="h-7 w-7 opacity-30" />No problems recorded
                </div>
              ) : (
                <div className="space-y-2">
                  {problems.map((p: any) => (
                    <div key={p.id} className="flex items-start justify-between gap-3 rounded-xl border border-border/60 bg-card px-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          {p.icd10_code && <span className="font-mono text-xs text-muted-foreground">{p.icd10_code}</span>}
                          <Badge variant="outline" className={cn("text-[10px] capitalize",
                            p.status === "active" ? "border-blue-500/30 text-blue-400 bg-blue-500/10" :
                            p.status === "resolved" ? "border-green-500/30 text-green-400 bg-green-500/10" :
                            "border-slate-500/30 text-slate-400"
                          )}>{p.status}</Badge>
                        </div>
                        <p className="text-sm font-medium">{p.description}</p>
                        {p.onset_date && <p className="text-xs text-muted-foreground mt-0.5">Onset: {fmtDate(p.onset_date)}</p>}
                      </div>
                      {p.status === "active" && (
                        <Button
                          size="sm" variant="ghost"
                          className="h-7 px-2 text-xs text-green-400 hover:text-green-300 hover:bg-green-500/10 shrink-0"
                          onClick={() => resolveProblemMut.mutate(p.id)}
                          disabled={resolveProblemMut.isPending}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Tab: Consent ── */}
          {mainTab === "consent" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">{consents.length} record{consents.length !== 1 ? "s" : ""}</p>
                <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" onClick={() => setConsentOpen(true)}>
                  <Plus className="h-3 w-3" /> Record Consent
                </Button>
              </div>
              {consents.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                  <ShieldAlert className="h-7 w-7 opacity-30" />No consent records
                </div>
              ) : (
                <div className="space-y-2">
                  {consents.map((c: any) => (
                    <div key={c.id} className="rounded-xl border border-border/60 bg-card px-3 py-2.5">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium capitalize">{(c.consent_type ?? "").replace(/_/g, " ")}</span>
                        {c.consented
                          ? <Badge variant="outline" className="text-[10px] border-green-500/30 text-green-400 bg-green-500/10 gap-1"><CheckCircle2 className="h-2.5 w-2.5"/>Consented</Badge>
                          : <Badge variant="outline" className="text-[10px] border-red-500/30 text-red-400 bg-red-500/10 gap-1"><XCircle className="h-2.5 w-2.5"/>Refused</Badge>
                        }
                      </div>
                      <p className="text-[11px] text-muted-foreground">{fmtDateTime(c.signed_at)} · {c.captured_by ?? "—"}</p>
                      {c.notes && <p className="text-xs text-muted-foreground mt-1 italic">"{c.notes}"</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Tab: Specialist ── */}
          {mainTab === "specialist" && (
            <div className="space-y-2">
              {specialistNotes.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                  <ClipboardCheck className="h-7 w-7 opacity-30" />
                  <p>No specialist notes yet</p>
                  <Button
                    size="sm" variant="outline"
                    onClick={() => navigate("/hospital/specialist")}
                  >
                    Go to Specialist Clinics
                  </Button>
                </div>
              ) : (
                specialistNotes.map((n: any, idx: number) => (
                  <div key={n.id ?? idx} className="rounded-xl border border-border/60 bg-card px-4 py-3">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="text-[10px] capitalize bg-indigo-500/10 border-indigo-500/30 text-indigo-400">
                          {(n.specialty ?? n.template_specialty ?? "specialist").replace(/_/g, " ")}
                        </Badge>
                        {n.icd10_codes && n.icd10_codes.length > 0 && n.icd10_codes.map((code: string) => (
                          <span key={code} className="font-mono text-[10px] text-muted-foreground">{code}</span>
                        ))}
                        {n.is_amended && (
                          <Badge variant="outline" className="text-[10px] border-yellow-500/30 text-yellow-400 bg-yellow-500/10 gap-1">
                            <PenLine className="h-2.5 w-2.5" />Amended
                          </Badge>
                        )}
                      </div>
                      <span className="shrink-0 text-[11px] text-muted-foreground">{fmtDateTime(n.created_at)}</span>
                    </div>
                    {n.encounter_id && (
                      <p className="text-[11px] text-muted-foreground mb-2">Encounter: <span className="font-mono">{n.encounter_id}</span></p>
                    )}
                    {n.fields && typeof n.fields === "object" && Object.keys(n.fields).length > 0 && (
                      <div className="mt-1 grid grid-cols-1 gap-1.5 rounded-lg bg-muted/40 px-3 py-2">
                        {Object.entries(n.fields as Record<string, any>).map(([key, val]) => (
                          val != null && val !== "" && val !== false ? (
                            <div key={key} className="flex gap-2 text-xs">
                              <span className="shrink-0 capitalize text-muted-foreground min-w-[120px]">
                                {key.replace(/_/g, " ")}
                              </span>
                              <span className="font-medium">
                                {typeof val === "boolean" ? (val ? "Yes" : "No") : String(val)}
                              </span>
                            </div>
                          ) : null
                        ))}
                      </div>
                    )}
                    {n.written_by && (
                      <p className="mt-2 text-[10px] text-muted-foreground">Written by: {n.written_by}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* ── Tab: Meds ── */}
          {mainTab === "meds" && (
            <div className="space-y-4">
              {/* Active */}
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Active Medications</h3>
                {activeMeds.length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">No active medications</p>
                ) : activeMeds.map((rx: any) => {
                  const noDetail = isPlaceholderRecord(rx.drug_name, rx.external_source);
                  return (
                    <div key={rx.id} className="mb-2 flex items-start justify-between gap-3 rounded-xl border border-border/60 bg-card px-3 py-2.5">
                      <div>
                        {noDetail ? (
                          <>
                            <p className="text-sm font-semibold italic text-muted-foreground">No drug detail captured</p>
                            <p className="text-xs text-muted-foreground">Legacy billing record only — source system didn't record a medication name or dosage</p>
                          </>
                        ) : (
                          <>
                            <p className="text-sm font-semibold">{rx.drug_name}</p>
                            <p className="text-xs text-muted-foreground">{rx.dosage} · {rx.frequency} · {rx.duration} · Route: {rx.route}</p>
                          </>
                        )}
                      </div>
                      <Badge variant="outline" className={cn("text-[10px] capitalize shrink-0", noDetail ? "bg-muted text-muted-foreground border-border" : "bg-green-50 text-green-700 border-green-300")}>{rx.status?.replace(/_/g," ")}</Badge>
                    </div>
                  );
                })}
              </div>
              {/* Past */}
              {(data?.prescriptions ?? []).filter((rx: any) => !["pending","partially_dispensed"].includes(rx.status)).length > 0 && (
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Past Medications</h3>
                  {(data?.prescriptions ?? []).filter((rx: any) => !["pending","partially_dispensed"].includes(rx.status)).map((rx: any) => {
                    const noDetail = isPlaceholderRecord(rx.drug_name, rx.external_source);
                    return (
                      <div key={rx.id} className="mb-2 flex items-start justify-between gap-3 rounded-xl border border-border/60 bg-muted/30 px-3 py-2">
                        <div>
                          {noDetail ? (
                            <>
                              <p className="text-sm italic text-muted-foreground">No drug detail captured</p>
                              <p className="text-xs text-muted-foreground">Legacy billing record only</p>
                            </>
                          ) : (
                            <>
                              <p className="text-sm">{rx.drug_name}</p>
                              <p className="text-xs text-muted-foreground">{rx.dosage} · {rx.frequency}</p>
                            </>
                          )}
                        </div>
                        <Badge variant="outline" className="text-[10px] capitalize shrink-0">{rx.status?.replace(/_/g," ")}</Badge>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── Tab: Orders ── */}
          {mainTab === "orders" && (
            <div className="space-y-4">
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lab Orders</h3>
                {(data?.lab_orders ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">No lab orders</p>
                ) : (data?.lab_orders ?? []).map((o: any) => {
                  const noDetail = isPlaceholderRecord(o.test_name, o.external_source);
                  return (
                    <div key={o.id} className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-card px-3 py-2">
                      <div>
                        <p className={cn("text-sm font-medium", noDetail && "italic text-muted-foreground")}>
                          {noDetail ? "No test detail captured" : o.test_name}
                        </p>
                        <p className="text-xs text-muted-foreground">{noDetail ? "Legacy record — source system only recorded an internal catalog ID" : fmtDate(o.ordered_at)}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Badge variant="outline" className="text-[10px] uppercase">{o.urgency}</Badge>
                        <Badge variant="outline" className="text-[10px] capitalize">{o.status}</Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Imaging Orders</h3>
                {radOrders.length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">No imaging orders</p>
                ) : radOrders.map((o: any) => (
                  <div key={o.id} className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-card px-3 py-2">
                    <div>
                      <p className="text-sm font-medium">{o.modality?.toUpperCase()} — {o.body_part}</p>
                      <p className="text-xs text-muted-foreground">{o.clinical_indication} · {fmtDate(o.ordered_at)}</p>
                    </div>
                    <Badge variant="outline" className="text-[10px] capitalize shrink-0">{o.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Tab: Notes ── */}
          {mainTab === "notes" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">{encNotes.length} note{encNotes.length !== 1 ? "s" : ""}</p>
                {isDoctor && hasActiveEnc && (
                  <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" onClick={() => setNoteOpen(true)}>
                    <NotebookPen className="h-3 w-3" /> Add Progress Note
                  </Button>
                )}
              </div>
              {encNotes.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                  <NotebookPen className="h-7 w-7 opacity-30" />No progress notes yet
                </div>
              ) : encNotes.map((n: any, idx: number) => {
                let soap: Record<string,string> | null = null;
                try { soap = JSON.parse(n.content); } catch { /**/ }
                return (
                  <div key={n.id ?? idx} className="rounded-xl border border-border/60 bg-card px-4 py-3">
                    <div className="mb-2 flex items-center justify-between">
                      <Badge variant="outline" className="text-[10px] capitalize">{(n.note_type ?? "note").replace(/_/g," ")}</Badge>
                      <span className="text-[11px] text-muted-foreground">{fmtDateTime(n.created_at)} · {n.created_by}</span>
                    </div>
                    {soap ? (
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        {(["subjective","objective","assessment","plan"] as const).map(k => soap![k] ? (
                          <div key={k} className="rounded-lg bg-muted/40 p-2">
                            <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-1">{k[0].toUpperCase()}</p>
                            <p className="leading-snug">{soap![k]}</p>
                          </div>
                        ) : null)}
                      </div>
                    ) : (
                      <p className="text-sm text-foreground/80 whitespace-pre-wrap">{n.content}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* ── Tab: Labs ── */}
          {mainTab === "labs" && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Resulted lab orders with reference ranges</p>
              {(data?.lab_orders ?? []).filter((o: any) => o.status === "resulted" || o.result_summary).length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                  <TrendingUp className="h-7 w-7 opacity-30" />No results yet
                </div>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted/40 border-b">
                        {["Test","Result","Reference","Interp.","Date"].map(h => (
                          <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(data?.lab_orders ?? []).filter((o: any) => o.result_summary || o.result_value).map((o: any) => {
                        const ref = refRanges.find(r => r.test_name?.toLowerCase() === o.test_name?.toLowerCase());
                        const val = parseFloat(o.result_value ?? o.result_summary ?? "");
                        const isAbnormal = ref && !isNaN(val) && (val < (ref.normal_low ?? -Infinity) || val > (ref.normal_high ?? Infinity));
                        return (
                          <tr key={o.id} className={cn("border-b last:border-0", isAbnormal && "bg-red-50/50")}>
                            <td className="px-3 py-2 font-medium">{o.test_name}</td>
                            <td className={cn("px-3 py-2 font-semibold", isAbnormal ? "text-red-700" : "text-green-700")}>
                              {o.result_summary ?? o.result_value ?? "—"}
                              {isAbnormal && <AlertTriangle className="inline ml-1 h-3 w-3 text-red-600" />}
                            </td>
                            <td className="px-3 py-2 text-xs text-muted-foreground">
                              {ref ? `${ref.normal_low ?? "?"}–${ref.normal_high ?? "?"} ${ref.unit ?? ""}` : o.reference_range ?? "—"}
                            </td>
                            <td className="px-3 py-2">
                              <Badge variant="outline" className="text-[10px] capitalize">{o.interpretation ?? "—"}</Badge>
                            </td>
                            <td className="px-3 py-2 text-xs text-muted-foreground">{fmtDate(o.resulted_at ?? o.ordered_at)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Tab: Surgery ── */}
          {mainTab === "surgery" && (
            <div className="space-y-3">
              {theatreCases.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                  <Scissors className="h-7 w-7 opacity-30" />No surgical cases
                </div>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted/40 border-b">
                        {["Procedure","Theatre","Surgeon","Urgency","Status","Date"].map(h => (
                          <th key={h} className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {theatreCases.map((c: any) => (
                        <tr key={c.id} className="border-b last:border-0">
                          <td className="px-3 py-2 font-medium">{c.procedure_name}</td>
                          <td className="px-3 py-2 text-muted-foreground">{c.theatre_name ?? "—"}</td>
                          <td className="px-3 py-2 text-muted-foreground">{c.surgeon_id ?? "—"}</td>
                          <td className="px-3 py-2">
                            <Badge variant="outline" className="text-[10px] capitalize">{c.urgency}</Badge>
                          </td>
                          <td className="px-3 py-2">
                            <Badge variant="outline" className="text-[10px] capitalize">{c.status?.replace(/_/g," ")}</Badge>
                          </td>
                          <td className="px-3 py-2 text-xs text-muted-foreground">{fmtDate(c.scheduled_date)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </main>

        {/* ── RIGHT: Action Panel ────────────────────────────────────────── */}
        <aside className="flex w-48 shrink-0 flex-col gap-2">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Actions</p>

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            onClick={openEditPatient}
          >
            <PenLine className="h-3.5 w-3.5" />
            Edit Patient Info
          </Button>

          <Button
            className="w-full justify-start gap-2"
            size="sm"
            onClick={() => setEncounterOpen(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            New Encounter
          </Button>

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            onClick={() => setLabOpen(true)}
            disabled={!hasActiveEnc}
          >
            <FlaskConical className="h-3.5 w-3.5" />
            Add Lab Order
          </Button>
          {!hasActiveEnc && (
            <p className="text-[10px] text-muted-foreground -mt-1 pl-1">Open encounter first</p>
          )}

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            onClick={() => setRxOpen(true)}
            disabled={!hasActiveEnc}
          >
            <Pill className="h-3.5 w-3.5" />
            Prescribe
          </Button>

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            onClick={() => setFollowUpOpen(true)}
          >
            <CalendarPlus className="h-3.5 w-3.5" />
            Schedule Follow-up
          </Button>

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            disabled={!patient?.id}
            onClick={() => patient?.id && navigate(`/hospital/billing?patient_id=${patient.id}`)}
          >
            <Receipt className="h-3.5 w-3.5" />
            View Billing
          </Button>

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            onClick={() => navigate("/hospital/queue")}
          >
            <Activity className="h-3.5 w-3.5" />
            View Queue
          </Button>

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            onClick={() => setDocUploadOpen(true)}
          >
            <Upload className="h-3.5 w-3.5" />
            Upload Document
          </Button>

          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
            onClick={() => { setGeneratedLetter(null); setReferralOpen(true); }}
            disabled={!hasActiveEnc}
          >
            <Send className="h-3.5 w-3.5" />
            Referral Letter
          </Button>

          {hasActiveEnc && data?.active_encounter?.status === "billing_pending" && (
            <>
              <Separator className="my-1" />
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start gap-2 border-green-500/30 text-green-400 hover:bg-green-500/10"
                disabled={dischargeMut.isPending}
                onClick={() => setDischargeOpen(true)}
              >
                <UserCheck className="h-3.5 w-3.5" />
                Discharge
              </Button>
            </>
          )}
          {hasActiveEnc && data?.active_encounter?.status !== "billing_pending" && (
            <p className="text-[10px] text-muted-foreground pl-1">
              Discharge available once billing is finalized (current: {String(data?.active_encounter?.status ?? "").replace(/_/g, " ")})
            </p>
          )}

          <Separator className="my-2" />

          {/* Summary counts */}
          <div className="rounded-xl border border-border/50 bg-card p-3 space-y-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Summary</p>
            {[
              { label: "Encounters", value: data?.encounters.length ?? 0, icon: Stethoscope },
              { label: "Lab Orders", value: data?.lab_orders.length ?? 0, icon: FlaskConical },
              { label: "Prescriptions", value: data?.prescriptions.length ?? 0, icon: Pill },
              { label: "Bills", value: data?.bills.length ?? 0, icon: Receipt },
            ].map(({ label, value, icon: Icon }) => (
              <div key={label} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Icon className="h-3 w-3" /> {label}
                </span>
                <span className="font-semibold">{value}</span>
              </div>
            ))}
          </div>
        </aside>
      </div>

      {/* ── Add Problem Dialog ────────────────────────────────────────── */}
      <Dialog open={problemOpen} onOpenChange={setProblemOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Problem</DialogTitle>
            <DialogDescription>Add a condition to {fullName}'s problem list</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Search ICD-10</Label>
              <Input
                value={icd10Search}
                onChange={e => setIcd10Search(e.target.value)}
                placeholder="e.g. J18 or pneumonia"
              />
              {icd10Results.length > 0 && (
                <div className="rounded-md border max-h-36 overflow-y-auto">
                  {icd10Results.map((code: any) => (
                    <button
                      key={code.code}
                      className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors"
                      onClick={() => {
                        setProblemForm(f => ({ ...f, icd10_code: code.code, description: f.description || code.description }));
                        setIcd10Search(code.code + " — " + code.description);
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
              <Label>Description *</Label>
              <Input
                value={problemForm.description}
                onChange={e => setProblemForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Problem description"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Status</Label>
                <Select value={problemForm.status} onValueChange={v => setProblemForm(f => ({ ...f, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="chronic">Chronic</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Onset Date</Label>
                <Input type="date" value={problemForm.onset_date} onChange={e => setProblemForm(f => ({ ...f, onset_date: e.target.value }))} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setProblemOpen(false)}>Cancel</Button>
            <Button disabled={!problemForm.description.trim() || addProblemMut.isPending} onClick={() => addProblemMut.mutate()}>
              {addProblemMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Add Problem
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── All Vitals Dialog (Cover Sheet "View all") ──────────────────── */}
      <Dialog open={vitalsDialogOpen} onOpenChange={setVitalsDialogOpen}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>All Vitals</DialogTitle>
            <DialogDescription>Full vitals history for {fullName}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {vitals.map((v: any, idx: number) => (
              <div key={v.id ?? idx} className="rounded-xl border border-border/60 bg-card px-4 py-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Thermometer className="h-3.5 w-3.5 text-muted-foreground" />
                    Vitals Entry
                  </span>
                  <span className="text-[11px] text-muted-foreground">{fmtDateTime(v.recorded_at)}</span>
                </div>
                <div className="grid grid-cols-3 gap-x-4 gap-y-2 text-xs">
                  {v.bp_systolic != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">BP</p>
                      <p className="font-semibold">{v.bp_systolic}/{v.bp_diastolic} <span className="font-normal text-muted-foreground">mmHg</span></p>
                    </div>
                  )}
                  {v.pulse != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Pulse</p>
                      <p className="font-semibold">{v.pulse} <span className="font-normal text-muted-foreground">bpm</span></p>
                    </div>
                  )}
                  {v.temperature != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Temp</p>
                      <p className="font-semibold">{v.temperature}<span className="font-normal text-muted-foreground">°C</span></p>
                    </div>
                  )}
                  {v.spo2 != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">SpO2</p>
                      <p className="font-semibold">{v.spo2}<span className="font-normal text-muted-foreground">%</span></p>
                    </div>
                  )}
                  {v.respiratory_rate != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">RR</p>
                      <p className="font-semibold">{v.respiratory_rate} <span className="font-normal text-muted-foreground">/min</span></p>
                    </div>
                  )}
                  {v.weight != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Weight</p>
                      <p className="font-semibold">{v.weight} <span className="font-normal text-muted-foreground">kg</span></p>
                    </div>
                  )}
                  {v.height != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Height</p>
                      <p className="font-semibold">{v.height} <span className="font-normal text-muted-foreground">cm</span></p>
                    </div>
                  )}
                  {v.bmi != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">BMI</p>
                      <p className="font-semibold">{v.bmi}</p>
                    </div>
                  )}
                  {v.gcs != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">GCS</p>
                      <p className="font-semibold">{v.gcs}<span className="font-normal text-muted-foreground">/15</span></p>
                    </div>
                  )}
                  {v.pain_score != null && (
                    <div>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Pain</p>
                      <p className="font-semibold">{v.pain_score}<span className="font-normal text-muted-foreground">/10</span></p>
                    </div>
                  )}
                </div>
                {v.notes && (
                  <p className="mt-2 text-xs text-muted-foreground italic border-t border-border/50 pt-1.5">"{v.notes}"</p>
                )}
                {v.recorded_by && (
                  <p className="mt-1 text-[10px] text-muted-foreground">Recorded by: {v.recorded_by}</p>
                )}
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Add Posting Dialog ────────────────────────────────────────── */}
      <Dialog open={postingOpen} onOpenChange={setPostingOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Posting</DialogTitle>
            <DialogDescription>Add a clinical flag/notice to {fullName}'s chart</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Type</Label>
                <Select value={postingForm.posting_type} onValueChange={v => setPostingForm(f => ({ ...f, posting_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="alert">Alert</SelectItem>
                    <SelectItem value="precaution">Precaution</SelectItem>
                    <SelectItem value="directive">Directive</SelectItem>
                    <SelectItem value="note">Note</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Severity</Label>
                <Select value={postingForm.severity} onValueChange={v => setPostingForm(f => ({ ...f, severity: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="info">Info</SelectItem>
                    <SelectItem value="warning">Warning</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>Message *</Label>
              <Textarea
                value={postingForm.message}
                onChange={e => setPostingForm(f => ({ ...f, message: e.target.value }))}
                placeholder="e.g. Fall risk — assist ambulation"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPostingOpen(false)}>Cancel</Button>
            <Button disabled={!postingForm.message.trim() || addPostingMut.isPending} onClick={() => addPostingMut.mutate()}>
              {addPostingMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Add Posting
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Allergy Dialog ────────────────────────────────────────── */}
      <Dialog open={allergyOpen} onOpenChange={setAllergyOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Allergy</DialogTitle>
            <DialogDescription>Record a documented allergy for {fullName}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Allergen *</Label>
              <Input
                value={allergyForm.allergen}
                onChange={e => setAllergyForm(f => ({ ...f, allergen: e.target.value }))}
                placeholder="e.g. Penicillin"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Severity</Label>
                <Select value={allergyForm.severity} onValueChange={v => setAllergyForm(f => ({ ...f, severity: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="mild">Mild</SelectItem>
                    <SelectItem value="moderate">Moderate</SelectItem>
                    <SelectItem value="severe">Severe</SelectItem>
                    <SelectItem value="unknown">Unknown</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Reaction</Label>
                <Input
                  value={allergyForm.reaction}
                  onChange={e => setAllergyForm(f => ({ ...f, reaction: e.target.value }))}
                  placeholder="e.g. Rash"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAllergyOpen(false)}>Cancel</Button>
            <Button disabled={!allergyForm.allergen.trim() || addAllergyMut.isPending} onClick={() => addAllergyMut.mutate()}>
              {addAllergyMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Add Allergy
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Edit Patient Information Dialog ─────────────────────────────── */}
      <Dialog open={editPatientOpen} onOpenChange={setEditPatientOpen}>
        <DialogContent className="sm:max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Patient Information</DialogTitle>
            <DialogDescription>Fill in or update {fullName}'s demographics</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Phone</Label>
                <Input
                  value={editPatientForm.phone}
                  onChange={e => setEditPatientForm(f => ({ ...f, phone: e.target.value }))}
                  placeholder="e.g. 08012345678"
                />
              </div>
              <div className="space-y-1">
                <Label>Blood Group</Label>
                <Select value={editPatientForm.blood_group || undefined} onValueChange={v => setEditPatientForm(f => ({ ...f, blood_group: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    {["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown"].map(bg => (
                      <SelectItem key={bg} value={bg}>{bg}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>Genotype</Label>
              <Input
                value={editPatientForm.genotype}
                onChange={e => setEditPatientForm(f => ({ ...f, genotype: e.target.value }))}
                placeholder="e.g. AA, AS, SS"
              />
            </div>
            <div className="space-y-1">
              <Label>Address</Label>
              <Textarea
                value={editPatientForm.address}
                onChange={e => setEditPatientForm(f => ({ ...f, address: e.target.value }))}
                placeholder="Residential address"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Next of Kin</Label>
                <Input
                  value={editPatientForm.next_of_kin_name}
                  onChange={e => setEditPatientForm(f => ({ ...f, next_of_kin_name: e.target.value }))}
                  placeholder="Full name"
                />
              </div>
              <div className="space-y-1">
                <Label>NOK Phone</Label>
                <Input
                  value={editPatientForm.next_of_kin_phone}
                  onChange={e => setEditPatientForm(f => ({ ...f, next_of_kin_phone: e.target.value }))}
                  placeholder="e.g. 08012345678"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Allergies</Label>
              <Input
                value={editPatientForm.allergies}
                onChange={e => setEditPatientForm(f => ({ ...f, allergies: e.target.value }))}
                placeholder="Comma-separated, e.g. Penicillin, Sulfa"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditPatientOpen(false)}>Cancel</Button>
            <Button disabled={editPatientMut.isPending} onClick={() => editPatientMut.mutate()}>
              {editPatientMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Log Immunisation Dialog ───────────────────────────────────── */}
      <Dialog open={immunisationOpen} onOpenChange={setImmunisationOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Log Immunization</DialogTitle>
            <DialogDescription>Record an immunization dose for {fullName}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Vaccine *</Label>
              <Input
                value={immunisationForm.vaccine_name}
                onChange={e => setImmunisationForm(f => ({ ...f, vaccine_name: e.target.value }))}
                placeholder="e.g. BCG"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Dose #</Label>
                <Input
                  type="number" min={1}
                  value={immunisationForm.dose_number}
                  onChange={e => setImmunisationForm(f => ({ ...f, dose_number: e.target.value }))}
                />
              </div>
              <div className="space-y-1">
                <Label>Site</Label>
                <Input
                  value={immunisationForm.site}
                  onChange={e => setImmunisationForm(f => ({ ...f, site: e.target.value }))}
                  placeholder="e.g. LTA"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImmunisationOpen(false)}>Cancel</Button>
            <Button disabled={!immunisationForm.vaccine_name.trim() || addImmunisationMut.isPending} onClick={() => addImmunisationMut.mutate()}>
              {addImmunisationMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Log Immunization
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Generic Record Detail Dialog (shared by every Cover Sheet card) ── */}
      <Dialog open={!!recordDetail} onOpenChange={(open) => !open && setRecordDetail(null)}>
        <DialogContent className="sm:max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{recordDetail?.title}</DialogTitle>
            {recordDetail?.subtitle && <DialogDescription>{recordDetail.subtitle}</DialogDescription>}
          </DialogHeader>
          {recordDetail && (
            <div className="space-y-1.5 text-sm">
              {recordDetail.rows
                .filter(([, value]) => value !== null && value !== undefined && value !== "")
                .map(([label, value]) => (
                  <div key={label} className="flex items-start justify-between gap-3 border-b border-border/40 py-1.5 last:border-0">
                    <span className="text-xs text-muted-foreground shrink-0">{label}</span>
                    <span className="text-right min-w-0 break-words">{value}</span>
                  </div>
                ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Record Consent Dialog ─────────────────────────────────────── */}
      <Dialog open={consentOpen} onOpenChange={setConsentOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Record Consent</DialogTitle>
            <DialogDescription>Document informed consent for {fullName}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Consent Type *</Label>
              <Select value={consentForm.consent_type} onValueChange={v => setConsentForm(f => ({ ...f, consent_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["general_treatment","surgery","anaesthesia","blood_transfusion","hiv_testing","data_processing","research","other"].map(t => (
                    <SelectItem key={t} value={t}>{t.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setConsentForm(f => ({ ...f, consented: !f.consented }))}
                className={cn("h-8 w-8 rounded-full border-2 flex items-center justify-center transition-colors",
                  consentForm.consented ? "border-green-500 bg-green-500/10" : "border-red-500 bg-red-500/10")}
              >
                {consentForm.consented
                  ? <CheckCircle2 className="h-4 w-4 text-green-400" />
                  : <XCircle className="h-4 w-4 text-red-400" />}
              </button>
              <span className="text-sm">{consentForm.consented ? "Patient consented" : "Patient refused"}</span>
            </div>
            <div className="space-y-1">
              <Label>Witness Name</Label>
              <Input value={consentForm.witness_name} onChange={e => setConsentForm(f => ({ ...f, witness_name: e.target.value }))} placeholder="Nurse / relative name" />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Textarea value={consentForm.notes} onChange={e => setConsentForm(f => ({ ...f, notes: e.target.value }))} rows={2} placeholder="Optional notes..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConsentOpen(false)}>Cancel</Button>
            <Button disabled={addConsentMut.isPending} onClick={() => addConsentMut.mutate()}>
              {addConsentMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save Consent
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Existing Encounter Dialog ──────────────────────────────────────────── */}
      <Dialog open={encounterOpen} onOpenChange={setEncounterOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Open New Encounter</DialogTitle>
            <DialogDescription>Register {fullName} into the clinical queue</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {hasActiveEnc && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-600">
                {fullName} already has an active encounter
                {data?.active_encounter?.queue_number ? ` (${data.active_encounter.queue_number})` : ""}
                {" "}— submitting will reuse it instead of creating a duplicate.
              </div>
            )}
            <div className="space-y-1">
              <Label>Encounter Type</Label>
              <Select
                value={encounterForm.encounter_type}
                onValueChange={v => setEncounterForm(f => ({ ...f, encounter_type: v }))}
              >
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
              <Input
                value={encounterForm.department}
                onChange={e => setEncounterForm(f => ({ ...f, department: e.target.value }))}
                placeholder="e.g. OPD, Cardiology"
              />
            </div>
            <div className="space-y-1">
              <Label>Chief Complaint</Label>
              <Textarea
                value={encounterForm.chief_complaint}
                onChange={e => setEncounterForm(f => ({ ...f, chief_complaint: e.target.value }))}
                placeholder="Presenting complaint..."
                rows={3}
              />
            </div>
            <CoverageQuote
              patientId={patient.id}
              serviceName="Consultation"
              category="consultation"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEncounterOpen(false)}>Cancel</Button>
            <Button disabled={openEncMut.isPending} onClick={() => openEncMut.mutate()}>
              {openEncMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Open Encounter
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Discharge Dialog ───────────────────────────────────────────── */}
      <Dialog open={dischargeOpen} onOpenChange={setDischargeOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Discharge Patient</DialogTitle>
            <DialogDescription>{fullName} — Encounter {String(data?.active_encounter?.id ?? "").slice(0, 8)}</DialogDescription>
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
              <Label>Discharge Summary *</Label>
              <Textarea
                value={dischargeForm.discharge_summary}
                onChange={e => setDischargeForm(f => ({ ...f, discharge_summary: e.target.value }))}
                placeholder="Clinical summary, follow-up instructions..."
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDischargeOpen(false)}>Cancel</Button>
            <Button
              className="bg-green-600 hover:bg-green-700"
              disabled={dischargeMut.isPending || !dischargeForm.discharge_summary.trim()}
              onClick={() => dischargeMut.mutate()}
            >
              {dischargeMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Confirm Discharge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Schedule Follow-up Dialog ──────────────────────────────────── */}
      <Dialog open={followUpOpen} onOpenChange={setFollowUpOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Schedule Follow-up</DialogTitle>
            <DialogDescription>Book an appointment for {fullName}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Date</Label>
              <Input
                type="date"
                value={followUpForm.slot_date}
                onChange={e => setFollowUpForm(f => ({ ...f, slot_date: e.target.value, slot_id: "" }))}
              />
            </div>
            <div className="space-y-1">
              <Label>Available Slot *</Label>
              <Select
                value={followUpForm.slot_id}
                onValueChange={v => setFollowUpForm(f => ({ ...f, slot_id: v }))}
                disabled={followUpSlotsLoading || followUpSlots.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder={
                    followUpSlotsLoading ? "Loading slots..." : followUpSlots.length === 0 ? "No slots available this date" : "Select a slot"
                  } />
                </SelectTrigger>
                <SelectContent>
                  {followUpSlots.map((s: any) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.start_time?.slice(0, 5)}
                      {s.provider_name ? ` — ${s.provider_name}` : ""}
                      {s.department ? ` (${s.department})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Appointment Type</Label>
              <Select value={followUpForm.appointment_type} onValueChange={v => setFollowUpForm(f => ({ ...f, appointment_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["follow_up", "consultation", "procedure", "review", "antenatal", "vaccination"].map(t => (
                    <SelectItem key={t} value={t} className="capitalize">{t.replace(/_/g, " ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Textarea value={followUpForm.notes} onChange={e => setFollowUpForm(f => ({ ...f, notes: e.target.value }))} rows={2} placeholder="Reason for follow-up..." />
            </div>
          </div>
          <DialogFooter className="sm:justify-between">
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-xs text-muted-foreground"
              onClick={() => { setFollowUpOpen(false); navigate("/calendar/tasks"); }}
            >
              View Full Doctor Calendar
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setFollowUpOpen(false)}>Cancel</Button>
              <Button
                disabled={!followUpForm.slot_id || followUpMut.isPending}
                onClick={() => followUpMut.mutate()}
              >
                {followUpMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Book Follow-up
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Lab Order Dialog ───────────────────────────────────────── */}
      <Dialog open={labOpen} onOpenChange={setLabOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Place Lab Order</DialogTitle>
            <DialogDescription>Order a diagnostic test for {fullName}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Test Name *</Label>
              <Input
                value={labForm.test_name}
                onChange={e => setLabForm(f => ({ ...f, test_name: e.target.value }))}
                placeholder="e.g. FBC, Malaria RDT, LFT"
              />
            </div>
            <div className="space-y-1">
              <Label>Urgency</Label>
              <Select value={labForm.urgency} onValueChange={v => setLabForm(f => ({ ...f, urgency: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="routine">Routine</SelectItem>
                  <SelectItem value="urgent">Urgent</SelectItem>
                  <SelectItem value="stat">STAT</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Clinical Notes</Label>
              <Textarea
                value={labForm.notes}
                onChange={e => setLabForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Additional clinical context..."
                rows={2}
              />
            </div>
            {labForm.test_name.trim() && (
              <CoverageQuote
                patientId={patient.id}
                serviceName={labForm.test_name}
                category="lab"
              />
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLabOpen(false)}>Cancel</Button>
            <Button disabled={!labForm.test_name.trim() || labMut.isPending} onClick={() => labMut.mutate()}>
              {labMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Place Order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* ── Prescribe Dialog ──────────────────────────────────────────── */}
      <Dialog open={rxOpen} onOpenChange={setRxOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Write Prescription</DialogTitle>
            <DialogDescription>Prescribe medication for {fullName}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Drug Name *</Label>
              <Input
                value={rxForm.drug_name}
                onChange={e => setRxForm(f => ({ ...f, drug_name: e.target.value }))}
                placeholder="e.g. Amoxicillin 500mg"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Dosage</Label>
                <Input
                  value={rxForm.dosage}
                  onChange={e => setRxForm(f => ({ ...f, dosage: e.target.value }))}
                  placeholder="e.g. 500mg"
                />
              </div>
              <div className="space-y-1">
                <Label>Frequency *</Label>
                <Select value={rxForm.frequency} onValueChange={v => setRxForm(f => ({ ...f, frequency: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="once daily">Once daily</SelectItem>
                    <SelectItem value="twice daily">Twice daily</SelectItem>
                    <SelectItem value="three times daily">Three times daily</SelectItem>
                    <SelectItem value="four times daily">Four times daily</SelectItem>
                    <SelectItem value="every 8 hours">Every 8 hours</SelectItem>
                    <SelectItem value="as needed">As needed (PRN)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Duration</Label>
                <Input
                  value={rxForm.duration}
                  onChange={e => setRxForm(f => ({ ...f, duration: e.target.value }))}
                  placeholder="e.g. 5 days"
                />
              </div>
              <div className="space-y-1">
                <Label>Route</Label>
                <Select value={rxForm.route} onValueChange={v => setRxForm(f => ({ ...f, route: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="oral">Oral</SelectItem>
                    <SelectItem value="iv">IV</SelectItem>
                    <SelectItem value="im">IM</SelectItem>
                    <SelectItem value="sc">SC</SelectItem>
                    <SelectItem value="topical">Topical</SelectItem>
                    <SelectItem value="inhaled">Inhaled</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {rxForm.drug_name.trim() && (
              <CoverageQuote
                patientId={patient.id}
                serviceName={rxForm.drug_name}
                category="pharmacy"
              />
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRxOpen(false)}>Cancel</Button>
            <Button
              disabled={!rxForm.drug_name.trim() || !rxForm.frequency.trim() || rxMut.isPending}
              onClick={() => rxMut.mutate()}
            >
              {rxMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Write Prescription
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Duplicate Prescription Alert Dialog ──────────────────────────── */}
      <Dialog open={!!duplicateRxAlert} onOpenChange={o => { if (!o) setDuplicateRxAlert(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <ShieldAlert className="h-5 w-5" />
              Duplicate Prescription
            </DialogTitle>
            <DialogDescription>{duplicateRxAlert?.message}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            {(duplicateRxAlert?.existing ?? []).map((rx: any, i: number) => (
              <div key={i} className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm">
                <p className="font-semibold">{rx.drug_name}</p>
                <p className="text-xs text-muted-foreground capitalize">
                  Status: {rx.status} — prescribed {rx.prescribed_at ? new Date(rx.prescribed_at).toLocaleDateString() : "—"}
                </p>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDuplicateRxAlert(null)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={rxMut.isPending}
              onClick={() => rxMut.mutate(true)}
            >
              {rxMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <AlertTriangle className="mr-2 h-4 w-4" />}
              Prescribe Anyway
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Upload Document Dialog ────────────────────────────────────────── */}
      <Dialog open={docUploadOpen} onOpenChange={setDocUploadOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>Attach a file to {fullName}'s record</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>File (PDF, image)</Label>
              <input
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                className="w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary-foreground"
                onChange={e => setUploadedFile(e.target.files?.[0] ?? null)}
              />
            </div>
            {uploadedFile && (
              <p className="text-xs text-muted-foreground">Selected: {uploadedFile.name} ({(uploadedFile.size / 1024).toFixed(1)} KB)</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDocUploadOpen(false)}>Cancel</Button>
            <Button disabled={!uploadedFile || docUploadMut.isPending} onClick={() => docUploadMut.mutate()}>
              {docUploadMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              <Upload className="mr-2 h-3.5 w-3.5" />Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Referral Letter Dialog ────────────────────────────────────────── */}
      <Dialog open={referralOpen} onOpenChange={(v) => { setReferralOpen(v); if (!v) setGeneratedLetter(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Referral Letter</DialogTitle>
            <DialogDescription>Generate a referral letter for {fullName}</DialogDescription>
          </DialogHeader>
          {generatedLetter ? (
            <div className="space-y-3">
              <pre className="max-h-80 overflow-y-auto rounded-lg bg-muted p-3 text-xs font-mono whitespace-pre-wrap">{generatedLetter}</pre>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => {
                  navigator.clipboard.writeText(generatedLetter);
                  toast({ title: "Copied to clipboard" });
                }}>Copy</Button>
                <Button size="sm" variant="outline" onClick={() => {
                  const blob = new Blob([generatedLetter], { type: "text/plain" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url; a.download = `referral-${patient.mrn}.txt`; a.click();
                  URL.revokeObjectURL(url);
                }}>Download</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4 py-2">
              <div className="space-y-1">
                <Label>Referring To *</Label>
                <Input value={referralForm.referring_to} onChange={e => setReferralForm(f => ({ ...f, referring_to: e.target.value }))} placeholder="e.g. Cardiology Dept, Lagos Island General Hospital" />
              </div>
              <div className="space-y-1">
                <Label>Reason for Referral *</Label>
                <Textarea value={referralForm.reason} onChange={e => setReferralForm(f => ({ ...f, reason: e.target.value }))} rows={3} placeholder="Clinical reason for referral..." />
              </div>
              <div className="grid grid-cols-2 gap-3">
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
                <div className="space-y-1">
                  <Label>Referring Doctor</Label>
                  <Input value={referralForm.referring_doctor} onChange={e => setReferralForm(f => ({ ...f, referring_doctor: e.target.value }))} placeholder="Dr. Name" />
                </div>
              </div>
              <div className="space-y-1">
                <Label>Additional Notes</Label>
                <Textarea value={referralForm.additional_notes} onChange={e => setReferralForm(f => ({ ...f, additional_notes: e.target.value }))} rows={2} placeholder="Any additional context..." />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setReferralOpen(false)}>Close</Button>
            {!generatedLetter && (
              <Button
                disabled={!referralForm.referring_to.trim() || !referralForm.reason.trim() || referralMut.isPending}
                onClick={() => referralMut.mutate()}
              >
                {referralMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <Send className="mr-2 h-3.5 w-3.5" />Generate Letter
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Progress Note Dialog (doctor-only) ────────────────────── */}
      <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <NotebookPen className="h-4 w-4" /> Add Progress Note
            </DialogTitle>
            <DialogDescription>{fullName} — {data?.active_encounter ? `Encounter #${data.active_encounter.id}` : ""}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Note Type</Label>
              <Select value={noteForm.note_type} onValueChange={v => setNoteForm(f => ({ ...f, note_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["soap","general","assessment","plan"].map(t => (
                    <SelectItem key={t} value={t} className="capitalize">{t.replace(/_/g," ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {[
              { key: "subjective", label: "S — Subjective (Patient's complaints)", placeholder: "Chief complaint, history..." },
              { key: "objective", label: "O — Objective (Examination findings)", placeholder: "Exam findings, vitals..." },
              { key: "assessment", label: "A — Assessment (Diagnosis)", placeholder: "Working diagnosis, ICD-10 codes..." },
              { key: "plan", label: "P — Plan (Management)", placeholder: "Investigations ordered, treatment plan, follow-up..." },
            ].map(({ key, label, placeholder }) => (
              <div key={key} className="space-y-1">
                <Label className="text-xs font-semibold">{label}</Label>
                <Textarea
                  value={(noteForm as any)[key]}
                  onChange={e => setNoteForm(f => ({ ...f, [key]: e.target.value }))}
                  placeholder={placeholder}
                  rows={2}
                  className="text-sm"
                />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNoteOpen(false)}>Cancel</Button>
            <Button
              disabled={!noteForm.assessment.trim() || noteMut.isPending || !data?.active_encounter}
              onClick={() => noteMut.mutate()}
            >
              {noteMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Note
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
