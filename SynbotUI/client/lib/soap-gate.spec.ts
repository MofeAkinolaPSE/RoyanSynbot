import { describe, it, expect } from "vitest";
import {
  emptySoapDraft,
  evaluateSoapGate,
  isSubjectiveComplete,
  isObjectiveComplete,
  isAssessmentComplete,
  isPlanComplete,
  signBlockedReason,
  isDraftDirty,
  type SoapDraft,
} from "./soap-gate";

/** Build a draft progressively filled up to the named stage. */
function draftUpTo(stage: "none" | "s" | "o" | "a" | "p"): SoapDraft {
  const d = emptySoapDraft();
  if (stage === "none") return d;
  d.subjective.chief_complaint = "Headache x 3 days";
  if (stage === "s") return d;
  d.objective.general = "No pallor, no jaundice, afebrile";
  if (stage === "o") return d;
  d.assessment.diagnoses = [{ icd_code: "B54", description: "Unspecified malaria", is_primary: true }];
  if (stage === "a") return d;
  d.plan.text = "Start ACT, review in 3 days";
  return d;
}

describe("section completion rules", () => {
  it("S completes on chief complaint alone — HPI and ROS are optional", () => {
    const d = emptySoapDraft();
    d.subjective.chief_complaint = "Cough";
    expect(isSubjectiveComplete(d)).toBe(true);
    expect(d.subjective.hpc).toBe("");
    expect(d.subjective.ros).toBe("");
  });

  it("S does NOT complete on HPI/ROS without a chief complaint", () => {
    const d = emptySoapDraft();
    d.subjective.hpc = "Long history of...";
    d.subjective.ros = "Constitutional: Negative";
    expect(isSubjectiveComplete(d)).toBe(false);
  });

  it("whitespace does not count as a chief complaint", () => {
    const d = emptySoapDraft();
    d.subjective.chief_complaint = "    ";
    expect(isSubjectiveComplete(d)).toBe(false);
  });

  it("O completes on general examination alone", () => {
    const d = draftUpTo("s");
    d.objective.general = "No acute distress";
    expect(isObjectiveComplete(d)).toBe(true);
  });

  it("O completes on any systemic block alone", () => {
    const d = draftUpTo("s");
    d.objective.systems = { Respiratory: "Chest clear" };
    expect(isObjectiveComplete(d)).toBe(true);
  });

  it("O ignores empty systemic blocks", () => {
    const d = draftUpTo("s");
    d.objective.systems = { Respiratory: "", Cardiovascular: "   " };
    expect(isObjectiveComplete(d)).toBe(false);
  });

  // The single most important rule in this file.
  it("A requires a STRUCTURED diagnosis — free text must not satisfy it", () => {
    const d = draftUpTo("o");
    d.assessment.text = "Probably malaria, will treat empirically";
    expect(isAssessmentComplete(d)).toBe(false);

    d.assessment.diagnoses = [{ icd_code: "B54", description: "Unspecified malaria" }];
    expect(isAssessmentComplete(d)).toBe(true);
  });

  it("P completes on narrative OR on a staged order", () => {
    const withText = draftUpTo("a");
    withText.plan.text = "Discharge with advice";
    expect(isPlanComplete(withText)).toBe(true);

    const withOrder = draftUpTo("a");
    withOrder.plan.orders = [
      { tempId: "t1", kind: "lab", label: "FBC", payload: {} },
    ];
    expect(isPlanComplete(withOrder)).toBe(true);
  });
});

describe("open sections, ordered signing", () => {
  it("leaves every section open to write on an empty draft", () => {
    const g = evaluateSoapGate(emptySoapDraft());
    for (const k of ["s", "o", "a", "p"] as const) expect(g[k].status).toBe("active");
    expect(g.canSign).toBe(false);
  });

  it("marks each section complete on its own content", () => {
    const d = emptySoapDraft();
    d.assessment.diagnoses = [{ icd_code: "B54", description: "Malaria" }];
    const g = evaluateSoapGate(d);
    expect(g.a.status).toBe("complete");
    expect(g.s.status).toBe("active");
    expect(g.p.status).toBe("active");
  });

  // "If you don't put A, you can't move to the next stage" - kept at signing.
  it("will not sign without a diagnosis", () => {
    const d = draftUpTo("p");
    d.assessment.diagnoses = [];
    expect(evaluateSoapGate(d).canSign).toBe(false);
    expect(signBlockedReason(d)).toMatch(/diagnosis/i);
  });

  it("allows signing only when all four are complete", () => {
    expect(evaluateSoapGate(draftUpTo("a")).canSign).toBe(false);
    expect(evaluateSoapGate(draftUpTo("p")).canSign).toBe(true);
  });

  it("stops signing again if an earlier section is cleared", () => {
    const d = draftUpTo("p");
    d.subjective.chief_complaint = "";
    const g = evaluateSoapGate(d);
    expect(g.o.status).toBe("complete");
    expect(g.canSign).toBe(false);
  });
});

describe("blocked reasons are specific and actionable", () => {
  it("names what each section is missing", () => {
    const g = evaluateSoapGate(emptySoapDraft());
    expect(g.s.blockedReason).toMatch(/chief complaint/i);
    expect(g.o.blockedReason).toMatch(/examination/i);
    expect(g.a.blockedReason).toMatch(/diagnosis/i);
  });

  it("signBlockedReason points at the earliest missing section, null when signable", () => {
    expect(signBlockedReason(emptySoapDraft())).toMatch(/chief complaint/i);
    expect(signBlockedReason(draftUpTo("a"))).toMatch(/plan|order/i);
    expect(signBlockedReason(draftUpTo("p"))).toBeNull();
  });
});

describe("focus", () => {
  it("advances through the sections and clears when done", () => {
    expect(evaluateSoapGate(emptySoapDraft()).focus).toBe("s");
    expect(evaluateSoapGate(draftUpTo("s")).focus).toBe("o");
    expect(evaluateSoapGate(draftUpTo("o")).focus).toBe("a");
    expect(evaluateSoapGate(draftUpTo("a")).focus).toBe("p");
    expect(evaluateSoapGate(draftUpTo("p")).focus).toBeNull();
  });
});

describe("isDraftDirty — guards against losing work on close", () => {
  it("is false for a pristine draft", () => {
    expect(isDraftDirty(emptySoapDraft())).toBe(false);
  });

  it("is true after any single field is touched", () => {
    const cc = emptySoapDraft();
    cc.subjective.chief_complaint = "x";
    expect(isDraftDirty(cc)).toBe(true);

    const ros = emptySoapDraft();
    ros.subjective.ros = "Negative";
    expect(isDraftDirty(ros)).toBe(true);

    const sys = emptySoapDraft();
    sys.objective.systems = { Chest: "clear" };
    expect(isDraftDirty(sys)).toBe(true);

    const dx = emptySoapDraft();
    dx.assessment.diagnoses = [{ icd_code: "A", description: "B" }];
    expect(isDraftDirty(dx)).toBe(true);

    const ord = emptySoapDraft();
    ord.plan.orders = [{ tempId: "1", kind: "lab", label: "FBC", payload: {} }];
    expect(isDraftDirty(ord)).toBe(true);
  });

  it("ignores whitespace-only edits", () => {
    const d = emptySoapDraft();
    d.plan.text = "   \n  ";
    expect(isDraftDirty(d)).toBe(false);
  });
});
