import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  WALKTHROUGHS,
  getWalkthroughsForRole,
  getWalkthroughsForRoute,
  getWalkthroughById,
} from "./walkthroughs";

/**
 * These guard the two ways a walkthrough silently rots: an anchor that no
 * longer exists in the UI (so a step highlights nothing), and a homeRoute that
 * is not a real page (so "Show me how" never appears). Both fail quietly at
 * runtime, which is exactly the class of bug worth a test.
 */

const CLIENT_DIR = path.resolve(__dirname, "..");

function readAllSource(): string {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === "dist") continue;
        walk(p);
      } else if (/\.tsx?$/.test(entry.name) && !/\.spec\.tsx?$/.test(entry.name)) {
        out.push(fs.readFileSync(p, "utf8"));
      }
    }
  };
  walk(CLIENT_DIR);
  return out.join("\n");
}

describe("walkthrough definitions", () => {
  it("every walkthrough has a unique id", () => {
    const ids = WALKTHROUGHS.map((w) => w.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every walkthrough has content", () => {
    for (const w of WALKTHROUGHS) {
      expect(w.title.trim(), `${w.id} title`).not.toBe("");
      expect(w.summary.trim(), `${w.id} summary`).not.toBe("");
      expect(w.steps.length, `${w.id} steps`).toBeGreaterThan(0);
      expect(w.estMinutes, `${w.id} estMinutes`).toBeGreaterThan(0);
    }
  });

  it("every step has a title and body", () => {
    for (const w of WALKTHROUGHS) {
      w.steps.forEach((s, i) => {
        expect(s.title.trim(), `${w.id} step ${i + 1} title`).not.toBe("");
        expect(s.body.trim().length, `${w.id} step ${i + 1} body`).toBeGreaterThan(20);
      });
    }
  });

  // The important one: a typo'd anchor highlights nothing and nobody notices.
  it("every anchor exists as a data-tour-id somewhere in the client", () => {
    const source = readAllSource();
    const missing: string[] = [];
    for (const w of WALKTHROUGHS) {
      for (const s of w.steps) {
        if (!s.anchor) continue;
        if (!source.includes(`data-tour-id="${s.anchor}"`)) {
          missing.push(`${w.id} → ${s.anchor}`);
        }
      }
    }
    expect(missing, `anchors with no matching data-tour-id:\n${missing.join("\n")}`).toEqual([]);
  });

  it("every homeRoute is a real route in App.tsx", () => {
    const app = fs.readFileSync(path.join(CLIENT_DIR, "App.tsx"), "utf8");
    const routes = new Set(
      Array.from(app.matchAll(/<Route\s+path="([^"]+)"/g)).map((m) => m[1]),
    );
    const bad = WALKTHROUGHS
      .filter((w) => w.homeRoute && !routes.has(w.homeRoute))
      .map((w) => `${w.id} → ${w.homeRoute}`);
    expect(bad, `homeRoutes not present in App.tsx:\n${bad.join("\n")}`).toEqual([]);
  });

  it("navigateTo steps point at real routes too", () => {
    const app = fs.readFileSync(path.join(CLIENT_DIR, "App.tsx"), "utf8");
    const routes = new Set(
      Array.from(app.matchAll(/<Route\s+path="([^"]+)"/g)).map((m) => m[1]),
    );
    const bad: string[] = [];
    for (const w of WALKTHROUGHS) {
      for (const s of w.steps) {
        if (s.navigateTo && !routes.has(s.navigateTo)) bad.push(`${w.id} → ${s.navigateTo}`);
      }
    }
    expect(bad).toEqual([]);
  });
});

describe("walkthrough selection", () => {
  it("filters by role", () => {
    const doctor = getWalkthroughsForRole("doctor").map((w) => w.id);
    expect(doctor).toContain("soap-note");
    expect(doctor).not.toContain("dispensing");

    const pharmacist = getWalkthroughsForRole("pharmacist").map((w) => w.id);
    expect(pharmacist).toContain("dispensing");
    expect(pharmacist).not.toContain("soap-note");
  });

  it("gives every clinical role at least one walkthrough", () => {
    for (const role of ["doctor", "nurse", "pharmacist", "lab", "receptionist"]) {
      expect(getWalkthroughsForRole(role).length, role).toBeGreaterThan(0);
    }
  });

  it("filters by route", () => {
    const onQueue = getWalkthroughsForRoute("/hospital/queue", "doctor").map((w) => w.id);
    expect(onQueue).toContain("soap-note");

    const onPharmacy = getWalkthroughsForRoute("/hospital/pharmacy", "doctor");
    expect(onPharmacy).toEqual([]);
  });

  it("looks up by id", () => {
    expect(getWalkthroughById("soap-note")?.title).toBe("Writing a SOAP note");
    expect(getWalkthroughById("nope")).toBeUndefined();
  });
});

describe("content accuracy", () => {
  // These caveats are patient-safety relevant. If someone rewrites the copy and
  // drops them, that should fail rather than quietly ship.
  it("the dispensing walkthrough states the allergy caveat", () => {
    const w = getWalkthroughById("dispensing")!;
    const text = w.steps.map((s) => `${s.title} ${s.body}`).join(" ").toLowerCase();
    expect(text).toContain("does not mean the patient has none");
  });

  it("the addendum walkthrough states that notes cannot be edited", () => {
    const w = getWalkthroughById("note-addendum")!;
    const text = w.steps.map((s) => `${s.title} ${s.body}`).join(" ").toLowerCase();
    expect(text).toContain("cannot be edited");
  });

  it("the lab walkthrough explains the verify gate", () => {
    const w = getWalkthroughById("lab-verify")!;
    const text = w.steps.map((s) => `${s.title} ${s.body}`).join(" ").toLowerCase();
    expect(text).toContain("not visible to the requesting doctor until it is verified");
  });
});

describe("interaction model", () => {
  it("a step can only ask for a click if it has something to click", () => {
    const bad = WALKTHROUGHS.flatMap((w) =>
      w.steps
        .map((s, n) => ({ s, n }))
        .filter(({ s }) => s.action === "click" && !s.anchor)
        .map(({ n }) => `${w.id} step ${n + 1}`),
    );
    expect(bad, `click steps with no anchor: ${bad.join(", ")}`).toEqual([]);
  });

  // The safety rule of the whole player: a control that commits something to a
  // real record must never be the thing we invite a trainee to press.
  it("cautioned steps are never click-to-advance", () => {
    const bad = WALKTHROUGHS.flatMap((w) =>
      w.steps
        .map((s, n) => ({ s, n }))
        .filter(({ s }) => s.caution && s.action === "click")
        .map(({ n }) => `${w.id} step ${n + 1}`),
    );
    expect(bad, `cautioned steps marked clickable: ${bad.join(", ")}`).toEqual([]);
  });

  // Signing a note, verifying a result and registering a patient all write to a
  // real record. If one lost its caution flag the player would start inviting
  // trainees to press it against live data.
  it("the committing controls stay observe-only", () => {
    const anchors = new Map<string, { caution?: boolean; action?: string }>();
    for (const w of WALKTHROUGHS) {
      for (const s of w.steps) if (s.anchor) anchors.set(s.anchor, s);
    }
    for (const a of ["soap-sign-button", "lab-verify-button", "frontdesk-register"]) {
      expect(anchors.get(a)?.caution, `${a} must be cautioned`).toBe(true);
      expect(anchors.get(a)?.action, `${a} must be observe-only`).toBe("observe");
    }
  });

  it("every click step tells the learner what to click", () => {
    const missing = WALKTHROUGHS.flatMap((w) =>
      w.steps.filter((s) => s.action === "click" && !s.cue).map((s) => `${w.id}: ${s.title}`),
    );
    expect(missing, `click steps with no cue: ${missing.join(", ")}`).toEqual([]);
  });

  // A walkthrough where nothing is ever pressed is a slideshow, which is the
  // thing this rebuild exists to stop being.
  it("every anchored walkthrough has at least one hands-on step", () => {
    const passive = WALKTHROUGHS.filter(
      (w) => w.steps.some((s) => s.anchor) && !w.steps.some((s) => s.action === "click"),
    ).map((w) => w.id);
    expect(passive, `walkthroughs with no clickable step: ${passive.join(", ")}`).toEqual([]);
  });
});
