export const FREQUENCY_OPTIONS = [
  { value: "once daily", label: "Once daily" },
  { value: "twice daily", label: "Twice daily" },
  { value: "three times daily", label: "Three times daily" },
  { value: "four times daily", label: "Four times daily" },
  { value: "every 8 hours", label: "Every 8 hours" },
  { value: "every 6 hours", label: "Every 6 hours" },
  { value: "every 12 hours", label: "Every 12 hours" },
  { value: "as needed", label: "As needed (PRN)" },
  { value: "stat", label: "Stat (immediately)" },
];

export const ROUTE_OPTIONS = [
  { value: "oral", label: "Oral" },
  { value: "iv", label: "IV" },
  { value: "im", label: "IM" },
  { value: "sc", label: "SC" },
  { value: "topical", label: "Topical" },
  { value: "inhaled", label: "Inhaled" },
  { value: "rectal", label: "Rectal" },
  { value: "sublingual", label: "Sublingual" },
];

/**
 * Duration, unit and dose form were free text in all three prescribing UIs
 * while drug name and frequency were pickers — an inconsistency that produced
 * "5/7", "5 days", "five days" and "5d" for the same instruction.
 *
 * Free text is still allowed alongside these (see DURATION_OPTIONS usage): the
 * lists cover the common cases, not every case, and blocking an unusual course
 * length would be worse than the inconsistency.
 */
export const DURATION_OPTIONS = [
  { value: "3 days", label: "3 days" },
  { value: "5 days", label: "5 days" },
  { value: "7 days", label: "7 days" },
  { value: "10 days", label: "10 days" },
  { value: "14 days", label: "14 days" },
  { value: "1 month", label: "1 month" },
  { value: "3 months", label: "3 months" },
  { value: "ongoing", label: "Ongoing / repeat" },
  { value: "single dose", label: "Single dose" },
];

/** Dispensing units. Mirrors royan_drug_formulary.unit. */
export const UNIT_OPTIONS = [
  { value: "tablet", label: "Tablet(s)" },
  { value: "capsule", label: "Capsule(s)" },
  { value: "ml", label: "mL" },
  { value: "bottle", label: "Bottle(s)" },
  { value: "vial", label: "Vial(s)" },
  { value: "ampoule", label: "Ampoule(s)" },
  { value: "sachet", label: "Sachet(s)" },
  { value: "tube", label: "Tube(s)" },
  { value: "suppository", label: "Suppository(ies)" },
  { value: "drop", label: "Drop(s)" },
  { value: "puff", label: "Puff(s)" },
];

/** Matches the `form` CHECK constraint on royan_drug_formulary (migration 130). */
export const DOSE_FORM_OPTIONS = [
  { value: "tablet", label: "Tablet" },
  { value: "capsule", label: "Capsule" },
  { value: "syrup", label: "Syrup" },
  { value: "injection", label: "Injection" },
  { value: "cream", label: "Cream" },
  { value: "ointment", label: "Ointment" },
  { value: "drops", label: "Drops" },
  { value: "inhaler", label: "Inhaler" },
  { value: "patch", label: "Patch" },
  { value: "suppository", label: "Suppository" },
  { value: "other", label: "Other" },
];

/**
 * Sensible dispensing unit for a drug's dose form, used to prefill Unit when a
 * drug is picked. The formulary carries its own `unit`, which wins; this is the
 * fallback for rows where it is blank.
 */
export function unitForDoseForm(form?: string | null): string | undefined {
  switch ((form ?? "").toLowerCase()) {
    case "tablet": return "tablet";
    case "capsule": return "capsule";
    case "syrup": return "ml";
    case "injection": return "vial";
    case "drops": return "drop";
    case "inhaler": return "puff";
    case "suppository": return "suppository";
    case "cream":
    case "ointment": return "tube";
    default: return undefined;
  }
}
