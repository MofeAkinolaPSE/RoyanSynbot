import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/AuthProvider";
import { RoleDetailsForm } from "@/components/RoleDetailsForm";
import {
  Stethoscope, Pill, FlaskConical, ShieldCheck, LayoutDashboard,
  ClipboardList, TestTube, Microscope, Users, ChevronRight, ChevronLeft, Check, X
} from "lucide-react";

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

// ── Designation options per role (Select, with "Other" for anything unlisted) ─
const DESIGNATION_OPTIONS: Record<string, string[]> = {
  doctor: ["Consultant Physician", "Senior Registrar", "Registrar", "Resident Doctor", "House Officer", "Medical Officer", "General Practitioner"],
  nurse: ["Staff Nurse", "Senior Nurse", "Nurse Manager", "Ward Sister", "Nurse Practitioner"],
  pharmacist: ["Pharmacist", "Chief Pharmacist", "Pharmacy Technician"],
  lab: ["Lab Technician", "Medical Laboratory Scientist", "Chief Lab Scientist"],
  radiology: ["Radiographer", "Chief Radiographer", "Sonographer"],
  admin: ["System Administrator", "Administrative Officer", "Front Desk Officer", "HR Officer", "Operations Manager"],
  management: ["Hospital Administrator", "Medical Director", "Operations Director", "Chief Executive Officer"],
};
const OTHER_DESIGNATION = "__other__";

// ── Main wizard ───────────────────────────────────────────────────────────────
interface ProfileSetupProps {
  initialData?: Record<string, any>;
  onComplete: () => void;
}

const ProfileSetup = ({ initialData, onComplete }: ProfileSetupProps) => {
  const { roles } = useAuth();
  const primaryRole = roles.find((r) => GUIDE_CARDS[r]) ?? "admin";

  const { data: departmentsData } = useQuery({
    queryKey: ["mdm-departments"],
    queryFn: () => api.mdm.departments(),
    staleTime: 5 * 60 * 1000,
  });
  const departments = departmentsData?.records ?? [];

  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const designationOptions = DESIGNATION_OPTIONS[primaryRole] ?? [];

  // Step 1: identity
  const [identity, setIdentity] = useState({
    full_name: initialData?.full_name || "",
    department: initialData?.department || "",
    designation: initialData?.designation || "",
  });
  // If the existing designation isn't one of this role's preset options,
  // start in "type your own" mode so we don't silently blank out saved data.
  const [useCustomDesignation, setUseCustomDesignation] = useState(
    () => !!identity.designation && !designationOptions.includes(identity.designation),
  );

  // Step 2: role-specific metadata
  const [roleDetails, setRoleDetails] = useState<Record<string, string>>({});

  const guideCards = GUIDE_CARDS[primaryRole] ?? GUIDE_CARDS.admin;
  const TOTAL_STEPS = 3;

  const handleNext = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS));
  const handleBack = () => setStep((s) => Math.max(s - 1, 1));

  // Most accounts get their royan_staff row created at admin-approval time (see
  // the public registration + admin approval flow) — but a few legacy paths
  // (the seed admin, or accounts an admin creates directly) can reach here with
  // no staff row yet. Create it first in that case, then always patch in
  // whatever's been filled on this screen.
  const ensureStaffRowExists = async () => {
    if (initialData) return;
    await api.staff.ensureProfile({
      full_name: identity.full_name || undefined,
      department: identity.department || undefined,
      designation: identity.designation || undefined,
    });
  };

  const handleFinish = async () => {
    setSaving(true);
    setError(null);
    try {
      await ensureStaffRowExists();
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

  const handleDismiss = async () => {
    setSaving(true);
    setError(null);
    try {
      await ensureStaffRowExists();
      await api.staff.updateProfile({ metadata: { profile_complete: true } });
      onComplete();
    } catch (e: any) {
      setError(e?.message || "Could not dismiss this — please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl bg-background p-8 shadow-2xl">
        <button
          type="button"
          onClick={handleDismiss}
          disabled={saving}
          aria-label="Don't show this again"
          title="Don't show this again"
          className="absolute right-4 top-4 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          <X className="h-4 w-4" />
        </button>

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
            <h2 className="mb-1 text-xl font-semibold">Welcome to RoyanHealth</h2>
            <p className="mb-6 text-sm text-muted-foreground">Let's confirm your details so Roy knows exactly who it's working with.</p>
            <div className="space-y-4">
              <div>
                <Label>Full Name</Label>
                <Input value={identity.full_name} onChange={(e) => setIdentity({ ...identity, full_name: e.target.value })} placeholder="e.g. Sarah Ahmed" />
              </div>
              <div>
                <Label>Department *</Label>
                <Select value={identity.department} onValueChange={(v) => setIdentity({ ...identity, department: v })}>
                  <SelectTrigger><SelectValue placeholder="Select your department" /></SelectTrigger>
                  <SelectContent>
                    {departments.map((d) => (
                      <SelectItem key={d.id} value={d.name}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Designation / Job Title</Label>
                {useCustomDesignation ? (
                  <div className="flex gap-2">
                    <Input
                      autoFocus
                      value={identity.designation}
                      onChange={(e) => setIdentity({ ...identity, designation: e.target.value })}
                      placeholder="e.g. Consultant Physician"
                    />
                    {designationOptions.length > 0 && (
                      <Button type="button" variant="ghost" size="sm" onClick={() => setUseCustomDesignation(false)}>
                        Choose from list
                      </Button>
                    )}
                  </div>
                ) : (
                  <Select
                    value={identity.designation}
                    onValueChange={(v) => {
                      if (v === OTHER_DESIGNATION) {
                        setUseCustomDesignation(true);
                        setIdentity({ ...identity, designation: "" });
                      } else {
                        setIdentity({ ...identity, designation: v });
                      }
                    }}
                  >
                    <SelectTrigger><SelectValue placeholder="Select your designation" /></SelectTrigger>
                    <SelectContent>
                      {designationOptions.map((d) => (
                        <SelectItem key={d} value={d}>{d}</SelectItem>
                      ))}
                      <SelectItem value={OTHER_DESIGNATION}>Other (type my own)</SelectItem>
                    </SelectContent>
                  </Select>
                )}
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
            <p className="mb-4 text-sm text-muted-foreground">Here are the key areas of RoyanHealth for your role.</p>
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
            <Button onClick={handleNext} disabled={step === 1 && (!identity.full_name.trim() || !identity.department.trim())}>
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
