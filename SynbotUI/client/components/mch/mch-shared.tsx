import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
export { SectionLabel } from "@/components/shared/panel-shared";
// Re-exported so existing call sites keep their import path.
export { DetailRow } from "@/components/shared/panel-shared";

// Blank date/text inputs in these forms default to "", not undefined — sent
// as-is, an empty string in a date column ('') fails at the DB (Postgres
// rejects it for `date`, unlike NULL). Strip before every mutationFn call.
export function stripEmptyStrings<T extends Record<string, any>>(obj: T): Partial<T> {
  const out: Partial<T> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v !== "") (out as any)[k] = v;
  }
  return out;
}

export const ANC_STATUS_COLORS: Record<string, string> = {
  active:      "bg-green-100 text-green-700 border-green-300",
  delivered:   "bg-blue-100 text-blue-700 border-blue-300",
  miscarriage: "bg-red-100 text-red-700 border-red-300",
  referred:    "bg-orange-100 text-orange-700 border-orange-300",
};

export const DELIVERY_MODE_COLORS: Record<string, string> = {
  svd:      "bg-green-100 text-green-700 border-green-300",
  assisted: "bg-yellow-100 text-yellow-700 border-yellow-300",
  cs:       "bg-sky-100 text-sky-700 border-sky-300",
  breech:   "bg-orange-100 text-orange-700 border-orange-300",
};

export function ANCStatusBadge({ status }: { status?: string }) {
  const s = status ?? "active";
  return (
    <Badge variant="outline" className={cn("text-xs capitalize", ANC_STATUS_COLORS[s] || "")}>
      {s}
    </Badge>
  );
}

export function BoolCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <div
        onClick={() => onChange(!checked)}
        className={cn(
          "w-4 h-4 rounded border flex items-center justify-center cursor-pointer transition-colors flex-shrink-0",
          checked ? "bg-green-100 border-green-500" : "border-border hover:border-ring"
        )}
      >
        {checked && <span className="w-2 h-2 rounded-full bg-green-600" />}
      </div>
      <span className="text-xs text-muted-foreground">{label}</span>
    </label>
  );
}

export const emptyAnc = {
  patient_id: "", encounter_id: "", gravida: "", para: "",
  lmp: "", edd: "", gestational_age_weeks: "",
  blood_group: "", rhesus: "positive",
  hiv_status: "unknown", hbsag: "unknown", syphilis: "unknown",
  malaria_prophylaxis: false, tetanus_toxoid: false, iron_folic_acid: false,
  risk_factors: "", referred_from: "", notes: "",
};

export const emptyVisit = {
  visit_date: "", gestational_age_weeks: "", weight_kg: "",
  bp_systolic: "", bp_diastolic: "", fundal_height_cm: "",
  fetal_heart_rate: "", presentation: "", engagement: "",
  oedema: false, proteinuria: false, haemoglobin: "",
  malaria_rapid_test: "", drugs_given: "", counselling_given: "",
  next_visit_date: "", clinician_id: "", notes: "",
};

export const emptyDelivery = {
  delivery_date: "", delivery_time: "",
  mode_of_delivery: "svd", indication: "",
  duration_of_labour_hours: "", blood_loss_ml: "",
  placenta_complete: true, perineal_tear: "", episiotomy: false,
  maternal_complications: "", anaesthesia_type: "", attending_clinician: "", notes: "",
};

export const emptyNewborn = {
  sex: "male", birth_weight_kg: "", length_cm: "", head_circumference_cm: "",
  apgar_1min: "", apgar_5min: "", apgar_10min: "",
  gestational_age_at_birth: "",
  cry_at_birth: true, resuscitation_needed: false, resuscitation_type: "",
  congenital_anomalies: "",
  eye_prophylaxis: false, vitamin_k_given: false, bcg_given: false,
  opv0_given: false, hbv_given: false,
  breast_feeding_initiated: true, notes: "",
  father_name: "", place_of_birth: "",
};
