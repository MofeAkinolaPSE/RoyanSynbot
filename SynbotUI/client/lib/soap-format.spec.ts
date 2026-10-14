import { describe, it, expect } from "vitest";
import { emptySoapDraft, type SoapDraft } from "./soap-gate";
import {
  composeSubjective,
  composeObjective,
  composeAssessment,
  composePlan,
  composeNoteContent,
  composeNotePayload,
  collectIcd10Codes,
  summariseSoap,
  appendAtCaret,
} from "./soap-format";

function fullDraft(): SoapDraft {
  const d = emptySoapDraft();
  d.subjective = {
    chief_complaint: "Headache x 3 days",
    hpc: "Gradual onset, frontal, worse in the mornings.",
    ros: "Constitutional: Negative except fever",
  };
  d.objective = {
    general: "No pallor, no jaundice, afebrile",
    systems: { Respiratory: "Chest clear", Cardiovascular: "S1 S2 heard" },
  };
  d.assessment = {
    diagnoses: [
      { icd_code: "B54", description: "Unspecified malaria", is_primary: true },
      { icd_code: "R51", description: "Headache", certainty: "working" },
    ],
    text: "Await FBC before escalating.",
  };
  d.plan = {
    text: "Start ACT, review in 3 days",
    orders: [
      { tempId: "1", kind: "lab", label: "FBC (routine)", payload: {} },
      { tempId: "2", kind: "medication", label: "Artemether 20mg PO BD x3/7", payload: {} },
    ],
  };
  return d;
}

describe("composeSubjective", () => {
  it("labels the three discrete fields", () => {
    const out = composeSubjective(fullDraft());
    expect(out).toContain("Chief complaint: Headache x 3 days");
    expect(out).toContain("History of presenting complaint:");
    expect(out).toContain("Review of systems:");
  });

  it("omits optional fields that were left blank", () => {
    const d = emptySoapDraft();
    d.subjective.chief_complaint = "Cough";
    const out = composeSubjective(d);
    expect(out).toBe("Chief complaint: Cough");
    expect(out).not.toContain("History of presenting");
    expect(out).not.toContain("Review of systems");
  });
});

describe("composeObjective", () => {
  it("puts general examination before the systemic blocks", () => {
    const out = composeObjective(fullDraft());
    const lines = out.split("\n");
    expect(lines[0]).toMatch(/^General examination:/);
    expect(lines[1]).toMatch(/^Respiratory:/);
  });

  it("drops empty systemic blocks", () => {
    const d = emptySoapDraft();
    d.objective.systems = { Respiratory: "Chest clear", Neuro: "   " };
    expect(composeObjective(d)).toBe("Respiratory: Chest clear");
  });
});

describe("composeAssessment", () => {
  it("renders 'Description [CODE]' and marks the primary first", () => {
    const out = composeAssessment(fullDraft());
    const lines = out.split("\n");
    expect(lines[0]).toBe("Primary: Unspecified malaria [B54]");
    expect(lines[1]).toBe("Secondary: Headache [R51] (working)");
  });

  it("treats the first diagnosis as primary when none is flagged", () => {
    const d = emptySoapDraft();
    d.assessment.diagnoses = [
      { icd_code: "A", description: "First" },
      { icd_code: "B", description: "Second" },
    ];
    const lines = composeAssessment(d).split("\n");
    expect(lines[0]).toMatch(/^Primary: First/);
    expect(lines[1]).toMatch(/^Secondary: Second/);
  });

  it("appends assessment free text after the coded diagnoses", () => {
    expect(composeAssessment(fullDraft())).toContain("Await FBC before escalating.");
  });
});

describe("composePlan", () => {
  // Without this the orders would exist only in other tables and the note
  // would be unreadable as a standalone record.
  it("serialises staged orders into the note body", () => {
    const out = composePlan(fullDraft());
    expect(out).toContain("Start ACT, review in 3 days");
    expect(out).toContain("Orders:");
    expect(out).toContain("- Lab: FBC (routine)");
    expect(out).toContain("- Rx: Artemether 20mg PO BD x3/7");
  });

  it("handles orders with no narrative", () => {
    const d = emptySoapDraft();
    d.plan.orders = [{ tempId: "1", kind: "radiology", label: "CXR", payload: {} }];
    expect(composePlan(d)).toBe("Orders:\n- Radiology: CXR");
  });

  it("handles narrative with no orders", () => {
    const d = emptySoapDraft();
    d.plan.text = "Reassure and discharge";
    expect(composePlan(d)).toBe("Reassure and discharge");
  });
});

describe("collectIcd10Codes", () => {
  it("extracts and de-duplicates codes", () => {
    expect(collectIcd10Codes(fullDraft().assessment.diagnoses)).toEqual(["B54", "R51"]);
    expect(
      collectIcd10Codes([
        { icd_code: "B54", description: "a" },
        { icd_code: "B54", description: "b" },
      ]),
    ).toEqual(["B54"]);
  });

  it("is safe on undefined", () => {
    expect(collectIcd10Codes(undefined)).toEqual([]);
  });
});

describe("composeNotePayload", () => {
  it("produces the exact POST shape the backend accepts", () => {
    const p = composeNotePayload(fullDraft());
    expect(p.note_type).toBe("soap");
    expect(p.subjective).toContain("Chief complaint");
    expect(p.objective).toContain("General examination");
    expect(p.assessment).toContain("[B54]");
    expect(p.plan).toContain("Orders:");
    expect(p.icd10_codes).toEqual(["B54", "R51"]);
    expect(p.content).toContain("SUBJECTIVE");
    expect(p.content).toContain("PLAN");
  });

  it("nulls empty sections rather than sending empty strings", () => {
    const p = composeNotePayload(emptySoapDraft());
    expect(p.subjective).toBeNull();
    expect(p.objective).toBeNull();
    expect(p.assessment).toBeNull();
    expect(p.plan).toBeNull();
    expect(p.icd10_codes).toBeNull();
  });
});

describe("summariseSoap — must match EncounterStoryPanel's renderer", () => {
  it("joins present sections with two spaces", () => {
    expect(
      summariseSoap({ subjective: "cough", objective: "clear", assessment: "URTI", plan: "rest" }),
    ).toBe("S: cough  O: clear  A: URTI  P: rest");
  });

  it("skips absent sections", () => {
    expect(summariseSoap({ subjective: "cough", plan: "rest" })).toBe("S: cough  P: rest");
  });

  it("falls back to content when no SOAP fields exist", () => {
    expect(summariseSoap({ content: "Free text note" })).toBe("Free text note");
  });

  it("returns empty string when there is nothing at all", () => {
    expect(summariseSoap({})).toBe("");
  });
});

describe("appendAtCaret", () => {
  it("returns the insert when the field is empty", () => {
    expect(appendAtCaret("", "Chest clear")).toBe("Chest clear");
    expect(appendAtCaret("   ", "Chest clear")).toBe("Chest clear");
  });

  it("appends on a new line when no caret is given", () => {
    expect(appendAtCaret("Existing", "Added")).toBe("Existing\nAdded");
  });

  it("inserts at the caret position", () => {
    expect(appendAtCaret("AB", "X", 1)).toBe("A\nX\nB");
  });

  it("does not double up newlines", () => {
    expect(appendAtCaret("A\n", "X", 2)).toBe("A\nX");
  });

  it("ignores an empty insert", () => {
    expect(appendAtCaret("Existing", "   ")).toBe("Existing");
  });

  it("falls back to appending when the caret is out of range", () => {
    expect(appendAtCaret("AB", "X", 99)).toBe("AB\nX");
  });
});
