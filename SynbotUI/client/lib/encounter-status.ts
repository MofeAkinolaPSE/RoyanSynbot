// Single source of truth for encounter workflow-stage badge colors — this
// used to be copy-pasted into 4 different files with drifting assignments
// (e.g. one dashboard used green for "consulting" and red for "billing",
// while the rest used green for "discharged" and pink for "billing"), so the
// same status showed a different, sometimes contradictory color depending on
// which screen you were looking at.
//
// Progresses light-to-deep blue through the clinical stages, breaks out to
// gold for the billing/financial stage and green only for the terminal
// discharge — consistent with the Royal Azure palette (see global.css).
export const ENCOUNTER_STATUS_COLORS: Record<string, string> = {
  patient_registered:  "bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30",
  triaged:             "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
  nurse_assessment:    "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/30",
  called:              "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400 border-cyan-500/30",
  consulting:          "bg-primary/15 text-primary border-primary/30",
  lab_ordered:         "bg-indigo-500/15 text-indigo-700 dark:text-indigo-400 border-indigo-500/30",
  // Results are back and nobody has read them yet. Deliberately the loudest
  // colour on the board: this is the state where a patient sits waiting while
  // an answer already exists.
  awaiting_results:    "bg-teal-500/20 text-teal-700 dark:text-teal-300 border-teal-500/40",
  pharmacy_dispensing: "bg-violet-500/15 text-violet-700 dark:text-violet-400 border-violet-500/30",
  billing_pending:     "bg-gold/15 text-gold border-gold/30",
  discharged:          "bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30",
};

/** What each step of the visit is called on screen (the finance-meeting workflow: front desk -> vitals -> doctor ->
 *  cashier -> services -> review if asked -> pay -> discharge). `awaiting_results` is set when the LAST result is back,
 *  so it reads "Results ready", not "awaiting". */
export const ENCOUNTER_STATUS_LABELS: Record<string, string> = {
  patient_registered: "Registered",
  triaged: "Waiting for vitals",
  nurse_assessment: "Ready for doctor",
  called: "Called in",
  consulting: "With doctor",
  lab_ordered: "Waiting for results",
  awaiting_results: "Results ready – doctor review",
  pharmacy_dispensing: "Pharmacy",
  billing_pending: "Done – pay & discharge",
  discharged: "Discharged",
  admitted: "Admitted",
};

export function encounterStatusLabel(status?: string | null): string {
  return ENCOUNTER_STATUS_LABELS[status ?? ""] ?? String(status ?? "").replace(/_/g, " ");
}

export const ENCOUNTER_STATUS_FALLBACK_COLOR =
  "bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30";

export function encounterStatusColor(status?: string | null): string {
  return ENCOUNTER_STATUS_COLORS[status ?? ""] ?? ENCOUNTER_STATUS_FALLBACK_COLOR;
}
