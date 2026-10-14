import { useState, useMemo } from "react";
import { encounterStatusLabel } from "@/lib/encounter-status";
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
  User, Phone, MapPin, Heart, Droplets, AlertTriangle,
  ShieldCheck, ShieldOff, Clock, Stethoscope, FlaskConical, Pill,
  Receipt, Activity, Plus, CalendarPlus, MessageSquare, UserCheck,
  ChevronRight, FileText, Loader2, ListChecks, ShieldAlert, CheckCircle2,
  XCircle, PenLine, Thermometer, TrendingUp, ClipboardCheck, Upload, Send,
  Scissors, ScanLine, Eye, NotebookPen, Megaphone, CalendarClock, Bell, Syringe, Baby,
  BedDouble, Landmark
} from "lucide-react";
import { BackButton } from "@/components/BackButton";
import { useAuth } from "@/components/AuthProvider";
import { EncounterStoryPanel } from "@/components/patient/EncounterStoryPanel";
import { api } from "@/lib/api-client";
import { ViewReportButton } from "@/components/reports/ResultReport";
import { useToast } from "@/hooks/use-toast";
import { CoverageQuote } from "@/components/CoverageQuote";
import { AlertBanner } from "@/components/AlertBanner";
import { AllergyBanner } from "@/components/AllergyBanner";
import { CoverSheetWidget } from "@/components/patient/CoverSheetWidget";
import { SoapNoteComposer } from "@/components/soap/SoapNoteComposer";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { FREQUENCY_OPTIONS, ROUTE_OPTIONS, DURATION_OPTIONS } from "@/lib/clinical-options";
import { RecordDetailPanel, type RecordDetail } from "@/components/patient/RecordDetailPanel";
import { LabWorkspacePanel } from "@/components/lab/LabWorkspacePanel";
import { RadiologyWorkspacePanel } from "@/components/radiology/RadiologyWorkspacePanel";
import { TheatreWorkspacePanel } from "@/components/theatre/TheatreWorkspacePanel";
import { RecordTable, CellStack, type RecordColumn } from "@/components/patient/RecordTable";

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
  // Added to royan_patients by migration 159 for the immunisation booklet
  // header (father's/guardian's name and place of birth). The page already
  // reads both; the interface simply never caught up.
  father_name?: string;
  place_of_birth?: string;
  mother_patient_id?: number | string | null;
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
  // Shipped by services/patient_context.py but never declared here — the page
  // reads data.clinical_notes for the Notes tab and only compiled because tsc
  // was disabled by an invalid tsconfig value.
  clinical_notes?: any[];
  // Also present in the payload and still unrendered; declared so a future
  // reader can see what is actually available rather than re-deriving it.
  discharges?: any[];
  payments?: any[];
  insurance_claims?: any[];
  radiology?: any[];
  coverage_authorizations?: any[];
  insurance_records?: any[];
  section_counts?: Record<string, number>;
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

// Builds the recordDetail payload for a prescription row — shared by the
// Active and Past Medications lists so dispensing history (added once here)
// shows up consistently in both instead of drifting between two copies.
/**
 * royan_ward_stay_history stores admitted_at/discharged_at and no duration, and
 * the endpoint computes none, so length of stay is derived here. An open stay
 * measures to now, which is what a ward round actually wants to know.
 */
function lengthOfStay(admitted?: string | null, discharged?: string | null): string | null {
  if (!admitted) return null;
  const start = new Date(admitted).getTime();
  const end = discharged ? new Date(discharged).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  const days = Math.floor((end - start) / 86_400_000);
  const hours = Math.floor(((end - start) % 86_400_000) / 3_600_000);
  const suffix = discharged ? "" : " so far";
  if (days === 0) return `${hours} hour${hours === 1 ? "" : "s"}${suffix}`;
  return `${days} day${days === 1 ? "" : "s"}${hours ? `, ${hours}h` : ""}${suffix}`;
}

/**
 * Structured SOAP columns first (notes written since the migration), falling
 * back to the older JSON-in-content convention. Extracted because the table
 * needs it in two columns and the panel needs it again on click.
 */
/**
 * The urgency left-border from the Laboratory worklist, so a stat order reads
 * the same on the chart as it does on the worklist.
 */
const URGENCY_ACCENT: Record<string, string> = {
  stat: "border-l-red-500",
  urgent: "border-l-orange-500",
  routine: "border-l-transparent",
};

/**
 * Specialist notes carry an open-ended note_data blob whose keys vary by
 * template, so the columns are derived rather than declared. Falsy values are
 * dropped: an unticked checkbox is not a finding.
 */
/**
 * One column set for both medication tables. A placeholder row (legacy billing
 * line with no drug name) renders muted and says so, rather than showing an
 * empty cell that reads as missing data.
 */
const MED_COLUMNS: RecordColumn<any>[] = [
  {
    header: "Drug",
    cell: (rx: any) => {
      const noDetail = isPlaceholderRecord(rx.drug_name, rx.external_source);
      return (
        <CellStack
          muted={noDetail}
          primary={noDetail ? "No drug detail captured" : rx.drug_name}
          secondary={noDetail ? "Legacy billing record only" : [rx.dosage, rx.frequency].filter(Boolean).join(" · ")}
        />
      );
    },
  },
  { header: "Route", width: "w-[100px]", className: "capitalize text-muted-foreground", cell: (rx: any) => rx.route ?? "—" },
  { header: "Duration", width: "w-[110px]", className: "text-muted-foreground", cell: (rx: any) => rx.duration ?? "—" },
  {
    header: "Status",
    width: "w-[130px]",
    cell: (rx: any) => (
      <Badge variant="outline" className="text-xs capitalize">
        {rx.status?.replace(/_/g, " ") ?? "—"}
      </Badge>
    ),
  },
];

function specialistNoteRows(n: any): [string, any][] {
  if (!n?.note_data || typeof n.note_data !== "object") return [];
  return Object.entries(n.note_data as Record<string, any>)
    .filter(([, val]) => val != null && val !== "" && val !== false)
    .map(([key, val]): [string, any] => [
      key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      typeof val === "boolean" ? (val ? "Yes" : "No") : String(val),
    ]);
}

function noteSoap(n: any): Record<string, string> | null {
  if (n.subjective || n.objective || n.assessment || n.plan) {
    return { subjective: n.subjective, objective: n.objective, assessment: n.assessment, plan: n.plan };
  }
  try { return JSON.parse(n.content); } catch { return null; }
}

function rxRecordDetail(rx: any, noDetail: boolean): RecordDetail {
  if (noDetail) {
    return {
      title: "Prescription",
      subtitle: `${new Date(rx.prescribed_at ?? "").toLocaleDateString("en-NG")}`,
      rows: [
        ["Status", "No drug detail captured"],
        ["Notes", "Legacy billing record only — the source system didn't record a medication name or dosage."],
      ],
    };
  }
  const dispensing: any[] = Array.isArray(rx.dispensing) ? rx.dispensing : [];
  return {
    title: rx.drug_name ?? "Prescription",
    subtitle: `${rx.dosage ?? "—"} · ${rx.frequency ?? "—"}`,
    rows: [
      ["Duration", rx.duration],
      ["Route", rx.route],
      ["Quantity", rx.quantity != null ? `${rx.quantity} ${rx.unit ?? ""}`.trim() : null],
      ["Special instructions", rx.special_instructions],
      ["Status", rx.status?.replace(/_/g, " ")],
      ["Prescribed by", formatAttribution(rx.prescribed_by)],
      ["Prescribed at", rx.prescribed_at ? fmtDateTime(rx.prescribed_at) : null],
      ...(dispensing.length > 0
        ? dispensing.map((d, i): [string, any] => [
            dispensing.length > 1 ? `Dispensed (${i + 1}/${dispensing.length})` : "Dispensed",
            `${d.quantity_dispensed ?? "—"} ${d.unit ?? ""} · ${formatAttribution(d.dispensed_by) ?? "—"} · ${d.dispensed_at ? fmtDateTime(d.dispensed_at) : "—"}${d.batch_number ? ` · Batch ${d.batch_number}` : ""}`,
          ])
        : [["Dispensed", rx.status === "pending" ? "Not yet dispensed" : null] as [string, any]]),
    ],
  };
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
  const [recordDetail, setRecordDetail] = useState<RecordDetail | null>(null);
  // Clinical records open in the same workspace panels the worklists use, so a
  // result looks identical whether reached from the chart or from Laboratory.
  const [labPanelOrder, setLabPanelOrder] = useState<any | null>(null);
  const [radPanelOrder, setRadPanelOrder] = useState<any | null>(null);
  const [radPanelTab, setRadPanelTab] = useState<string | undefined>(undefined);
  const [theatrePanelCase, setTheatrePanelCase] = useState<any | null>(null);
  // Opening a record from the timeline hides the story rather than stacking a
  // second right-hand Sheet over it — two Sheets means two focus traps. The
  // encounter is remembered so closing the record returns you to your place in
  // the story instead of dumping you back on the chart.
  const [storyReturnId, setStoryReturnId] = useState<number | null>(null);

  const openStoryRecord = (kind: string, record: any) => {
    setStoryReturnId(storyEncounterId);
    switch (kind) {
      case "lab": setLabPanelOrder(record); break;
      case "radiology":
        setRadPanelOrder(record);
        setRadPanelTab(record.reported_at ? "report" : "detail");
        break;
      case "note":
        setRecordDetail({
          title: record.note_title || `${(record.note_type ?? "clinical").replace(/_/g, " ")} note`,
          subtitle: record.created_at ? fmtDateTime(record.created_at) : undefined,
          icon: NotebookPen,
          badges: record.signed_at
            ? [{ label: "Signed", tone: "success" as const }]
            : [{ label: "Unsigned", tone: "warning" as const }],
          blocks: [
            { label: "Subjective", text: record.subjective },
            { label: "Objective", text: record.objective },
            { label: "Assessment", text: record.assessment },
            { label: "Plan", text: record.plan },
            ...(!record.subjective && !record.objective && !record.assessment && !record.plan
              ? [{ label: "Note", text: record.content }]
              : []),
          ],
          sections: [{
            label: "Attribution",
            rows: [
              ["Author", record.author_name],
              ["Signed at", record.signed_at ? fmtDateTime(record.signed_at) : null],
            ],
          }],
        });
        break;
      case "vitals":
        setRecordDetail({
          title: "Vitals",
          subtitle: record.recorded_at ? fmtDateTime(record.recorded_at) : undefined,
          icon: Thermometer,
          rows: [
            ["Blood pressure", record.bp_systolic != null && record.bp_diastolic != null ? `${record.bp_systolic}/${record.bp_diastolic} mmHg` : null],
            ["Pulse", record.pulse != null ? `${record.pulse} bpm` : null],
            ["Temperature", record.temperature != null ? `${record.temperature} °C` : null],
            ["SpO2", record.spo2 != null ? `${record.spo2}%` : null],
            ["Respiratory rate", record.respiratory_rate],
            ["Weight", record.weight != null ? `${record.weight} kg` : null],
            ["Height", record.height != null ? `${record.height} cm` : null],
            ["Pain score", record.pain_score],
            ["Recorded by", record.recorded_by],
          ],
        });
        break;
      case "bill":
        setRecordDetail({
          title: record.bill_number ? `Bill ${record.bill_number}` : "Bill",
          subtitle: record.billed_at ? fmtDateTime(record.billed_at) : undefined,
          icon: Receipt,
          badges: record.status ? [{ label: record.status.replace(/_/g, " "), tone: "info" as const }] : undefined,
          rows: [
            ["Subtotal", record.subtotal != null ? `₦${Number(record.subtotal).toLocaleString()}` : null],
            ["Discount", record.discount != null ? `₦${Number(record.discount).toLocaleString()}` : null],
            ["Total", record.total != null ? `₦${Number(record.total).toLocaleString()}` : null],
            ["Status", record.status?.replace(/_/g, " ")],
          ],
        });
        break;
    }
  };

  // Restore the story when the record opened from it closes.
  const returnToStory = () => {
    if (storyReturnId != null) {
      setStoryEncounterId(storyReturnId);
      setStoryReturnId(null);
    }
  };
  const [storyEncounterId, setStoryEncounterId] = useState<number | null>(null);
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
    father_name: "", place_of_birth: "",
  });
  const [noteOpen, setNoteOpen] = useState(false);
  const [problemOpen, setProblemOpen] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const [problemForm, setProblemForm] = useState({ description: "", icd10_code: "", status: "active", onset_date: "" });
  const [icd10Search, setIcd10Search] = useState("");
  const [drugSearch, setDrugSearch] = useState("");
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
    mutationFn: (overrideDuplicate: boolean = false) => api.hospital.pharmacy.createRx({
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
      // Every surface that lists appointments keeps its own React Query
      // cache under a different key (see CalendarTaskManager.tsx /
      // HospitalAppointments.tsx) — invalidate all of them so a follow-up
      // booked here shows up everywhere without a manual refresh.
      void qc.invalidateQueries({ queryKey: ["appointments"] });
      void qc.invalidateQueries({ queryKey: ["appointments-day"] });
      void qc.invalidateQueries({ queryKey: ["appointments-calendar"] });
      void qc.invalidateQueries({ queryKey: ["appointment-slots"] });
      void qc.invalidateQueries({ queryKey: ["sched-appointments"] });
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

  const { data: drugData } = useQuery({
    queryKey: ["patient-profile-drug-search", drugSearch],
    queryFn: () => api.hospital.clinical.searchDrugs(drugSearch),
    enabled: drugSearch.length >= 2,
    staleTime: 300_000,
  });
  const drugResults: any[] = Array.isArray(drugData?.drugs) ? drugData.drugs : [];

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

  // Cumulative imaging history — a DIFFERENT endpoint to the worklist above.
  // GET /radiology/orders is correctly restricted to native orders so 56k
  // Hope-imported rows never show as active queue entries; the patient chart
  // wants exactly those historical rows, so it uses /patients/{id}/history.
  const { data: radHistData } = useQuery({
    queryKey: ["patient-radiology-history", patientNumId],
    queryFn: () => api.hospital.radiology.patientHistory(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 300_000,
  });
  // Only studies that actually carry a result — the cover sheet shows reports,
  // not pending requests. 41,536 of 56,536 orders are reported; the remainder
  // were never reported in Hope either.
  const reportedImaging: any[] = (radHistData?.history ?? [])
    .filter((r: any) => r.report || r.impression || r.findings)
    .sort((a: any, b: any) => new Date(b.reported_at ?? 0).getTime() - new Date(a.reported_at ?? 0).getTime());

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

  // ── Encounter notes — full patient-level history from build_patient_context,
  // not a per-encounter fetch capped to the 10 most recent encounters. ──────────
  const encounters: any[] = Array.isArray(data?.encounters) ? data.encounters : [];
  const encNotes: any[] = Array.isArray(data?.clinical_notes) ? data.clinical_notes : [];

  // ── Roles (for notes write access) ───────────────────────────────────────────
  const { roles } = useAuth();
  const isDoctor = roles.some(r => ["doctor", "admin"].includes(r));

  // ── Computed CPRS summary values ──────────────────────────────────────────────
  const activeMeds = useMemo(() =>
    (data?.prescriptions ?? []).filter((rx: any) => ["pending", "partially_dispensed"].includes(rx.status)),
    [data?.prescriptions]
  );
  // The complement of activeMeds — was filtered inline twice in the Meds tab.
  const pastMeds = useMemo(() =>
    (data?.prescriptions ?? []).filter((rx: any) => !["pending", "partially_dispensed"].includes(rx.status)),
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

  // ── Phase B2: migrated Hope history ───────────────────────────────────────
  // These four datasets were loaded in Phase A but had no endpoint until B0,
  // so nothing in the app could show them. Coverage across 60,929 patients:
  // billing 93% · ward stays 5,923 · documents 3,093 · flowsheet 2,412.
  const { data: billingHistData } = useQuery({
    queryKey: ["patient-billing-history", patientNumId],
    queryFn: () => api.hospital.clinical.listBillingHistory(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 300_000,
  });
  const billingTxns: any[] = billingHistData?.transactions ?? [];
  const billingSummaries: any[] = billingHistData?.summaries ?? [];

  const { data: wardStayData } = useQuery({
    queryKey: ["patient-ward-stays", patientNumId],
    queryFn: () => api.hospital.clinical.listWardStays(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 300_000,
  });
  const wardStays: any[] = wardStayData?.stays ?? [];

  const { data: patientDocsData } = useQuery({
    queryKey: ["patient-documents-index", patientNumId],
    queryFn: () => api.hospital.clinical.listPatientDocuments(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 300_000,
  });
  const patientDocs: any[] = patientDocsData?.documents ?? [];

  const { data: flowsheetData } = useQuery({
    queryKey: ["patient-flowsheet", patientNumId],
    queryFn: () => api.hospital.clinical.listFlowsheet(patientNumId!),
    enabled: !!patientNumId,
    staleTime: 300_000,
  });
  const flowsheet: any[] = flowsheetData?.observations ?? [];

  // Hope's accounting side for this patient: vouchers, discount requests and
  // settlements. Loaded but never surfaced until now.
  const { data: ledger, isLoading: ledgerLoading } = useQuery({
    queryKey: ["patient-financial-ledger", patient?.id],
    queryFn: () => api.hospital.clinical.financialLedger(patient!.id),
    enabled: !!patient?.id,
  });
  const ledgerCount = Number(ledger?.count ?? 0);

  const outstandingBalance = billingSummaries.reduce(
    (sum, b) => sum + (Number(b.amount_pending) || 0), 0,
  );

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
      father_name: patient.father_name ?? "",
      place_of_birth: patient.place_of_birth ?? "",
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
      father_name: editPatientForm.father_name || null,
      place_of_birth: editPatientForm.place_of_birth || null,
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

  // Note writing lives in SoapNoteComposer now (see the Add Progress Note
  // dialog below) — it owns its own draft, gating, sign mutation and toasts.

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
        <BackButton fallback="/hospital/patients" variant="outline">Back to Patients</BackButton>
      </div>
    );
  }

  const fullName = `${patient.first_name} ${patient.last_name}`;
  const hasActiveEnc = !!data?.active_encounter;
  const insuranceActive = insurance?.active ?? false;

  return (
    <motion.div className="pce-readable flex h-full min-h-0 flex-col gap-0" {...motionTransitions.fadeInUp}>
      <AlertBanner className="mb-2" />
      <AllergyBanner allergies={patient.allergies} className="mb-2" />
      {/* Page header */}
      <div className="mb-4 flex items-center gap-3">
        <BackButton fallback="/hospital/patients" />
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
                    ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400"
                    : "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-400",
                )}>
                  {insuranceActive ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldOff className="h-3.5 w-3.5" />}
                  {insurance?.hmo_name ?? patient.hmo_provider ?? (insuranceActive ? "HMO Active" : "No HMO")}
                </div>
                {insurance?.plan_name && (
                  <p className="text-xs text-muted-foreground">{insurance.plan_name}</p>
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
                      <Badge key={a} variant="outline" className="text-xs bg-destructive/10 text-destructive border-destructive/30">
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
                        className="text-xs text-primary underline underline-offset-2"
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
                  <span className="ml-auto font-normal normal-case text-xs">{fmtDate(lastVitals.recorded_at)}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                {lastVitals.bp_systolic && (
                  <div><p className="text-muted-foreground text-xs">BP</p><p className="font-medium">{lastVitals.bp_systolic}/{lastVitals.bp_diastolic}</p></div>
                )}
                {lastVitals.pulse && (
                  <div><p className="text-muted-foreground text-xs">Pulse</p><p className="font-medium">{lastVitals.pulse} bpm</p></div>
                )}
                {lastVitals.temperature && (
                  <div><p className="text-muted-foreground text-xs">Temp</p><p className="font-medium">{lastVitals.temperature}°C</p></div>
                )}
                {lastVitals.spo2 && (
                  <div><p className="text-muted-foreground text-xs">SpO2</p><p className="font-medium">{lastVitals.spo2}%</p></div>
                )}
                {lastVitals.weight && (
                  <div><p className="text-muted-foreground text-xs">Weight</p><p className="font-medium">{lastVitals.weight} kg</p></div>
                )}
                {lastVitals.pain_score != null && (
                  <div><p className="text-muted-foreground text-xs">Pain</p><p className="font-medium">{lastVitals.pain_score}/10</p></div>
                )}
              </CardContent>
            </Card>
          )}
        </aside>

        {/* ── CENTER: Main Panel ─────────────────────────────────────────── */}
        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
          {/* Active encounter banner */}
          {hasActiveEnc && (
            <div className="mb-4 flex items-center gap-3 rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-2.5 text-sm text-blue-700 dark:text-blue-400">
              <Activity className="h-4 w-4 shrink-0 animate-pulse" />
              <span>
                Active encounter — <strong className="capitalize">
                  {encounterStatusLabel(data.active_encounter!.status)}
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
                  {encounterStatusLabel(data.last_encounter.status)}
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
                emptyLabel="None recorded yet — ask the patient"
                helpHintId="allergies-empty"
                onAdd={() => setAllergyOpen(true)} addLabel="Add allergy"
              >
                <div className="space-y-1.5">
                  {structuredAllergies.length > 0
                    ? structuredAllergies.slice(0, 6).map((a: any) => (
                      <div key={a.id} className="flex items-center justify-between gap-2 text-xs">
                        <span className="min-w-0 truncate font-medium text-red-600 dark:text-red-400">{a.allergen}</span>
                        <Badge variant="outline" className="text-xs capitalize shrink-0">{a.severity}</Badge>
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
                        <Badge variant="outline" className={cn("text-xs capitalize mr-1.5",
                          p.severity === "critical" ? "border-red-500/30 text-red-500 bg-red-500/10" :
                          p.severity === "warning" ? "border-amber-500/30 text-amber-500 bg-amber-500/10" :
                          "border-slate-500/30 text-slate-700 dark:text-slate-400"
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
                        <Badge variant="outline" className="text-xs capitalize shrink-0">{rx.status?.replace(/_/g, " ")}</Badge>
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
                      // The lab panel already renders this record properly —
                      // specimen chain, reference ranges, verify state, amend
                      // history. Re-flattening it here gave a worse view of
                      // the same data.
                      onClick={() => setLabPanelOrder(o)}
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
                helpHintId="vitals-recent-shown"
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
                      onClick={() => {
                        // A visit is a full clinical encounter — open the
                        // Encounter Story (the complete chronological record:
                        // vitals, notes, orders, results, dispensing, billing)
                        // instead of the flat status/date summary appointments
                        // still use, since a booking has no "story" to tell.
                        if (v.kind === "visit" && v.record.id) {
                          setStoryEncounterId(v.record.id);
                          return;
                        }
                        setRecordDetail({
                          title: "Appointment Details",
                          subtitle: `${fmtDate(v.date)} · ${v.label}`,
                          rows: [
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
                          ],
                        });
                      }}
                      className="flex w-full items-center justify-between gap-2 text-xs text-left rounded px-1 -mx-1 py-0.5 hover:bg-muted/60 transition-colors"
                    >
                      <div className="min-w-0">
                        <span className="text-muted-foreground mr-1">{fmtDate(v.date)}</span>
                        <span className="truncate">{v.label}</span>
                      </div>
                      <Badge variant="outline" className="text-xs capitalize shrink-0">{v.status?.replace(/_/g, " ")}</Badge>
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

              {/* ── Phase B2: migrated history that had no UI until now ────── */}

              {/* Billing — previously a bare count in the summary box and a
                  navigate-away link, despite covering 93% of all patients. */}
              <CoverSheetWidget
                title="Billing History" icon={Receipt}
                helpHintId="billing-outstanding"
                count={billingTxns.length}
                isEmpty={billingTxns.length === 0}
                emptyLabel="No billing history"
              
                onViewAll={patient?.id ? () => navigate(`/hospital/billing?patient_id=${patient.id}`) : undefined}>
                <div className="space-y-1.5">
                  {outstandingBalance > 0 && (
                    <div className="flex items-center justify-between rounded bg-amber-500/10 px-1.5 py-1 text-xs">
                      <span className="text-amber-700 dark:text-amber-400">Outstanding</span>
                      <span className="font-semibold text-amber-700 dark:text-amber-400">
                        ₦{outstandingBalance.toLocaleString()}
                      </span>
                    </div>
                  )}
                  {billingTxns.slice(0, 5).map((b: any) => (
                    <button
                      key={b.id}
                      onClick={() => setRecordDetail({
                        title: "Billing Transaction",
                        subtitle: b.bill_number,
                        rows: [
                          ["Bill number", b.bill_number],
                          ["Date", b.transaction_date ? fmtDate(b.transaction_date) : null],
                          ["Category", b.payment_category],
                          ["Mode", b.mode_of_payment],
                          ["Amount", b.amount != null ? `₦${Number(b.amount).toLocaleString()}` : null],
                          ["Total", b.total_amount != null ? `₦${Number(b.total_amount).toLocaleString()}` : null],
                          ["Paid", b.amount_paid != null ? `₦${Number(b.amount_paid).toLocaleString()}` : null],
                          ["Pending", b.amount_pending != null ? `₦${Number(b.amount_pending).toLocaleString()}` : null],
                          ["Discount", b.discount_amount != null ? `₦${Number(b.discount_amount).toLocaleString()}` : null],
                          ["Remark", b.remark],
                        ],
                      })}
                      className="flex w-full items-center justify-between gap-2 rounded px-1 -mx-1 py-0.5 text-left text-xs transition-colors hover:bg-muted/60"
                    >
                      <span className="min-w-0 truncate">{b.bill_number || "—"}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {b.total_amount != null ? `₦${Number(b.total_amount).toLocaleString()}` : fmtDate(b.transaction_date)}
                      </span>
                    </button>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Vouchers, discount requests and settlements carried over from
                  Hope — 78,672 voucher entries that had an endpoint but no
                  screen. Sits beside Billing History because it answers the
                  same question from the accounts side. */}
              <CoverSheetWidget
                title="Financial Ledger" icon={Landmark}
                count={ledgerCount}
                isLoading={ledgerLoading}
                isEmpty={ledgerCount === 0}
                emptyLabel="No ledger entries"
              >
                <div className="space-y-1.5">
                  {(ledger?.voucher_entries ?? []).slice(0, 5).map((v: any) => (
                    <button
                      key={`v-${v.id}`}
                      onClick={() => setRecordDetail({
                        title: v.narration || "Voucher entry",
                        subtitle: v.entry_date ? fmtDate(v.entry_date) : undefined,
                        icon: Landmark,
                        rows: [
                          ["Account", v.account_ref],
                          ["Debit", v.debit_amount ? `₦${Number(v.debit_amount).toLocaleString()}` : null],
                          ["Credit", v.credit_amount ? `₦${Number(v.credit_amount).toLocaleString()}` : null],
                          ["Type", v.entry_type],
                          ["Date", v.entry_date ? fmtDateTime(v.entry_date) : null],
                        ],
                      })}
                      className="flex w-full items-center justify-between gap-2 rounded px-1 -mx-1 py-0.5 text-left text-xs transition-colors hover:bg-muted/60"
                    >
                      <span className="min-w-0 truncate">{v.narration || v.entry_type || "Entry"}</span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        {v.debit_amount ? `₦${Number(v.debit_amount).toLocaleString()}` :
                         v.credit_amount ? `₦${Number(v.credit_amount).toLocaleString()}` : "—"}
                      </span>
                    </button>
                  ))}
                  {(ledger?.discount_requests ?? []).length > 0 && (
                    <p className="pt-1 text-xs text-muted-foreground">
                      {ledger.discount_requests.length} discount request
                      {ledger.discount_requests.length === 1 ? "" : "s"} on record
                    </p>
                  )}
                  {(ledger?.settlements ?? []).length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {ledger.settlements.length} settlement
                      {ledger.settlements.length === 1 ? "" : "s"}
                    </p>
                  )}
                </div>
              </CoverSheetWidget>


              {/* Ward stays — no patient-centric admission view existed at all;
                  royan_beds models live occupancy, not history. */}
              <CoverSheetWidget
                title="Ward Stays" icon={BedDouble}
                count={wardStays.length}
                isEmpty={wardStays.length === 0}
                emptyLabel="No inpatient stays"
              >
                <div className="space-y-1.5">
                  {wardStays.slice(0, 6).map((w: any) => (
                    <button
                      key={w.id}
                      onClick={() => setRecordDetail({
                        title: w.ward_name || "Ward stay",
                        subtitle: `${fmtDate(w.admitted_at)}${w.discharged_at ? ` → ${fmtDate(w.discharged_at)}` : " → current"}`,
                        icon: BedDouble,
                        badges: [
                          w.discharged_at
                            ? { label: "Discharged", tone: "default" as const }
                            : { label: "Currently admitted", tone: "success" as const },
                          ...(w.readmitted ? [{ label: "Readmission", tone: "warning" as const }] : []),
                        ],
                        rows: [
                          ["Ward", w.ward_name],
                          ["Room", w.room_name],
                          ["Bed", w.bed_label],
                          ["Admitted", w.admitted_at ? fmtDateTime(w.admitted_at) : null],
                          ["Discharged", w.discharged_at ? fmtDateTime(w.discharged_at) : "Still admitted"],
                          // Derived, not stored — royan_ward_stay_history has no
                          // length_of_stay column and the endpoint computes none.
                          ["Length of stay", lengthOfStay(w.admitted_at, w.discharged_at)],
                        ],
                      })}
                      className="flex w-full items-center justify-between gap-2 rounded px-1 -mx-1 py-0.5 text-left text-xs transition-colors hover:bg-muted/60"
                    >
                      <span className="min-w-0 truncate">
                        {w.ward_name || "Ward"}
                        {w.room_name ? ` · ${w.room_name}` : ""}
                        {w.bed_label ? ` · Bed ${w.bed_label}` : ""}
                      </span>
                      <span className="shrink-0 text-muted-foreground">
                        {fmtDate(w.admitted_at)}
                        {w.discharged_at ? ` → ${fmtDate(w.discharged_at)}` : " (current)"}
                      </span>
                    </button>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Documents — upload already worked, but nothing ever listed
                  them back. Hope's binary files were not migrated, so these are
                  index entries; is_migrated=false is surfaced honestly. */}
              <CoverSheetWidget
                title="Documents" icon={FileText}
                helpHintId="documents-index-only"
                count={patientDocs.length}
                isEmpty={patientDocs.length === 0}
                emptyLabel="No documents on file"
              >
                <div className="space-y-1.5">
                  {patientDocs.slice(0, 6).map((d: any) => (
                    <button
                      key={d.id}
                      onClick={() => setRecordDetail({
                        title: "Document",
                        subtitle: d.description || d.filename,
                        rows: [
                          ["Description", d.description],
                          ["Filename", d.filename],
                          ["Type", d.mime_type],
                          ["Size", d.size_bytes ? `${Math.round(d.size_bytes / 1024)} KB` : null],
                          ["Date", d.document_date ? fmtDate(d.document_date) : null],
                          ["Comment", d.comment],
                          ["File available", d.is_migrated ? "Yes" : "No — archived in the legacy system"],
                        ],
                      })}
                      className="flex w-full items-center justify-between gap-2 rounded px-1 -mx-1 py-0.5 text-left text-xs transition-colors hover:bg-muted/60"
                    >
                      <span className="min-w-0 truncate">{d.description || d.filename}</span>
                      <span className="shrink-0 text-muted-foreground">{fmtDate(d.document_date)}</span>
                    </button>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* Radiology reports — 41,536 reports across 29,621 patients were
                  reachable only by opening the Orders tab and clicking into a
                  detail dialog. Reported studies now surface on the cover sheet
                  with their impression, which is the line a doctor actually
                  wants at a glance. */}
              <CoverSheetWidget
                title="Radiology Reports" icon={ScanLine}
                helpHintId="history-starts-before-golive"
                count={reportedImaging.length}
                isEmpty={reportedImaging.length === 0}
                emptyLabel="No reported studies"
                onViewAll={reportedImaging.length > 6 ? () => setMainTab("orders") : undefined}
              >
                <div className="space-y-1.5">
                  {reportedImaging.slice(0, 6).map((r: any) => (
                    <button
                      key={r.id}
                      // Opens on the report tab — a radiology row is clicked to
                      // read the findings, not to inspect order metadata.
                      onClick={() => { setRadPanelOrder(r); setRadPanelTab("report"); }}
                      className="w-full rounded px-1 -mx-1 py-0.5 text-left text-xs transition-colors hover:bg-muted/60"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="min-w-0 truncate font-medium">{r.test_name || r.modality}</span>
                        <span className="shrink-0 text-muted-foreground">{fmtDate(r.reported_at)}</span>
                      </div>
                      {r.impression && (
                        <p className="truncate text-xs text-muted-foreground">{r.impression}</p>
                      )}
                    </button>
                  ))}
                </div>
              </CoverSheetWidget>

              {/* ICU nursing flowsheet — decoded from Hope's per-hour chart. */}
              <CoverSheetWidget
                title="Nursing Observations" icon={Activity}
                count={flowsheet.length}
                isEmpty={flowsheet.length === 0}
                emptyLabel="No flowsheet observations"
              >
                <div className="space-y-1.5">
                  {flowsheet.slice(0, 6).map((f: any) => (
                    <button
                      key={f.id}
                      onClick={() => setRecordDetail({
                        title: f.observation_name || "Observation",
                        subtitle: [f.category_name, f.sub_category_name].filter(Boolean).join(" · ") || undefined,
                        icon: Activity,
                        rows: [
                          ["Value", [f.value_text, f.unit].filter(Boolean).join(" ")],
                          ["Category", f.category_name],
                          ["Section", f.sub_category_name],
                          ["Recorded", f.observed_at ? fmtDateTime(f.observed_at) : (f.observed_date ?? null)],
                          ["Hour slot", f.hour_slot],
                          ["Recorded by", f.recorded_by],
                        ],
                      })}
                      className="flex w-full items-center justify-between gap-2 rounded px-1 -mx-1 py-0.5 text-left text-xs transition-colors hover:bg-muted/60"
                    >
                      <span className="min-w-0 truncate" title={f.sub_category_name || undefined}>
                        {f.observation_name}
                      </span>
                      <span className="shrink-0 font-medium">
                        {f.value_text}
                        {f.unit ? ` ${f.unit}` : ""}
                      </span>
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
              <RecordTable
                rows={problems}
                rowKey={(p: any) => p.id}
                emptyIcon={<ListChecks className="h-6 w-6" />}
                emptyLabel="No problems recorded"
                accent={(p: any) => (p.status === "active" ? "border-l-blue-500" : undefined)}
                onRowClick={(p: any) => setRecordDetail({
                  title: p.description,
                  subtitle: p.icd10_code ?? undefined,
                  icon: ListChecks,
                  badges: [{
                    label: p.status,
                    tone: p.status === "active" ? ("info" as const) : ("success" as const),
                  }],
                  rows: [
                    ["Status", p.status],
                    ["ICD-10", p.icd10_code],
                    ["Onset date", p.onset_date ? fmtDate(p.onset_date) : null],
                    ["Resolved date", p.resolved_date ? fmtDate(p.resolved_date) : null],
                  ],
                  blocks: [{ label: "Notes", text: p.notes }],
                })}
                columns={[
                  {
                    header: "Problem",
                    cell: (p: any) => <CellStack primary={p.description} secondary={p.icd10_code} mono />,
                  },
                  {
                    header: "Status",
                    width: "w-[110px]",
                    cell: (p: any) => (
                      <Badge variant="outline" className={cn("text-xs capitalize",
                        p.status === "active" ? "border-blue-500/30 text-blue-700 dark:text-blue-400 bg-blue-500/10" :
                        p.status === "resolved" ? "border-green-500/30 text-green-700 dark:text-green-400 bg-green-500/10" :
                        "border-slate-500/30 text-slate-700 dark:text-slate-400"
                      )}>{p.status}</Badge>
                    ),
                  },
                  { header: "Onset", width: "w-[110px]", className: "text-muted-foreground", cell: (p: any) => p.onset_date ? fmtDate(p.onset_date) : "—" },
                  { header: "Resolved", width: "w-[110px]", className: "text-muted-foreground", cell: (p: any) => p.resolved_date ? fmtDate(p.resolved_date) : "—" },
                  {
                    header: "",
                    width: "w-[50px]",
                    // stopPropagation so resolving does not also open the row
                    cell: (p: any) => p.status === "active" ? (
                      <Button
                        size="sm" variant="ghost"
                        className="h-7 px-2 text-xs text-green-600 hover:bg-green-500/10 hover:text-green-500"
                        onClick={(e) => { e.stopPropagation(); resolveProblemMut.mutate(p.id); }}
                        disabled={resolveProblemMut.isPending}
                        title="Mark resolved"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      </Button>
                    ) : null,
                  },
                ]}
              />
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
              <RecordTable
                rows={consents}
                rowKey={(c: any) => c.id}
                emptyIcon={<ShieldAlert className="h-6 w-6" />}
                emptyLabel="No consent records"
                // A refusal is the row a reader must not miss.
                accent={(c: any) => (c.consented ? undefined : "border-l-red-500")}
                onRowClick={(c: any) => setRecordDetail({
                  title: (c.consent_type ?? "Consent").replace(/_/g, " "),
                  subtitle: c.signed_at ? fmtDateTime(c.signed_at) : undefined,
                  icon: ShieldAlert,
                  badges: [c.consented
                    ? { label: "Consented", tone: "success" as const }
                    : { label: "Refused", tone: "danger" as const }],
                  rows: [
                    ["Decision", c.consented ? "Consented" : "Refused"],
                    ["Signed", c.signed_at ? fmtDateTime(c.signed_at) : null],
                    ["Captured by", c.captured_by],
                    ["Witness", c.witness_name],
                  ],
                  blocks: [{ label: "Notes", text: c.notes }],
                })}
                columns={[
                  {
                    header: "Type",
                    cell: (c: any) => (
                      <CellStack
                        primary={<span className="capitalize">{(c.consent_type ?? "Consent").replace(/_/g, " ")}</span>}
                        secondary={c.witness_name ? `Witness: ${c.witness_name}` : undefined}
                      />
                    ),
                  },
                  {
                    header: "Decision",
                    width: "w-[130px]",
                    cell: (c: any) => c.consented
                      ? <Badge variant="outline" className="gap-1 text-xs border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400"><CheckCircle2 className="h-2.5 w-2.5" />Consented</Badge>
                      : <Badge variant="outline" className="gap-1 text-xs border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400"><XCircle className="h-2.5 w-2.5" />Refused</Badge>,
                  },
                  { header: "Captured by", width: "w-[150px]", className: "text-muted-foreground", cell: (c: any) => c.captured_by ?? "—" },
                  { header: "Signed", width: "w-[150px]", className: "text-muted-foreground", cell: (c: any) => fmtDateTime(c.signed_at) },
                ]}
              />
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
                <RecordTable
                  rows={specialistNotes}
                  rowKey={(n: any, i: number) => n.id ?? i}
                  emptyLabel="No specialist notes"
                  accent={(n: any) => (n.amended_at ? "border-l-amber-500" : undefined)}
                  onRowClick={(n: any) => setRecordDetail({
                    title: `${(n.specialty ?? n.template_specialty ?? "Specialist").replace(/_/g, " ")} note`,
                    subtitle: `${fmtDateTime(n.noted_at)} · ${n.noted_by ?? "—"}`,
                    icon: Stethoscope,
                    badges: [
                      ...(n.amended_at ? [{ label: "Amended", tone: "warning" as const }] : []),
                      ...(n.icd10_codes ?? []).map((c: string) => ({ label: c, tone: "info" as const })),
                    ],
                    rows: [
                      ["Encounter", n.encounter_id],
                      ["Written by", n.noted_by],
                      ["Amended", n.amended_at ? fmtDateTime(n.amended_at) : null],
                    ],
                    sections: specialistNoteRows(n).length > 0
                      ? [{ label: "Full note", rows: specialistNoteRows(n) }]
                      : undefined,
                  })}
                  columns={[
                    {
                      header: "Specialty",
                      width: "w-[150px]",
                      cell: (n: any) => (
                        <Badge variant="outline" className="text-xs capitalize bg-indigo-500/10 border-indigo-500/30 text-indigo-700 dark:text-indigo-400">
                          {(n.specialty ?? n.template_specialty ?? "specialist").replace(/_/g, " ")}
                        </Badge>
                      ),
                    },
                    {
                      header: "Summary",
                      cell: (n: any) => {
                        const rows = specialistNoteRows(n);
                        return (
                          <CellStack
                            primary={<span className="line-clamp-2 font-normal">{rows.length > 0 ? String(rows[0][1]) : "—"}</span>}
                            secondary={n.icd10_codes?.length ? n.icd10_codes.join(" · ") : undefined}
                            mono
                          />
                        );
                      },
                    },
                    { header: "By", width: "w-[140px]", className: "text-muted-foreground", cell: (n: any) => n.noted_by ?? "—" },
                    {
                      header: "Amended",
                      width: "w-[110px]",
                      cell: (n: any) => n.amended_at
                        ? <Badge variant="outline" className="gap-1 text-xs border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400"><PenLine className="h-2.5 w-2.5" />Yes</Badge>
                        : <span className="text-muted-foreground">—</span>,
                    },
                    { header: "Date", width: "w-[150px]", className: "text-muted-foreground", cell: (n: any) => fmtDateTime(n.noted_at) },
                  ]}
                />
              )}
            </div>
          )}

          {/* ── Tab: Meds ── */}
          {mainTab === "meds" && (
            <div className="space-y-5">
              {/* Active and past are separate tables rather than one list with a
                  status column: "what is this patient on right now" is a
                  different question from "what have they had". */}
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Active Medications</h3>
                <RecordTable
                  rows={activeMeds}
                  rowKey={(rx: any) => rx.id}
                  emptyIcon={<Pill className="h-6 w-6" />}
                  emptyLabel="No active medications"
                  onRowClick={(rx: any) => setRecordDetail(rxRecordDetail(rx, isPlaceholderRecord(rx.drug_name, rx.external_source)))}
                  columns={MED_COLUMNS}
                />
              </div>

              {pastMeds.length > 0 && (
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Past Medications</h3>
                  <RecordTable
                    rows={pastMeds}
                    rowKey={(rx: any) => rx.id}
                    emptyLabel="No past medications"
                    onRowClick={(rx: any) => setRecordDetail(rxRecordDetail(rx, isPlaceholderRecord(rx.drug_name, rx.external_source)))}
                    columns={MED_COLUMNS}
                  />
                </div>
              )}
            </div>
          )}

          {/* ── Tab: Orders ──
              A row per order, matching the Laboratory worklist. The card list
              this replaced cost roughly three times the vertical space and made
              two orders hard to compare side by side. */}
          {mainTab === "orders" && (
            <div className="space-y-5">
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lab Orders</h3>
                <RecordTable
                  rows={data?.lab_orders ?? []}
                  rowKey={(o: any) => o.id}
                  emptyIcon={<FlaskConical className="h-6 w-6" />}
                  emptyLabel="No lab orders"
                  accent={(o: any) => URGENCY_ACCENT[o.urgency ?? "routine"]}
                  onRowClick={(o: any) => {
                    const noDetail = isPlaceholderRecord(o.test_name, o.external_source);
                    // A placeholder row carries no test name, so the full lab
                    // panel would open on nothing. Say why instead.
                    if (noDetail) {
                      setRecordDetail({
                        title: "Lab order",
                        subtitle: `Ordered ${fmtDateTime(o.ordered_at)}`,
                        rows: [
                          ["Status", o.status?.replace(/_/g, " ")],
                          ["Ordered by", formatAttribution(o.ordered_by)],
                        ],
                        blocks: [{
                          label: "Why there is no detail",
                          text: "This came across from the legacy system as a billing line only — no test name, sample or result was recorded against it there.",
                        }],
                      });
                    } else {
                      setLabPanelOrder(o);
                    }
                  }}
                  columns={[
                    {
                      header: "Test",
                      cell: (o: any) => {
                        const noDetail = isPlaceholderRecord(o.test_name, o.external_source);
                        return (
                          <CellStack
                            muted={noDetail}
                            primary={noDetail ? "No test detail captured" : o.test_name}
                            secondary={noDetail ? "Legacy record — only an internal catalog ID was kept" : undefined}
                          />
                        );
                      },
                    },
                    { header: "Result", cell: (o: any) => o.result_summary ?? <span className="text-muted-foreground">—</span> },
                    { header: "Urgency", width: "w-[90px]", cell: (o: any) => <Badge variant="outline" className="text-xs uppercase">{o.urgency ?? "—"}</Badge> },
                    { header: "Status", width: "w-[120px]", cell: (o: any) => <Badge variant="outline" className="text-xs capitalize">{o.status?.replace(/_/g, " ") ?? "—"}</Badge> },
                    { header: "Ordered", width: "w-[110px]", className: "text-muted-foreground", cell: (o: any) => fmtDate(o.ordered_at) },
                    { header: "", width: "w-[130px]", cell: (o: any) => (o.result_summary || ["resulted", "verified", "completed"].includes(o.status))
                        ? <ViewReportButton kind="lab" orderIds={[o.id]} variant="ghost" /> : null },
                  ]}
                />
              </div>

              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Imaging Orders</h3>
                <RecordTable
                  rows={radOrders}
                  rowKey={(o: any) => o.id}
                  emptyIcon={<ScanLine className="h-6 w-6" />}
                  emptyLabel="No imaging orders"
                  accent={(o: any) => URGENCY_ACCENT[o.urgency ?? "routine"]}
                  onRowClick={(o: any) => { setRadPanelOrder(o); setRadPanelTab(o.reported_at ? "report" : "detail"); }}
                  columns={[
                    {
                      header: "Study",
                      cell: (o: any) => (
                        <CellStack
                          primary={`${o.modality?.toUpperCase() ?? "Imaging"}${o.body_part ? ` — ${o.body_part}` : ""}`}
                          secondary={o.clinical_indication}
                        />
                      ),
                    },
                    { header: "Impression", cell: (o: any) => o.impression ?? <span className="text-muted-foreground">—</span> },
                    { header: "Status", width: "w-[120px]", cell: (o: any) => <Badge variant="outline" className="text-xs capitalize">{o.status?.replace(/_/g, " ") ?? "—"}</Badge> },
                    { header: "Ordered", width: "w-[110px]", className: "text-muted-foreground", cell: (o: any) => fmtDate(o.ordered_at) },
                    { header: "", width: "w-[130px]", cell: (o: any) => (o.report || o.impression || o.findings)
                        ? <ViewReportButton kind="scan" orderIds={[o.id]} variant="ghost" /> : null },
                  ]}
                />
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
              {/* One row per note. The soap parse below preserves the old
                  JSON-in-content convention for notes written before the
                  structured columns existed. */}
              <RecordTable
                rows={encNotes}
                rowKey={(n: any, i: number) => n.id ?? i}
                emptyIcon={<NotebookPen className="h-6 w-6" />}
                emptyLabel="No progress notes yet"
                accent={(n: any) => (n.signed_at ? undefined : "border-l-amber-500")}
                onRowClick={(n: any) => {
                  const soap = noteSoap(n);
                  setRecordDetail({
                    title: `${(n.note_type ?? "note").replace(/_/g, " ")} note`,
                    subtitle: `${fmtDateTime(n.created_at)} · ${n.author_name ?? "—"}`,
                    icon: NotebookPen,
                    badges: [
                      n.signed_at
                        ? { label: "Signed", tone: "success" as const }
                        : { label: "Unsigned", tone: "warning" as const },
                      ...(n.icd10_codes ?? []).map((c: string) => ({ label: c, tone: "info" as const })),
                    ],
                    blocks: soap
                      ? [
                          { label: "Subjective", text: soap.subjective },
                          { label: "Objective", text: soap.objective },
                          { label: "Assessment", text: soap.assessment },
                          { label: "Plan", text: soap.plan },
                        ]
                      : [{ label: "Note", text: n.content }],
                    sections: [{
                      label: "Attribution",
                      rows: [
                        ["Author", n.author_name],
                        ["Written", n.created_at ? fmtDateTime(n.created_at) : null],
                        ["Signed by", n.signed_by ? (n.signed_by_name ?? n.signed_by) : null],
                        ["Signed at", n.signed_at ? fmtDateTime(n.signed_at) : null],
                      ],
                    }],
                  });
                }}
                columns={[
                  {
                    header: "Type",
                    width: "w-[140px]",
                    cell: (n: any) => (
                      <Badge variant="outline" className="text-xs capitalize">
                        {(n.note_type ?? "note").replace(/_/g, " ")}
                      </Badge>
                    ),
                  },
                  {
                    header: "Assessment",
                    cell: (n: any) => {
                      const soap = noteSoap(n);
                      const preview = soap?.assessment || soap?.subjective || n.content || "";
                      return (
                        <CellStack
                          primary={<span className="line-clamp-2 font-normal">{preview || "—"}</span>}
                          secondary={n.icd10_codes?.length ? n.icd10_codes.join(" · ") : undefined}
                          mono
                        />
                      );
                    },
                  },
                  { header: "Author", width: "w-[150px]", className: "text-muted-foreground", cell: (n: any) => n.author_name ?? "—" },
                  {
                    header: "Signed",
                    width: "w-[130px]",
                    cell: (n: any) => n.signed_at
                      ? <Badge variant="outline" className="gap-1 text-xs border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400"><CheckCircle2 className="h-2.5 w-2.5" />Signed</Badge>
                      : <Badge variant="outline" className="text-xs border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400">Unsigned</Badge>,
                  },
                  { header: "Date", width: "w-[150px]", className: "text-muted-foreground", cell: (n: any) => fmtDateTime(n.created_at) },
                ]}
              />
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
                          <tr
                            key={o.id}
                            onClick={() => setLabPanelOrder(o)}
                            className={cn("border-b last:border-0 cursor-pointer hover:bg-muted/40 transition-colors", isAbnormal && "bg-red-50/50")}
                          >
                            <td className="px-3 py-2 font-medium">{o.test_name}</td>
                            <td className={cn("px-3 py-2 font-semibold", isAbnormal ? "text-red-700" : "text-green-700")}>
                              {o.result_summary ?? o.result_value ?? "—"}
                              {isAbnormal && <AlertTriangle className="inline ml-1 h-3 w-3 text-red-600" />}
                            </td>
                            <td className="px-3 py-2 text-xs text-muted-foreground">
                              {ref ? `${ref.normal_low ?? "?"}–${ref.normal_high ?? "?"} ${ref.unit ?? ""}` : o.reference_range ?? "—"}
                            </td>
                            <td className="px-3 py-2">
                              <Badge variant="outline" className="text-xs capitalize">{o.interpretation ?? "—"}</Badge>
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
                        <tr
                          key={c.id}
                          // The theatre panel renders the operative note,
                          // anaesthetic record and post-op notes as documents.
                          // They were previously crammed into value cells,
                          // which is where an operative note reads worst.
                          onClick={() => setTheatrePanelCase(c)}
                          className="border-b last:border-0 cursor-pointer hover:bg-muted/40 transition-colors"
                        >
                          <td className="px-3 py-2 font-medium">{c.procedure_name}</td>
                          <td className="px-3 py-2 text-muted-foreground">{c.theatre_name ?? "—"}</td>
                          <td className="px-3 py-2 text-muted-foreground">{c.surgeon_id ?? "—"}</td>
                          <td className="px-3 py-2">
                            <Badge variant="outline" className="text-xs capitalize">{c.urgency}</Badge>
                          </td>
                          <td className="px-3 py-2">
                            <Badge variant="outline" className="text-xs capitalize">{c.status?.replace(/_/g," ")}</Badge>
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
            <p className="text-xs text-muted-foreground -mt-1 pl-1">Open encounter first</p>
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
                className="w-full justify-start gap-2 border-green-500/30 text-green-700 dark:text-green-400 hover:bg-green-500/10"
                disabled={dischargeMut.isPending}
                onClick={() => setDischargeOpen(true)}
              >
                <UserCheck className="h-3.5 w-3.5" />
                Discharge
              </Button>
            </>
          )}
          {hasActiveEnc && data?.active_encounter?.status !== "billing_pending" && (
            <p className="text-xs text-muted-foreground pl-1">
              Discharge available once the consultation is over and every bill is paid (now: {encounterStatusLabel(data?.active_encounter?.status)})
            </p>
          )}

          <Separator className="my-2" />

          {/* Summary counts */}
          <div className="rounded-xl border border-border/50 bg-card p-3 space-y-2">
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Summary</p>
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
                  <span className="text-xs text-muted-foreground">{fmtDateTime(v.recorded_at)}</span>
                </div>
                <div className="grid grid-cols-3 gap-x-4 gap-y-2 text-xs">
                  {v.bp_systolic != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">BP</p>
                      <p className="font-semibold">{v.bp_systolic}/{v.bp_diastolic} <span className="font-normal text-muted-foreground">mmHg</span></p>
                    </div>
                  )}
                  {v.pulse != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">Pulse</p>
                      <p className="font-semibold">{v.pulse} <span className="font-normal text-muted-foreground">bpm</span></p>
                    </div>
                  )}
                  {v.temperature != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">Temp</p>
                      <p className="font-semibold">{v.temperature}<span className="font-normal text-muted-foreground">°C</span></p>
                    </div>
                  )}
                  {v.spo2 != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">SpO2</p>
                      <p className="font-semibold">{v.spo2}<span className="font-normal text-muted-foreground">%</span></p>
                    </div>
                  )}
                  {v.respiratory_rate != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">RR</p>
                      <p className="font-semibold">{v.respiratory_rate} <span className="font-normal text-muted-foreground">/min</span></p>
                    </div>
                  )}
                  {v.weight != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">Weight</p>
                      <p className="font-semibold">{v.weight} <span className="font-normal text-muted-foreground">kg</span></p>
                    </div>
                  )}
                  {v.height != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">Height</p>
                      <p className="font-semibold">{v.height} <span className="font-normal text-muted-foreground">cm</span></p>
                    </div>
                  )}
                  {v.bmi != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">BMI</p>
                      <p className="font-semibold">{v.bmi}</p>
                    </div>
                  )}
                  {v.gcs != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">GCS</p>
                      <p className="font-semibold">{v.gcs}<span className="font-normal text-muted-foreground">/15</span></p>
                    </div>
                  )}
                  {v.pain_score != null && (
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">Pain</p>
                      <p className="font-semibold">{v.pain_score}<span className="font-normal text-muted-foreground">/10</span></p>
                    </div>
                  )}
                </div>
                {v.notes && (
                  <p className="mt-2 text-xs text-muted-foreground italic border-t border-border/50 pt-1.5">"{v.notes}"</p>
                )}
                {v.recorded_by && (
                  <p className="mt-1 text-xs text-muted-foreground">Recorded by: {v.recorded_by}</p>
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
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Father's / Guardian's Name</Label>
                <Input
                  value={editPatientForm.father_name}
                  onChange={e => setEditPatientForm(f => ({ ...f, father_name: e.target.value }))}
                  placeholder="Full name"
                />
              </div>
              <div className="space-y-1">
                <Label>Place of Birth</Label>
                <Input
                  value={editPatientForm.place_of_birth}
                  onChange={e => setEditPatientForm(f => ({ ...f, place_of_birth: e.target.value }))}
                  placeholder="e.g. Royan Hospital"
                />
              </div>
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

      {/* ── Record detail (shared by every clickable row on this page) ──
          A workspace panel, not a centred dialog: it carries the patient
          identity, groups sections, and gives clinical prose full width. */}
      <RecordDetailPanel
        detail={recordDetail}
        onClose={() => { setRecordDetail(null); returnToStory(); }}
        patientName={patient ? `${patient.first_name} ${patient.last_name}` : undefined}
      />

      {labPanelOrder && (
        <LabWorkspacePanel
          order={{
            ...labPanelOrder,
            patient_id: labPanelOrder.patient_id ?? patient?.id,
            patient_mrn: labPanelOrder.patient_mrn ?? patient?.mrn,
            patient_name: labPanelOrder.patient_name ?? (patient ? `${patient.first_name} ${patient.last_name}` : undefined),
          }}
          initialTab={labPanelOrder.result_summary || labPanelOrder.result_value ? "result" : "detail"}
          onClose={() => { setLabPanelOrder(null); returnToStory(); }}
        />
      )}

      {radPanelOrder && (
        <RadiologyWorkspacePanel
          order={{
            ...radPanelOrder,
            patient_id: radPanelOrder.patient_id ?? patient?.id,
            patient_mrn: radPanelOrder.patient_mrn ?? patient?.mrn,
            patient_name: radPanelOrder.patient_name ?? (patient ? `${patient.first_name} ${patient.last_name}` : undefined),
          }}
          initialTab={radPanelTab}
          onClose={() => { setRadPanelOrder(null); setRadPanelTab(undefined); returnToStory(); }}
        />
      )}

      {theatrePanelCase && (
        <TheatreWorkspacePanel
          case={{
            ...theatrePanelCase,
            patient_id: theatrePanelCase.patient_id ?? patient?.id,
            patient_name: theatrePanelCase.patient_name ?? (patient ? `${patient.first_name} ${patient.last_name}` : undefined),
          }}
          onClose={() => { setTheatrePanelCase(null); returnToStory(); }}
        />
      )}

      {/* ── Encounter Story (full chronological detail for a visit) ────── */}
      {storyEncounterId && !labPanelOrder && !radPanelOrder && !theatrePanelCase && !recordDetail && (
        <EncounterStoryPanel
          encounterId={storyEncounterId}
          patientName={fullName}
          onClose={() => { setStoryEncounterId(null); setStoryReturnId(null); }}
          onOpenRecord={openStoryRecord}
        />
      )}

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
                onChange={e => { setRxForm(f => ({ ...f, drug_name: e.target.value })); setDrugSearch(e.target.value); }}
                placeholder="e.g. Amoxicillin 500mg"
              />
              {drugResults.length > 0 && (
                <div className="rounded-md border max-h-28 overflow-y-auto">
                  {drugResults.map((d: any) => (
                    <button key={d.id} type="button" className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted"
                      onClick={() => { setRxForm(f => ({
                        ...f,
                        drug_name: `${d.generic_name}${d.strength ? " " + d.strength : ""}`,
                        dosage: f.dosage || (d.strength ?? ""),
                        route: f.route || (Array.isArray(d.route) && d.route.length === 1 ? d.route[0] : ""),
                      })); setDrugSearch(""); }}>
                      {d.generic_name} {d.strength}{d.unit} {d.brand_name ? `(${d.brand_name})` : ""}
                    </button>
                  ))}
                </div>
              )}
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
                    {FREQUENCY_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Duration</Label>
                <Select value={rxForm.duration} onValueChange={v => setRxForm(f => ({ ...f, duration: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
                  <SelectContent>
                    {DURATION_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Route</Label>
                <Select value={rxForm.route} onValueChange={v => setRxForm(f => ({ ...f, route: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROUTE_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
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
              onClick={() => rxMut.mutate(false)}
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
            <DialogTitle className="flex items-center gap-2 text-red-700 dark:text-red-400">
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

      {/* ── Add Progress Note Dialog (doctor-only) ──────────────────────
          Uses the SAME SoapNoteComposer as the OPD panel. This page used to
          carry a second, divergent note UI — four free-text SOAP boxes and a
          comma-separated ICD-10 field — writing a different shape to the same
          endpoint. The composer is container-agnostic (renders no dialog of
          its own, invalidates nothing), so this Dialog stays the container and
          invalidation stays here via onSigned. */}
      <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <NotebookPen className="h-4 w-4" /> Add Progress Note
            </DialogTitle>
            <DialogDescription>
              {fullName} — {data?.active_encounter ? `Encounter #${data.active_encounter.id}` : "No active encounter"}
            </DialogDescription>
          </DialogHeader>

          {data?.active_encounter ? (
            <SoapNoteComposer
              encounterId={data.active_encounter.id}
              patientId={patientNumId ?? undefined}
              patientSex={patient?.gender}
              patientName={fullName}
              patientMeta={[patient?.gender, mrn && `MRN ${mrn}`].filter(Boolean).join(" · ")}
              allergies={patient?.allergies}
              bloodGroup={patient?.blood_group}
              genotype={patient?.genotype}
              onSigned={() => {
                setNoteOpen(false);
                void qc.invalidateQueries({ queryKey: ["patient-profile", mrn] });
              }}
            />
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground">
              A clinical note must belong to an encounter. Start an encounter for this patient first.
            </p>
          )}
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
