/**
 * Tier 3 contextual help — one short explanation attached to one control.
 *
 * These are deliberately NOT walkthroughs. A walkthrough teaches a task you
 * chose to learn; a hint answers a question you had while doing something else,
 * without taking the screen away from you.
 *
 * The copy lives here rather than inline in JSX for three reasons: the same
 * explanation appears on more than one screen (an empty allergy list means the
 * same thing everywhere), the wording of the safety-critical ones is checked by
 * a spec, and a reviewer can read all of it in one file.
 */

export type HelpHint = {
  id: string;
  title: string;
  body: string;
  /**
   * Set where a plausible misreading of the screen has clinical consequences.
   * These render with an amber marker instead of a muted one, and their wording
   * is pinned by help-hints.spec.ts so it cannot be softened by accident.
   */
  safetyCritical?: boolean;
};

export const HELP_HINTS: HelpHint[] = [
  // ---------------------------------------------------------------- clinical
  {
    id: "allergies-empty",
    title: "An empty allergy list is not a clearance",
    safetyCritical: true,
    body:
      "It means nobody has recorded an allergy for this patient yet — it does not mean the patient has none. The old system held no allergy records at all, so every patient starts blank here. Ask the patient directly and record what they tell you; from then on it warns everyone who prescribes.",
  },
  {
    id: "history-starts-before-golive",
    title: "The record did not start today",
    body:
      "Visits, results, notes, bills and admissions from the old system were carried across, going back years. If a patient says they were seen here before, their history is on this chart — look before you assume it is missing.",
  },
  {
    id: "documents-index-only",
    title: "Listed, but not stored here",
    body:
      "Rows marked Migrated are an index of documents the old system held — the file itself was not carried across, so there is nothing to open. The entry is kept so you know the document exists and can ask records for it. Anything uploaded here from now on opens normally.",
  },
  {
    id: "note-locked-section",
    title: "Why this section is closed",
    body:
      "The note is written in order — Subjective, Objective, Assessment, Plan. Each section opens once the one before it has what it needs, and the grey line tells you exactly what is missing. Nothing is lost while you wait; the section is closed, not hidden.",
  },
  {
    id: "note-signed-lock",
    title: "Signing is permanent",
    safetyCritical: true,
    body:
      "Once signed, the text cannot be edited by anyone, including you. This is what makes the note usable as a legal record years later. If you need to correct it, add an addendum — the correction sits with the note and both versions stay readable.",
  },
  {
    id: "note-unsigned",
    title: "Saved, but not signed",
    body:
      "The note was stored but carries no signature, because this login is not yet linked to a staff record. Ask an administrator to link your account, then sign it. Until then it is a draft in the eyes of the record.",
  },
  {
    id: "diagnosis-code-readonly",
    title: "You do not type the code",
    body:
      "Search the condition in words. The ICD-10 code is attached automatically from the catalogue and shown for reference only — it cannot be typed over, so a mistyped code cannot reach billing or reporting.",
  },
  // --------------------------------------------------------------------- lab
  {
    id: "lab-verify-gate",
    title: "Verify is what releases the result",
    safetyCritical: true,
    body:
      "An entered result is not visible to the doctor who requested it until it is verified. That gap is deliberate: it gives you the chance to catch a transcription error before anyone treats on it. A result sitting unverified is a result nobody is acting on.",
  },
  // --------------------------------------------------------------- radiology
  {
    id: "radiology-worklist-scope",
    title: "The worklist shows today's work only",
    body:
      "Studies carried over from the old system are deliberately kept off this list, or it would open with tens of thousands of finished studies. They are all on the patient's chart under Radiology — the worklist is for what still needs doing.",
  },
  // ---------------------------------------------------------------- pharmacy
  {
    id: "pharmacy-allergy-warning",
    title: "A warning, not a block",
    safetyCritical: true,
    body:
      "This flags a drug against an allergy already recorded for the patient. It does not stop you — there are real reasons to prescribe through a known allergy. It exists so the decision is made knowingly rather than missed.",
  },
  {
    id: "pharmacy-batch-margin",
    title: "Where these prices come from",
    body:
      "Cost and selling price are per batch, carried over from the old system's purchase records, so margin can differ between two batches of the same drug. Batches past their expiry date are marked in red and should not be dispensed.",
  },
  // ----------------------------------------------------------------- billing
  {
    id: "billing-outstanding",
    title: "How outstanding is worked out",
    body:
      "It is the sum of what is still pending across this patient's bills, including those from the old system. It is a total of what the record shows as unpaid — treat it as a prompt to check, not as a demand to hand the patient.",
  },
  // ----------------------------------------------------------------- nursing
  {
    id: "nursing-notes-ungated",
    title: "Your notes are not gated",
    body:
      "The strict Subjective-Objective-Assessment-Plan order applies to a doctor's consultation note only. Write what you observed, in your own words, in any order. Signing and corrections work the same way as everywhere else.",
  },
  {
    id: "vitals-recent-shown",
    title: "Showing the most recent",
    body:
      "This card shows the latest readings, not the whole history. Use View all for the full set — some patients carry hundreds of recorded observations going back years.",
  },
];

const BY_ID = new Map(HELP_HINTS.map((h) => [h.id, h]));

export function getHelpHint(id: string): HelpHint | undefined {
  return BY_ID.get(id);
}
