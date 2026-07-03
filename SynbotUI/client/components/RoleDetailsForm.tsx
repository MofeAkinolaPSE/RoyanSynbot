import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// ── Role-specific form config ─────────────────────────────────────────────────
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

// ── Role-specific KYC/profile details form ────────────────────────────────────
// Shared between ProfileSetup.tsx (existing-account onboarding) and Register.tsx
// (public self-service registration) so per-role field definitions live in one place.
export function RoleDetailsForm({ role, value, onChange }: { role: string; value: Record<string, string>; onChange: (v: Record<string, string>) => void }) {
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

  // Admin / management / other roles without a dedicated KYC field set
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
