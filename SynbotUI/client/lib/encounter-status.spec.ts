import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { ENCOUNTER_STATUS_COLORS, encounterStatusColor } from "./encounter-status";

/**
 * The frontend's status list and the backend's enum are two copies of one fact.
 * They have drifted before: `awaiting_results` sat in the royan_encounters CHECK
 * constraint for months while the Python enum omitted it, so no encounter could
 * ever reach a state the database was perfectly happy to store.
 *
 * This reads the backend constant directly rather than restating it, so the two
 * cannot disagree silently.
 */

const BACKEND = path.resolve(
  __dirname, "..", "..", "..", "backend", "src", "constants.py",
);

function backendStatuses(): string[] {
  if (!fs.existsSync(BACKEND)) return [];
  const src = fs.readFileSync(BACKEND, "utf8");
  const block = src.match(/ENCOUNTER_STATUS_ALLOWED\s*=\s*\{([\s\S]*?)\}/);
  if (!block) return [];
  return Array.from(block[1].matchAll(/"([a-z_]+)"/g)).map((m) => m[1]);
}

describe("encounter status colours", () => {
  it("every backend status has a colour", () => {
    const statuses = backendStatuses();
    expect(statuses.length, "could not read the backend enum").toBeGreaterThan(5);
    const missing = statuses.filter((s) => !(s in ENCOUNTER_STATUS_COLORS));
    expect(
      missing,
      `statuses the backend can set but the UI has no colour for: ${missing.join(", ")}`,
    ).toEqual([]);
  });

  it("defines no colour for a status the backend cannot produce", () => {
    const statuses = new Set(backendStatuses());
    if (statuses.size === 0) return;
    const orphans = Object.keys(ENCOUNTER_STATUS_COLORS).filter((s) => !statuses.has(s));
    expect(orphans, `colours for statuses that no longer exist: ${orphans.join(", ")}`).toEqual([]);
  });

  it("falls back rather than rendering an unstyled badge", () => {
    expect(encounterStatusColor("something_new")).toBeTruthy();
    expect(encounterStatusColor(undefined)).toBeTruthy();
    expect(encounterStatusColor(null)).toBeTruthy();
  });
});
