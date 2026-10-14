import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { HELP_HINTS, getHelpHint } from "./help-hints";

/**
 * Hints fail silently in both directions: a hint nothing mounts is invisible,
 * and a mounted id that no longer exists renders nothing where staff expect an
 * explanation. Both are checked here, along with the wording of the ones whose
 * misreading has clinical consequences.
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

describe("help hint registry", () => {
  it("ids are unique", () => {
    const ids = HELP_HINTS.map((h) => h.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every hint has a real title and a body worth reading", () => {
    for (const h of HELP_HINTS) {
      expect(h.title.trim(), `${h.id} title`).not.toBe("");
      expect(h.body.trim().length, `${h.id} body`).toBeGreaterThan(40);
    }
  });

  it("looks up by id and returns undefined for unknown ids", () => {
    expect(getHelpHint("allergies-empty")?.title).toBeTruthy();
    expect(getHelpHint("does-not-exist")).toBeUndefined();
  });

  // A hint nobody mounted is documentation, not help.
  it("every hint is mounted somewhere in the client", () => {
    const source = readAllSource();
    const unmounted = HELP_HINTS
      .filter((h) => !source.includes(`"${h.id}"`))
      .map((h) => h.id);
    expect(unmounted, `hints defined but never mounted:\n${unmounted.join("\n")}`).toEqual([]);
  });

  // The reverse: a mounted id with no entry renders nothing at all.
  it("every mounted id exists in the registry", () => {
    const source = readAllSource();
    const known = new Set(HELP_HINTS.map((h) => h.id));
    const mounted = new Set<string>();
    for (const m of source.matchAll(/(?:helpHintId=|<HelpHint\s+id=)"([^"]+)"/g)) {
      mounted.add(m[1]);
    }
    const orphans = [...mounted].filter((id) => !known.has(id));
    expect(orphans, `mounted ids with no registry entry:\n${orphans.join("\n")}`).toEqual([]);
  });
});

describe("safety-critical wording", () => {
  const text = (id: string) => {
    const h = getHelpHint(id);
    if (!h) throw new Error(`missing hint: ${id}`);
    return `${h.title} ${h.body}`.toLowerCase();
  };

  // Hope carried across zero per-patient allergy records, so every chart starts
  // blank. If this ever reads as a clearance, someone gets prescribed through
  // an allergy nobody asked about.
  it("the empty-allergy hint refuses to read as a clearance", () => {
    expect(getHelpHint("allergies-empty")?.safetyCritical).toBe(true);
    expect(text("allergies-empty")).toContain("does not mean the patient has none");
  });

  it("the signing hint states permanence and names the remedy", () => {
    const t = text("note-signed-lock");
    expect(t).toContain("cannot be edited");
    expect(t).toContain("addendum");
  });

  it("the lab verify hint states the result is withheld until verified", () => {
    expect(text("lab-verify-gate")).toContain("not visible to the doctor");
  });

  it("the prescribing-allergy hint stays a warning, not a block", () => {
    expect(text("pharmacy-allergy-warning")).toContain("does not stop you");
  });

  it("safety-critical hints are flagged so they render as warnings", () => {
    for (const id of [
      "allergies-empty",
      "note-signed-lock",
      "lab-verify-gate",
      "pharmacy-allergy-warning",
    ]) {
      expect(getHelpHint(id)?.safetyCritical, id).toBe(true);
    }
  });
});
