import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/AuthProvider";
import {
  Stethoscope, Pill, FlaskConical, ShieldCheck, LayoutDashboard,
  ClipboardList, TestTube, Microscope, Users, ChevronRight, ChevronLeft, Check
} from "lucide-react";

// ── Role-specific step 2 form config ─────────────────────────────────────────
const SPECIALTIES = [
  "Cardiology", "Internal Medicine", "Pediatrics", "General Surgery",
  "Obstetrics & Gynaecology", "Orthopaedics", "Ophthalmology", "ENT",
  "Dermatology", "Psychiatry", "Neurology", "Urology", "Radiology",
  "Anaesthesia", "Family Medicine", "Emergency Medicine", "Pathology", "Other",
];
const PHARMACY_SPECIALIZATIONS = ["Clinical Pharmacy", "Hospital Pharmacy", "Community Pharmacy", "Oncology Pharmacy"];
const NURSING_SPECIALIZATIONS = ["General Nursing", "ICU/Critical Care", "Perioperative", "Paediatric", "Obstetric", "Emergency"];
const LAB_SECTIONS = ["Haematology", "Biochemistry", "Microbiology", "Histopathology", "Blood Bank", "Radiology", "MRI/CT", "Ultrasound"];
const ADMIN_TITLES = ["Hospital Director", "Chief Medical Officer", "Chief Nursing Officer", "CFO", "COO", "HR Manager", "Operations Manager", "Quality Manager", "Other"];

// ── Beginner guide cards per role ─────────────────────────────────────────────
type GuideCard = { icon: JSX.Element; title: string; description: string };

const GUIDE_CARDS: Record<string, GuideCard[]> = {
  doctor: [
    { icon: <ClipboardList className="h-6 w-6" />, title: "Clinical Queue", description: "View patients waiting to be seen, manage triage and consult flow." },
    { icon: <Stethoscope className="h-6 w-6" />, title: "Patient Chart", description: "Open a patient's full clinical history, vitals, allergies, and prior encounters." },
    { icon: <TestTube className="h-6 w-6" />, title: "Lab Orders", description: "Request investigations and review pending or completed lab results." },
    { icon: <Pill className="h-6 w-6" />, title: "Prescriptions", description: "Write, review, and track prescriptions sent to pharmacy." },
    { icon: <Stethoscope className="h-6 w-6" />, title: "DocRoy", description: "Ask Roy anything — patient context, lab interpretation, clinical actions." },
  ],
  nurse: [
    { icon: <LayoutDashboard className="h-6 w-6" />, title: "Ward View", description: "Monitor bed occupancy, patient assignments, and ward alerts in real time." },
    { icon: <ClipboardList className="h-6 w-6" />, title: "Vitals Entry", description: "Record and review patient vitals, nursing notes, and care observations." },
    { icon: <ClipboardList className="h-6 w-6" />, title: "Nursing Notes", description: "Document nursing care, handover notes, and patient progress." },
    { icon: <Stethoscope className="h-6 w-6" />, title: "NurseRoy", description: "Ask Roy about ward status, patient care plans, or critical flags." },
  ],
  pharmacist: [
    { icon: <Pill className="h-6 w-6" />, title: "Prescription Queue", description: "View prescriptions awaiting dispensing, verify drug details." },
    { icon: <FlaskConical className="h-6 w-6" />, title: "Drug Stock", description: "Check drug inventory levels, reorder alerts, and expiry tracking." },
    { icon: <ClipboardList className="h-6 w-6" />, title: "Dispensing Log", description: "Record and audit dispensed medications per patient encounter." },
    { icon: <Pill className="h-6 w-6" />, title: "PharmRoy", description: "Ask Roy about pending prescriptions, stock levels, or drug interactions." },
  ],
  lab: [
    { icon: <Microscope className="h-6 w-6" />, title: "Test Orders", description: "View all pending lab orders, prioritise urgent samples." },
    { icon: <TestTube className="h-6 w-6" />, title: "Result Entry", description: "Enter and validate lab results for pending orders." },
    { icon: <ClipboardList className="h-6 w-6" />, title: "Pending Reviews", description: "Track overdue results and critical value alerts." },
    { icon: <Microscope className="h-6 w-6" />, title: "LabRoy", description: "Ask Roy about TAT performance, pending orders, or result status." },
  ],
  radiology: [
    { icon: <Microscope className="h-6 w-6" />, title: "Imaging Worklist", description: "View pending imaging requests and radiology queue." },
    { icon: <TestTube className="h-6 w-6" />, title: "Report Entry", description: "Submit radiology reports and findings for ordered studies." },
    { icon: <ClipboardList className="h-6 w-6" />, title: "Pending Reviews", description: "Track unreported studies and urgent imaging flags." },
    { icon: <Microscope className="h-6 w-6" />, title: "LabRoy", description: "Ask Roy about radiology worklist status or pending reports." },
  ],
  admin: [
    { icon: <LayoutDashboard className="h-6 w-6" />, title: "Hospital Dashboard", description: "Live overview of patient flow, bed occupancy, and daily ops." },
    { icon: <Users className="h-6 w-6" />, title: "HR & Staff", description: "Manage staff records, shifts, timesheets, and payroll summaries." },
    { icon: <ClipboardList className="h-6 w-6" />, title: "Billing & HMO", description: "Track patient bills, HMO claims, and revenue reconciliation." },
    { icon: <ShieldCheck className="h-6 w-6" />, title: "Reports", description: "Generate compliance, audit, financial, and executive reports." },
    { icon: <Stethoscope className="h-6 w-6" />, title: "AdminRoy", description: "Ask Roy anything about operations, HR, billing, or hospital metrics." },
  ],
  management: [
    { icon: <LayoutDashboard className="h-6 w-6" />, title: "Executive Dashboard", description: "High-level hospital performance — revenue, patient flow, KPIs." },
    { icon: <ClipboardList className="h-6 w-6" />, title: "Reports", description: "On-demand executive summaries, board reports, and compliance docs." },
    { icon: <ShieldCheck className="h-6 w-6" />, title: "Risk & Compliance", description: "Monitor clinical risk signals, audit status, and regulatory flags." },
    { icon: <Stethoscope className="h-6 w-6" />, title: "AdminRoy", description: "Ask Roy about any metric, trend, or operational concern." },
  ],
};

// ── Step 2: role-specific profile details ────────────────────────────────────
function RoleDetailsForm({ role, value, onChange }: { role: string; value: Record<string, string>; onChange: (v: Record<string, string>) => void }) {
  const set = (k: string, v: string) => onChange({ ...value, [k]: v });

  if (role === "doctor") return (
    <div className="space-y-4">
      <div>
        <Label>Medical Specialty</Label>
        <Select value={value.specialty || ""} onValueChange={(v) => set("specialty", v)}>
          <SelectTrigger><SelectValue placeholder="Select specialty" /></SelectTrigger>
          <SelectContent>{SPECIALTIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div>
        <Label>Medical Council Number</Label>
        <Input placeholder="e.g. MDCN-12345" value={value.medical_council_number || ""} onChange={(e) => set("medical_council_number", e.target.value)} />
      </div>
      <div>
        <Label>Years of Experience</Label>
        <Input type="number" min={0} max={60} placeholder="e.g. 8" value={value.years_experience || ""} onChange={(e) => set("years_experience", e.target.value)} />
      </div>
    </div>
  );

  if (role === "pharmacist") return (
    <div className="space-y-4">
      <div>
        <Label>Pharmacy Council License No.</Label>
        <Input placeholder="e.g. PCN-54321" value={value.medical_council_number || ""} onChange={(e) => set("medical_council_number", e.target.value)} />
      </div>
      <div>
        <Label>Specialization</Label>
        <Select value={value.specialty || ""} onValueChange={(v) => set("specialty", v)}>
          <SelectTrigger><SelectValue placeholder="Select specialization" /></SelectTrigger>
          <SelectContent>{PHARMACY_SPECIALIZATIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      </div>
    </div>
  );

  if (role === "nurse") return (
    <div className="space-y-4">
      <div>
        <Label>Nursing Specialization</Label>
        <Select value={value.specialty || ""} onValueChange={(v) => set("specialty", v)}>
          <SelectTrigger><SelectValue placeholder="Select specialization" /></SelectTrigger>
          <SelectContent>{NURSING_SPECIALIZATIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div>
        <Label>Nursing Council Number (optional)</Label>
        <Input placeholder="e.g. NMCN-00001" value={value.medical_council_number || ""} onChange={(e) => set("medical_council_number", e.target.value)} />
      </div>
    </div>
  );

  if (role === "lab" || role === "radiology") return (
    <div className="space-y-4">
      <div>
        <Label>Lab / Radiology Section</Label>
        <Select value={value.specialty || ""} onValueChange={(v) => set("specialty", v)}>
          <SelectTrigger><SelectValue placeholder="Select section" /></SelectTrigger>
          <SelectContent>{LAB_SECTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div>
        <Label>Registration Number (optional)</Label>
        <Input placeholder="e.g. MLSCN-99999" value={value.medical_council_number || ""} onChange={(e) => set("medical_council_number", e.target.value)} />
      </div>
    </div>
  );

  // Admin / management
  return (
    <div className="space-y-4">
      <div>
        <Label>Administrative Title</Label>
        <Select value={value.specialty || ""} onValueChange={(v) => set("specialty", v)}>
          <SelectTrigger><SelectValue placeholder="Select title" /></SelectTrigger>
          <SelectContent>{ADMIN_TITLES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      </div>
    </div>
  );
}

// ── Main wizard ───────────────────────────────────────────────────────────────
interface ProfileSetupProps {
  initialData?: Record<string, any>;
  onComplete: () => void;
}

const ProfileSetup = ({ initialData, onComplete }: ProfileSetupProps) => {
  const { roles } = useAuth();
  const primaryRole = roles.find((r) => GUIDE_CARDS[r]) ?? "admin";

  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1: identity
  const [identity, setIdentity] = useState({
    full_name: initialData?.full_name || "",
    department: initialData?.department || "",
    designation: initialData?.designation || "",
  });

  // Step 2: role-specific metadata
  const [roleDetails, setRoleDetails] = useState<Record<string, string>>({});

  const guideCards = GUIDE_CARDS[primaryRole] ?? GUIDE_CARDS.admin;
  const TOTAL_STEPS = 3;

  const handleNext = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS));
  const handleBack = () => setStep((s) => Math.max(s - 1, 1));

  const handleFinish = async () => {
    setSaving(true);
    setError(null);
    try {
      // If no staff record exists yet, self-register first
      const meResp = await api.staff.getMe();
      if (!meResp.data) {
        await api.staff.register({
          full_name: identity.full_name,
          department: identity.department,
          designation: identity.designation,
        });
      }
      // Patch full profile + metadata
      await api.staff.updateProfile({
        full_name: identity.full_name || undefined,
        department: identity.department || undefined,
        designation: identity.designation || undefined,
        metadata: {
          ...roleDetails,
          profile_complete: true,
        },
      });
      onComplete();
    } catch (e: any) {
      setError(e?.message || "Failed to save profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl bg-background p-8 shadow-2xl">
        {/* Progress dots */}
        <div className="mb-6 flex justify-center gap-2">
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <div
              key={i}
              className={`h-2 rounded-full transition-all ${i + 1 === step ? "w-8 bg-primary" : i + 1 < step ? "w-2 bg-primary/60" : "w-2 bg-muted"}`}
            />
          ))}
        </div>

        {/* ── Step 1: Identity ── */}
        {step === 1 && (
          <div>
            <h2 className="mb-1 text-xl font-semibold">Welcome to Synbot Health</h2>
            <p className="mb-6 text-sm text-muted-foreground">Let's confirm your details so Roy knows exactly who it's working with.</p>
            <div className="space-y-4">
              <div>
                <Label>Full Name</Label>
                <Input value={identity.full_name} onChange={(e) => setIdentity({ ...identity, full_name: e.target.value })} placeholder="e.g. Sarah Ahmed" />
              </div>
              <div>
                <Label>Department</Label>
                <Input value={identity.department} onChange={(e) => setIdentity({ ...identity, department: e.target.value })} placeholder="e.g. Internal Medicine" />
              </div>
              <div>
                <Label>Designation / Job Title</Label>
                <Input value={identity.designation} onChange={(e) => setIdentity({ ...identity, designation: e.target.value })} placeholder="e.g. Consultant Physician" />
              </div>
            </div>
          </div>
        )}

        {/* ── Step 2: Role-specific details ── */}
        {step === 2 && (
          <div>
            <h2 className="mb-1 text-xl font-semibold">Professional Details</h2>
            <p className="mb-6 text-sm text-muted-foreground">This helps Roy give you accurate, role-specific assistance.</p>
            <RoleDetailsForm role={primaryRole} value={roleDetails} onChange={setRoleDetails} />
          </div>
        )}

        {/* ── Step 3: Beginner guide ── */}
        {step === 3 && (
          <div>
            <h2 className="mb-1 text-xl font-semibold">Your Quick-Start Guide</h2>
            <p className="mb-4 text-sm text-muted-foreground">Here are the key areas of Synbot Health for your role.</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {guideCards.map((card) => (
                <div key={card.title} className="flex items-start gap-3 rounded-xl border border-border/50 bg-muted/20 p-3">
                  <div className="mt-0.5 text-primary">{card.icon}</div>
                  <div>
                    <p className="text-sm font-medium">{card.title}</p>
                    <p className="text-xs text-muted-foreground">{card.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

        {/* Navigation */}
        <div className="mt-6 flex items-center justify-between">
          <Button variant="ghost" onClick={handleBack} disabled={step === 1}>
            <ChevronLeft className="mr-1 h-4 w-4" /> Back
          </Button>
          {step < TOTAL_STEPS ? (
            <Button onClick={handleNext} disabled={step === 1 && !identity.full_name.trim()}>
              Next <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          ) : (
            <Button onClick={handleFinish} disabled={saving}>
              {saving ? "Saving…" : <><Check className="mr-1 h-4 w-4" /> Finish</>}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProfileSetup;
