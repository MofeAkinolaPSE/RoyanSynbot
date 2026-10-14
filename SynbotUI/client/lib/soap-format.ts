/**
 * Composing a SOAP draft into the strings the backend stores.
 *
 * POST /queue/encounters/{id}/notes accepts subjective/objective/assessment/
 * plan/icd10_codes and, when `content` is omitted, composes its own
 * " | "-joined fallback (queue_clinical.py). We send an explicit `content`
 * instead so the human-readable record is exactly what the clinician saw —
 * including the staged orders, which royan_encounter_notes has no column to
 * link and would otherwise vanish from the note entirely.
 *
 * summariseSoap() intentionally mirrors the existing timeline renderer in
 * components/patient/EncounterStoryPanel.tsx (S:/O:/A:/P: joined by two
 * spaces) so a note reads identically in the composer, the Notes tab and the
 * encounter timeline. If that display ever changes, change it here.
 */

import type { DiagnosisEntry, DraftOrder, SoapDraft } from "./soap-gate";

export interface ComposedNote {
  note_type: "soap";
  subjective: string | null;
  objective: string | null;
  assessment: string | null;
  plan: string | null;
  icd10_codes: string[] | null;
  content: string;
}

const clean = (v: string | null | undefined): string => (v ?? "").trim();
const orNull = (v: string): string | null => (v ? v : null);

/**
 * Subjective is captured as three discrete fields ("it should come in
 * different input fields") but stored as one labelled block, so the structure
 * the doctor worked in survives into the record.
 */
export function composeSubjective(d: SoapDraft): string {
  const { chief_complaint, hpc, ros } = d.subjective;
  return [
    clean(chief_complaint) && `Chief complaint: ${clean(chief_complaint)}`,
    clean(hpc) && `History of presenting complaint: ${clean(hpc)}`,
    clean(ros) && `Review of systems: ${clean(ros)}`,
  ]
    .filter(Boolean)
    .join("\n");
}

/** General examination first, then each systemic block — the MD's own order. */
export function composeObjective(d: SoapDraft): string {
  const parts: string[] = [];
  if (clean(d.objective.general)) {
    parts.push(`General examination: ${clean(d.objective.general)}`);
  }
  for (const [system, text] of Object.entries(d.objective.systems ?? {})) {
    if (clean(text)) parts.push(`${system}: ${clean(text)}`);
  }
  return parts.join("\n");
}

/** Diagnoses as "Description [CODE]", primary first, then any free text. */
export function composeAssessment(d: SoapDraft): string {
  const dx = [...(d.assessment.diagnoses ?? [])].sort(
    (a, b) => Number(!!b.is_primary) - Number(!!a.is_primary),
  );
  const lines = dx.map((x, i) => {
    const primary = x.is_primary || (i === 0 && !dx.some((y) => y.is_primary));
    const certainty = x.certainty && x.certainty !== "confirmed" ? ` (${x.certainty.replace(/_/g, " ")})` : "";
    return `${primary ? "Primary" : "Secondary"}: ${x.description} [${x.icd_code}]${certainty}`;
  });
  if (clean(d.assessment.text)) lines.push(clean(d.assessment.text));
  return lines.join("\n");
}

const ORDER_LABEL: Record<DraftOrder["kind"], string> = {
  medication: "Rx",
  allergy: "Allergy",
  immunization: "Immunisation",
  lab: "Lab",
  radiology: "Radiology",
  procedure: "Procedure",
};

/**
 * Plan narrative plus a rendered list of the staged orders.
 * Without this the note would say "as discussed" while the actual orders lived
 * only in other tables — unreadable as a standalone legal record.
 */
export function composePlan(d: SoapDraft): string {
  const parts: string[] = [];
  if (clean(d.plan.text)) parts.push(clean(d.plan.text));

  const orders = d.plan.orders ?? [];
  if (orders.length) {
    parts.push(
      ["Orders:", ...orders.map((o) => `- ${ORDER_LABEL[o.kind] ?? o.kind}: ${o.label}`)].join("\n"),
    );
  }
  return parts.join("\n\n");
}

export function collectIcd10Codes(diagnoses: DiagnosisEntry[] | undefined): string[] {
  return Array.from(
    new Set((diagnoses ?? []).map((d) => clean(d.icd_code)).filter(Boolean)),
  );
}

/**
 * The S:/O:/A:/P: one-liner used by the timeline and note lists.
 * Mirrors EncounterStoryPanel.tsx:97-102 exactly.
 */
export function summariseSoap(note: {
  subjective?: string | null;
  objective?: string | null;
  assessment?: string | null;
  plan?: string | null;
  content?: string | null;
}): string {
  const soap = [
    clean(note.subjective) && `S: ${clean(note.subjective)}`,
    clean(note.objective) && `O: ${clean(note.objective)}`,
    clean(note.assessment) && `A: ${clean(note.assessment)}`,
    clean(note.plan) && `P: ${clean(note.plan)}`,
  ]
    .filter(Boolean)
    .join("  ");
  return soap || clean(note.content);
}

/** Full readable note body, section-labelled — what we store as `content`. */
export function composeNoteContent(d: SoapDraft): string {
  const s = composeSubjective(d);
  const o = composeObjective(d);
  const a = composeAssessment(d);
  const p = composePlan(d);
  return [
    s && `SUBJECTIVE\n${s}`,
    o && `OBJECTIVE\n${o}`,
    a && `ASSESSMENT\n${a}`,
    p && `PLAN\n${p}`,
  ]
    .filter(Boolean)
    .join("\n\n");
}

/** Build the exact POST body for /queue/encounters/{id}/notes. */
export function composeNotePayload(d: SoapDraft): ComposedNote {
  const codes = collectIcd10Codes(d.assessment.diagnoses);
  return {
    note_type: "soap",
    subjective: orNull(composeSubjective(d)),
    objective: orNull(composeObjective(d)),
    assessment: orNull(composeAssessment(d)),
    plan: orNull(composePlan(d)),
    icd10_codes: codes.length ? codes : null,
    content: composeNoteContent(d),
  };
}

/**
 * Append text into an existing field at the caret, keeping paragraphing sane.
 * Used by every template/phrase insert.
 */
export function appendAtCaret(
  existing: string,
  insert: string,
  caret?: number | null,
): string {
  const add = insert.trim();
  if (!add) return existing;
  const base = existing ?? "";
  if (!base.trim()) return add;

  if (caret == null || caret < 0 || caret > base.length) {
    return `${base.replace(/\s+$/, "")}\n${add}`;
  }
  const before = base.slice(0, caret).replace(/[ \t]+$/, "");
  const after = base.slice(caret);
  const sep = before && !before.endsWith("\n") ? "\n" : "";
  const tail = after && !after.startsWith("\n") ? "\n" : "";
  return `${before}${sep}${add}${tail}${after}`;
}
