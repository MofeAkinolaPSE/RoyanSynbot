/**
 * SOAP sequential gating.
 *
 * From the post-deployment meeting, the MD was unambiguous:
 *   "you put the S first, O first, A, then P... If you don't put A, you can't
 *    move to the next stage. Diagnosis must be there."
 *   "Chief Complaints. If I don't put a complaint, it's not likely to go."
 *   "give me the latitude to write whatever I like"          (HPI is free)
 *   "[Review of systems] we don't often do it, but it's part of"  (ROS optional)
 *
 * All gating lives here as one pure function so no rule is ever duplicated in
 * JSX. The composer renders state; it never decides it.
 *
 * Scope: DOCTOR SOAP NOTES ONLY. Nursing, progress, handover, referral and
 * free-text notes are deliberately ungated — a nurse recording an observation
 * must not be forced through a diagnosis. The "Quick note" path in the OPD
 * panel remains the sanctioned route for those, and is also the escape hatch
 * in an emergency.
 */

export interface DiagnosisEntry {
  icd_code: string;
  description: string;
  is_primary?: boolean;
  certainty?: "working" | "confirmed" | "rule_out";
}

export interface DraftOrder {
  tempId: string;
  kind: "medication" | "allergy" | "immunization" | "lab" | "radiology" | "procedure";
  label: string;
  payload: Record<string, unknown>;
}

export interface SoapDraft {
  subjective: { chief_complaint: string; hpc: string; ros: string };
  objective: { general: string; systems: Record<string, string> };
  assessment: { diagnoses: DiagnosisEntry[]; text: string };
  plan: { text: string; orders: DraftOrder[] };
}

export type SectionStatus = "locked" | "active" | "complete";

export interface SectionState {
  status: SectionStatus;
  /** Shown inline on a locked section. Never hide the section — say why. */
  blockedReason?: string;
}

export interface SoapGate {
  s: SectionState;
  o: SectionState;
  a: SectionState;
  p: SectionState;
  canSign: boolean;
  /** First section still needing attention — drives auto-expand. */
  focus: "s" | "o" | "a" | "p" | null;
}

export function emptySoapDraft(): SoapDraft {
  return {
    subjective: { chief_complaint: "", hpc: "", ros: "" },
    objective: { general: "", systems: {} },
    assessment: { diagnoses: [], text: "" },
    plan: { text: "", orders: [] },
  };
}

const filled = (v: string | null | undefined): boolean => !!(v && v.trim());

/** S is complete on chief complaint alone. HPI and ROS are explicitly optional. */
export function isSubjectiveComplete(d: SoapDraft): boolean {
  return filled(d.subjective.chief_complaint);
}

/** O accepts either the general examination or any systemic block. */
export function isObjectiveComplete(d: SoapDraft): boolean {
  if (filled(d.objective.general)) return true;
  return Object.values(d.objective.systems ?? {}).some(filled);
}

/**
 * A requires at least one STRUCTURED diagnosis.
 *
 * Free text deliberately does NOT satisfy this. If it did, the auto-ICD
 * requirement ("the diagnosis will automatically generate the code") would
 * leak: a doctor could type "malaria" as prose and the note would carry no
 * code at all.
 */
export function isAssessmentComplete(d: SoapDraft): boolean {
  return (d.assessment.diagnoses?.length ?? 0) > 0;
}

/** P accepts either narrative or at least one staged order. */
export function isPlanComplete(d: SoapDraft): boolean {
  return filled(d.plan.text) || (d.plan.orders?.length ?? 0) > 0;
}

export function evaluateSoapGate(draft: SoapDraft): SoapGate {
  // Every section is open to write in at any time (doctors asked, Oct 2026: on a results review they go straight
  // to the assessment or plan). The order S -> O -> A -> P is kept where it matters - signing needs all four, and
  // Plan still needs a diagnosis ("If you don't put A, you can't move to the next stage") before the note is signed.
  const sDone = isSubjectiveComplete(draft);
  const oDone = isObjectiveComplete(draft);
  const aDone = isAssessmentComplete(draft);
  const pDone = isPlanComplete(draft);

  const s: SectionState = sDone ? { status: "complete" } : { status: "active", blockedReason: "Add a chief complaint" };
  const o: SectionState = oDone ? { status: "complete" } : { status: "active", blockedReason: "Record your examination findings" };
  const a: SectionState = aDone ? { status: "complete" } : { status: "active", blockedReason: "Add at least one diagnosis" };
  const p: SectionState = pDone ? { status: "complete" } : { status: "active", blockedReason: "Add a plan or an order" };

  const focus: SoapGate["focus"] = !sDone ? "s" : !oDone ? "o" : !aDone ? "a" : !pDone ? "p" : null;

  return { s, o, a, p, canSign: sDone && oDone && aDone && pDone, focus };
}

/** Human-readable reason the note cannot be signed yet, or null when it can. */
export function signBlockedReason(draft: SoapDraft): string | null {
  const g = evaluateSoapGate(draft);
  if (g.canSign) return null;
  return (
    g.s.blockedReason ??
    g.o.blockedReason ??
    g.a.blockedReason ??
    g.p.blockedReason ??
    "Complete all four sections before signing"
  ) + " to sign";
}

/** True when anything at all has been entered — drives the unsaved-work guard. */
export function isDraftDirty(draft: SoapDraft): boolean {
  const { subjective: s, objective: o, assessment: a, plan: p } = draft;
  return (
    filled(s.chief_complaint) ||
    filled(s.hpc) ||
    filled(s.ros) ||
    filled(o.general) ||
    Object.values(o.systems ?? {}).some(filled) ||
    (a.diagnoses?.length ?? 0) > 0 ||
    filled(a.text) ||
    filled(p.text) ||
    (p.orders?.length ?? 0) > 0
  );
}
