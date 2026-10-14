import { describe, it, expect } from "vitest";
import { soapReducer } from "./use-soap-draft";
import { emptySoapDraft, evaluateSoapGate, type SoapDraft } from "@/lib/soap-gate";

const d0 = () => emptySoapDraft();
const dx = (code: string, desc = code) => ({ icd_code: code, description: desc });

describe("soapReducer — field edits", () => {
  it("sets the three subjective fields independently", () => {
    let s = soapReducer(d0(), { type: "setChiefComplaint", value: "Cough" });
    s = soapReducer(s, { type: "setHpc", value: "3 days" });
    s = soapReducer(s, { type: "setRos", value: "Negative" });
    expect(s.subjective).toEqual({ chief_complaint: "Cough", hpc: "3 days", ros: "Negative" });
  });

  it("sets and removes systemic examination blocks", () => {
    let s = soapReducer(d0(), { type: "setSystem", system: "Respiratory", value: "Chest clear" });
    expect(s.objective.systems).toEqual({ Respiratory: "Chest clear" });
    s = soapReducer(s, { type: "removeSystem", system: "Respiratory" });
    expect(s.objective.systems).toEqual({});
  });

  it("does not mutate the previous state object", () => {
    const before = d0();
    const after = soapReducer(before, { type: "setChiefComplaint", value: "x" });
    expect(before.subjective.chief_complaint).toBe("");
    expect(after).not.toBe(before);
  });
});

describe("soapReducer — diagnoses", () => {
  it("marks the first diagnosis primary automatically", () => {
    const s = soapReducer(d0(), { type: "addDiagnosis", diagnosis: dx("B54", "Malaria") });
    expect(s.assessment.diagnoses[0].is_primary).toBe(true);
  });

  it("does not mark subsequent diagnoses primary", () => {
    let s = soapReducer(d0(), { type: "addDiagnosis", diagnosis: dx("B54") });
    s = soapReducer(s, { type: "addDiagnosis", diagnosis: dx("R51") });
    expect(s.assessment.diagnoses.map((x) => !!x.is_primary)).toEqual([true, false]);
  });

  it("ignores a duplicate code", () => {
    let s = soapReducer(d0(), { type: "addDiagnosis", diagnosis: dx("B54") });
    s = soapReducer(s, { type: "addDiagnosis", diagnosis: dx("B54", "Different label") });
    expect(s.assessment.diagnoses).toHaveLength(1);
  });

  it("moves primary to the survivor when the primary is removed", () => {
    let s = soapReducer(d0(), { type: "addDiagnosis", diagnosis: dx("B54") });
    s = soapReducer(s, { type: "addDiagnosis", diagnosis: dx("R51") });
    s = soapReducer(s, { type: "removeDiagnosis", icdCode: "B54" });
    expect(s.assessment.diagnoses).toHaveLength(1);
    expect(s.assessment.diagnoses[0]).toMatchObject({ icd_code: "R51", is_primary: true });
  });

  it("switches primary explicitly, leaving exactly one", () => {
    let s = soapReducer(d0(), { type: "addDiagnosis", diagnosis: dx("B54") });
    s = soapReducer(s, { type: "addDiagnosis", diagnosis: dx("R51") });
    s = soapReducer(s, { type: "setPrimaryDiagnosis", icdCode: "R51" });
    expect(s.assessment.diagnoses.filter((x) => x.is_primary)).toHaveLength(1);
    expect(s.assessment.diagnoses.find((x) => x.is_primary)?.icd_code).toBe("R51");
  });
});

describe("soapReducer — orders", () => {
  it("adds and removes staged orders by tempId", () => {
    let s = soapReducer(d0(), {
      type: "addOrder",
      order: { tempId: "t1", kind: "lab", label: "FBC", payload: {} },
    });
    expect(s.plan.orders).toHaveLength(1);
    s = soapReducer(s, { type: "removeOrder", tempId: "t1" });
    expect(s.plan.orders).toHaveLength(0);
  });
});

describe("soapReducer — appendTo (template inserts)", () => {
  it("sets the field when empty", () => {
    const s = soapReducer(d0(), { type: "appendTo", field: "general", text: "No pallor" });
    expect(s.objective.general).toBe("No pallor");
  });

  it("appends on a new line when the field has content", () => {
    let s = soapReducer(d0(), { type: "setGeneral", value: "No pallor" });
    s = soapReducer(s, { type: "appendTo", field: "general", text: "No jaundice" });
    expect(s.objective.general).toBe("No pallor\nNo jaundice");
  });

  it("routes to each supported field", () => {
    const fields = ["hpc", "ros", "general", "assessmentText", "planText"] as const;
    for (const f of fields) {
      const s = soapReducer(d0(), { type: "appendTo", field: f, text: "X" });
      expect(JSON.stringify(s)).toContain("X");
    }
  });
});

describe("soapReducer — replace / reset", () => {
  it("replaces wholesale (draft restore)", () => {
    const restored: SoapDraft = { ...d0(), subjective: { chief_complaint: "Restored", hpc: "", ros: "" } };
    const s = soapReducer(d0(), { type: "replace", draft: restored });
    expect(s.subjective.chief_complaint).toBe("Restored");
  });

  it("resets to an empty draft", () => {
    let s = soapReducer(d0(), { type: "setChiefComplaint", value: "x" });
    s = soapReducer(s, { type: "reset" });
    expect(s).toEqual(d0());
  });
});

// The reducer and the gate must agree — this is the behaviour the MD asked for,
// exercised through the same action sequence the UI dispatches.
describe("reducer + gate integration", () => {
  it("walks a real consultation to signable, any section first", () => {
    let s = d0();
    expect(evaluateSoapGate(s).p.status).toBe("active");

    s = soapReducer(s, { type: "setPlanText", value: "Start ACT" });
    expect(evaluateSoapGate(s).p.status).toBe("complete");
    expect(evaluateSoapGate(s).canSign).toBe(false);

    s = soapReducer(s, { type: "setChiefComplaint", value: "Headache x3/7" });
    s = soapReducer(s, { type: "setGeneral", value: "Afebrile, no pallor" });
    // Free text alone is not a diagnosis.
    s = soapReducer(s, { type: "setAssessmentText", value: "probably malaria" });
    expect(evaluateSoapGate(s).canSign).toBe(false);

    s = soapReducer(s, { type: "addDiagnosis", diagnosis: dx("B54", "Malaria") });
    expect(evaluateSoapGate(s).canSign).toBe(true);
  });

  it("an order alone satisfies Plan", () => {
    let s = d0();
    s = soapReducer(s, { type: "setChiefComplaint", value: "c" });
    s = soapReducer(s, { type: "setGeneral", value: "o" });
    s = soapReducer(s, { type: "addDiagnosis", diagnosis: dx("B54") });
    s = soapReducer(s, {
      type: "addOrder",
      order: { tempId: "t1", kind: "lab", label: "FBC", payload: {} },
    });
    expect(evaluateSoapGate(s).canSign).toBe(true);
  });
});
